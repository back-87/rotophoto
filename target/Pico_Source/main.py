import os, time, machine, threading
import ubinascii as binascii
import uhashlib
import json
import select
import sys, io
import gc
from machine import UART, Pin

uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1), rxbuf=4096, timeout=200)

import builtins

# 1. Store a pointer to the original, true system print function
_true_print = builtins.print


def smart_protocol_print(*args, **kwargs):
    """
    Overrides the global print() function to safely protect the UART protocol.
    """
    sep = kwargs.get("sep", " ")
    message = sep.join(str(arg) for arg in args)

    if message.startswith("U:") or message.startswith("ERR:"):
        _true_print(message, **kwargs)
        return

    escaped_log = f"U:LOG:{message}"
    _true_print(escaped_log, **kwargs)


def walk_and_stream(path=""):
    """
    Recursively crawls the physical flash storage directory manifests.
    Computes MD5 hashes for files and streams them securely up to the Pi.
    """
    try:
        # Open a clean iterator handle for the target folder path lane
        for entry in os.ilistdir(path):
            # 🟢 FIXED: Safe variable extraction.
            # Grabs the first two core properties completely independent of tuple lengths!
            item_name = entry[0]
            entry_type = entry[1]

            # Formulate the fully qualified system asset path layout
            full_path = f"{path}/{item_name}" if path else item_name

            if entry_type == 0x4000:  # 📁 It is a Directory / Folder context
                walk_and_stream(full_path)

            elif entry_type == 0x8000:  # 📄 It is a valid File asset block
                # Avoid hashing system tracking configurations or transient logs
                if not full_path.endswith(".tmp") and full_path not in [
                    "main.py",
                    "boot.py",
                ]:
                    h = get_file_md5(full_path)
                    if h:
                        # Stream the manifest string response payload cleanly
                        reply(f"U:HASH:{full_path}:{h}")

    except Exception as e:
        # Prevent recursive folder crawling bugs from causing system resets
        reply(f"U:LOG:[SCAN_ERROR] Failed to map directory frame {path}: {repr(e)}")


def reply(s):
    raw_payload = (s.strip() + "\n").encode("utf-8")
    uart.write(raw_payload)


def get_file_md5(filepath):
    """Standalone utility to safely hash files in small RAM chunks."""
    try:
        hasher = uhashlib.md5()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(128)
                if not chunk:
                    break
                hasher.update(chunk)
        gc.collect()  # Force RAM garbage collection immediately after closing the file
        return binascii.hexlify(hasher.digest()).decode()
    except OSError:
        return None


def generate_json_encoded_hash_manifest(root_directory=""):
    manifest = {}

    for root, dirs, files in os.walk(root_directory):
        for file in files:
            local_path = os.path.join(root, file)

            if not file.endswith("main.py"):
                relative_path = os.path.relpath(local_path, root_directory)
                try:
                    with open(local_path, "rb") as f:
                        # 1. 🟢 Compute the raw hash object
                        hash_obj = hashlib.md5(f.read())

                        # 2. 🟢 Extract binary bytes and turn them into a hex string
                        raw_bytes = hash_obj.digest()
                        hex_string = ubinascii.hexlify(raw_bytes).decode("utf-8")

                    manifest[relative_path] = hex_string
                except Exception as e:
                    print(f"Error hashing {relative_path}: {e}")
            else:
                print("not hashing main.py")

    return json.dumps(manifest)


def trigger_reboot():
    try:
        os.dupterm(None, 0)
    except:
        pass

    time.sleep_ms(
        50
    )  # Allow physical peripheral registers to flush their pipeline cache strings
    machine.soft_reset()


def ensure_dir_exists(filepath):
    """Recursively creates parent directories for a given relative filepath if they don't exist."""
    parts = filepath.split("/")
    if len(parts) == 1:
        return  # File is destined for the root directory, no folders needed

    current_dir = ""
    # Loop through all path fragments except the actual file name at the end
    for folder in parts[:-1]:
        if not folder:
            continue
        current_dir = f"{current_dir}/{folder}" if current_dir else folder
        try:
            os.mkdir(current_dir)
        except OSError as e:
            # Errno 17 means EEXIST (Directory already exists). We safely ignore this.
            if e.errno != 17:
                raise e


