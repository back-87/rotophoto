import os, time, machine, threading
import ubinascii as binascii
from machine import UART, Pin

uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1), rxbuf=4096, timeout=200)


def reply(s):
    uart.write(s + "\n")


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
            name, size = parts[2], int(parts[3])
            if "/" in name or not name.endswith(".py") or name == "main.py":
                return reply("ERR:name")
            if self.f:
                self.f.close()
            self.name, self.size = name, size
            self.f = open(name + ".tmp", "wb")
            self.expected = 0
            self.crc = 0
            reply("OK")
        elif cmd == "DATA":
            if not self.f:
                return reply("ERR:nobegin")
            off = int(parts[2])
            if off < self.expected:
                return reply("OK")  # duplicate (our earlier ack got lost)
            if off > self.expected:
                return reply("ERR:offset:%d" % self.expected)
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
    """Call from the app's main loop too. Returns True if the line was an update command."""
    if not line.startswith("U:"):
        return False
    try:
        updater.handle(line.strip().split(":"))
    except Exception as e:
        reply("ERR:" + repr(e))
    return True


import app  # your motor logic; call poll_update() from its loop too

# 1. Create thread with target function
thread = threading.Thread(target=app.run, args=(uart, poll_update))

# 2. Start the thread
thread.start()

# --- boot window: stay in update mode if the Pi asks within 1.5s of power-up ---
try:
    while True:
        raw_bytes = uart.readline()
        if raw_bytes is not None:
            # 1. Decode to string safely
            decoded_line = raw_bytes.decode("utf-8", "replace").strip()

            # 2. Print the string safely
            print(f"read from uart: {decoded_line}")

            # 3. Pass the STRING (not bytes) to the handler
            poll_update(decoded_line)
        time.sleep_ms(100)
except KeyboardInterrupt:
    print("\nDetected Ctrl+C. Soft resetting...")
    import machine

    machine.soft_reset()