class Updater:
    def __init__(self):
        self.f = None
        self.name = None
        self.size = 0
        self.expected = 0
        self.crc = 0

    def handle(self, parts):
        cmd = parts[1]
        if cmd == "BEGIN":
            # Unpack fields precisely. Parts[2] is the full relative path string
            name, size = parts[2], int(parts[3])

            # Keep protection for main.py, but allow folder paths
            if not name.endswith(".py") or name == "main.py":
                return reply("ERR:name")
            if self.f:
                self.f.close()

            self.name, self.size = name, size

            try:
                # 1. Force the directory tree into existence on the LittleFS drive
                ensure_dir_exists(name)

                # 2. Open the temporary file in its designated subfolder destination
                self.f = open(name + ".tmp", "wb")
            except Exception as e:
                return reply(f"ERR:mkdir:{repr(e)}")

            self.expected = 0
            self.crc = 0
            reply("OK")

        elif cmd == "SCAN":
            reply("U:SCAN_START")
            print("starting scan")
            walk_and_stream()
            reply("U:SCAN_DONE")

            # CRITICAL SAFEGUARD: Push the bootloader window forward
            # so the 1.5s clock restarts FRESH right after finishing a long scan!
            global start_time
            start_time = time.ticks_ms()
            return
        elif cmd == "DATA":
            if not self.f:
                return reply("ERR:nobegin")
            off = int(parts[2])
            if off < self.expected:
                return reply("OK")
            if off > self.expected:
                return reply("ERR:offset:%d" % self.expected)

            # parts[3] now safely retains all data without truncation!
            data = binascii.unhexlify(parts[3])
            self.f.write(data)
            self.expected += len(data)
            self.crc = binascii.crc32(data, self.crc) & 0xFFFFFFFF
            reply("OK")
        elif cmd == "END":
            if not self.f:
                return reply("ERR:nobegin")
            self.f.close()
            self.f = None
            tmp = self.name + ".tmp"
            if self.expected != self.size or self.crc != int(parts[2], 16):
                os.remove(tmp)
                return reply("ERR:verify")
            os.rename(tmp, self.name)  # atomic replace on littlefs (RP2040 default)
            # CRITICAL SAFEGUARD: Restart the 1.5s clock after a heavy file write completes!
            global start_time
            start_time = time.ticks_ms()
            reply("OK")
        elif cmd == "RESET":
            reply("OK")
            time.sleep_ms(50)
            machine.reset()
        elif cmd == "HELLO":
            reply("OK")
            time.sleep_ms(50)


updater = Updater()


def poll_update(line):
    """Returns True only if a valid, supported update command was handled."""
    if not line.startswith("U:"):
        return False

    # parts[0] = "U"
    # parts[1] = "BEGIN" / "DATA" / "END"
    # parts[2] = offset / filename
    # parts[3] = the rest of the payload line (safely preserving any colons)
    parts = line.strip().split(":", 3)
    cmd = parts[1]

    # Only claim responsibility if it's a command our updater actually handles
    if cmd not in ["BEGIN", "DATA", "END", "RESET", "SCAN", "HELLO"]:
        return False

    try:
        updater.handle(parts)
        return True  # Handled successfully
    except Exception as e:
        reply("ERR:" + repr(e))
        return False


# Create a poll object to monitor standard input (USB Serial)
poll_obj = select.poll()
poll_obj.register(sys.stdin, select.POLLIN)

start_time = time.ticks_ms()
timeout_window_ms = 5000

try:
    while time.ticks_diff(time.ticks_ms(), start_time) < timeout_window_ms:
        # Check if there is data waiting in the serial buffer (timeout 100ms)
        # This keeps the loop spinning so the 5-second timer works!
        if poll_obj.poll(100):
            # Read the line from USB Serial
            raw_bytes = sys.stdin.readline().encode("utf-8")

            if raw_bytes and raw_bytes != b"":
                try:
                    decoded_line = raw_bytes.decode("utf-8", "replace").strip()
                except UnicodeDecodeError:
                    print(f"💥 HEX EXPOSED! Raw bytes that blew up: {raw_bytes}")
                    continue

                if poll_update(decoded_line):
                    # Reset the 5-second window if a valid packet arrived
                    start_time = time.ticks_ms()
except KeyboardInterrupt:
    print("\nDetected Ctrl+C. Soft resetting...")

    trigger_reboot()


# ==========================================
# 4. Safe App Handover Gate (Bottom of main.py)
# ==========================================


def app_bootstrap():
    try:
        # 1. Clear terminal duplication hooks cleanly inside Core 1
        os.dupterm(None, 0)
        uart.irq(handler=None, trigger=0)
        time.sleep_ms(50)

        # 2. Spin up a fresh, clean hardware object instance for the app
        import app

        fresh_uart = machine.UART(
            0,
            baudrate=115200,
            tx=machine.Pin(0),
            rx=machine.Pin(1),
            rxbuf=4096,
            timeout=0,
        )

        # Pass the pristine new handle down to your app loop!
        app.run(fresh_uart, smart_protocol_print)

    except Exception as e:
        import sys, io

        buf = io.StringIO()
        sys.print_exception(e, buf)
        for line in buf.getvalue().splitlines():
            if line.strip():
                _true_print(f"U:LOG:[CRASH] {line.strip()}")
        time.sleep_ms(500)


# --- THE EXECUTION GATEWAY ---
# 1. Broadcast your ready sequence string while the initial boot link is 100% active
reply("U:READY")
time.sleep_ms(100)

# 2. Launch your background thread smoothly targeting your fresh handler bootstrap
thread = threading.Thread(target=app_bootstrap)
thread.start()

# Core 0 loops silently in background memory, completely un-patched and safe
while True:
    time.sleep(1)
