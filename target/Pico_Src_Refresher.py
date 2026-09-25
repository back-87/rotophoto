import os, sys
import time
import serial
import binascii
import hashlib
import config


def receive_manifest(ser, line):
    pico_manifest = {}

    while True:
        raw_line = ser.readline()
        if not raw_line or raw_line == b"":
            continue  # Wait for the slow hardware transmission window

        line = raw_line.decode("utf-8", errors="ignore").strip()

        if line == "U:SCAN_START":
            print(" -> Pico manifest stream opened.")
            continue

        if line.startswith("U:LOG:"):
            print(f" 📺 [Pico App Log]: {line.replace('U:LOG:', '')}")
            continue

        if line.startswith("U:HASH:"):
            # Split precisely: ['U', 'HASH', 'path/to/file.py', 'hashstring']
            parts = line.split(":")
            file_path = parts[2]
            file_hash = parts[3]

            # Pop it straight into your standard Python map
            pico_manifest[file_path] = file_hash
            print(f"    [Discovered Remote Asset]: {file_path} -> {file_hash}")
            continue

        if line == "U:SCAN_DONE":
            print(" -> Pico manifest stream closed successfully.")
            break

        # If the Pico crashes or complains, halt before blasting files
        if line.startswith("ERR"):
            raise RuntimeError(f"Pico scan failed: {line}")

    # print(f"Complete remote table compiled: {pico_manifest}")
    return pico_manifest


def _txn(ser, line, retries=3):
    resp = ""  # <-- Initialize a default fallback value here!
    for attempt in range(retries):
        ser.write(line.encode() + b"\n")
        try:
            # 🟢 REMOVED: echo_line = ser.readline() (No longer needed!)

            # Read the actual response from the Pico
            raw_bytes = ser.readline()

            if raw_bytes == b"":
                print(
                    f"⏳ [Pi Retry]: Port went silent on attempt {attempt+1} for command: {line}"
                )
                continue

            resp = raw_bytes.decode("utf-8", errors="replace").strip()
            print(f"RESP: {resp}")
        except Exception as e:
            print(f"💥 Serial read/decode error: {e}")
            continue

        if line.startswith("U:LOG:"):
            print(f" 📺 [Pico App Log]: {line.replace('U:LOG:', '')}")
            continue

        if line[:20].startswith("SCAN") or line[:20].startswith("U:SCAN"):
            return receive_manifest(ser, line)

        if resp == "OK":
            return

        if resp.startswith("ERR"):
            raise RuntimeError(f"{line[:20]}... -> {resp}")

        # If we see a Traceback or an unexpected line, drain the error
        if resp and resp != "":
            full_response = [resp]
            while True:
                extra_line = ser.readline().decode("utf-8", errors="replace").strip()
                if not extra_line:
                    break
                full_response.append(extra_line)

            complete_error = "\n".join(full_response)
            raise RuntimeError(
                f"No ack for {line[:20]}...\n--- PICO CRASH LOG ---\n{complete_error}\n  RESP: \n{resp}\n----------------------"
            )

        # empty = timeout, retry loop continues
    raise RuntimeError(
        f"No ack for {line[:20]}... (Timeout - line was totally silent) RESP: \n{resp}\n"
    )


def push_file(ser, local_path, relative_path, chunk=64):
    data = open(local_path, "rb").read()
    ser.reset_input_buffer()
    _txn(ser, f"U:BEGIN:{relative_path}:{len(data)}")

    for off in range(0, len(data), chunk):
        # Flawless even-length hex packets that won't clip!
        hex_payload = binascii.hexlify(data[off : off + chunk]).decode()
        _txn(ser, f"U:DATA:{off}:{hex_payload}")

    crc = binascii.crc32(data) & 0xFFFFFFFF
    _txn(ser, f"U:END:{crc:08x}")


def deploy_pico_project(src_directory="target/Pico_Source"):
    print(f"Updating logic on BTT Pico with files from: {src_directory}")

    ser = None
    try:
        # 1. 🟢 SINGLE PORT INSTANTIATION: Open the connection EXACTLY once and hold it open!
        ser = serial.Serial(config.PICO_PORT, config.PICO_BAUD, timeout=1.0)

        # 2. 🟢 PRISTINE LINE ALIGNMENT:
        # Slam multiple Ctrl+C's down the raw wire to interrupt any running app loops on core 1,
        # then fire a clean soft reboot to force the board to boot up normally into main.py
        print("Forcing pristine runtime environment alignment...")
        ser.write(b"\x03\x03\x03")  # Ctrl+C (Break)
        time.sleep(0.05)
        ser.write(b"\x02")  # Ctrl+B (Ensure we exit any lingering Raw REPL states)
        time.sleep(0.05)
        ser.write(b"\x04")  # Ctrl+D (Soft reboot cleanly into main.py)
        time.sleep(0.2)  # Give the boot loader clock cycles to settle

        # 3. 🟢 THE BANNER DRAIN: Read the startup text streams out of the queue buffer cleanly
        print("Draining boot banner traffic...")
        while True:
            # Temporarily drop timeout to clear the cache instantly without long waits
            ser.timeout = 0.1
            junk_line = ser.readline()
            if junk_line == b"":
                break
            print(f" [Banner Drain]: {junk_line.decode('utf-8', 'ignore').strip()}")

        # Restore standard network timeout threshold
        ser.timeout = 1.0

        # 4. Now that main.py is up and wide awake on flash storage, send your handshakes!
        print("Sending initialization handshake...")
        _txn(ser, "U:HELLO")
        print("✅ Got initialization handshake confirmation.")

        # Dynamically bump the timeout threshold up safely for heavy file indexing tasks
        # without closing the underlying descriptor handle
        ser.timeout = 5.0
        print("Requesting remote hash manifest table...")
        pico_manifest = _txn(ser, "U:SCAN")
        print(f"✅ Got remote manifest structure.")

        # Return timeout parameters back to standard runtime boundaries
        ser.timeout = 1.0

        # Stream local folder asset updates
        print(f"📁 Processing assets from local directory: '{src_directory}/'")

        any_files_updated = False

        for root, dirs, files in os.walk(src_directory):
            for file in files:
                local_path = os.path.join(root, file)

                # Skip system tracking files completely
                if file.endswith("main.py") or file.endswith("boot.py"):
                    continue

                relative_path = os.path.relpath(local_path, src_directory)
                local_hash = hashlib.md5(open(local_path, "rb").read()).hexdigest()

                if pico_manifest.get(relative_path) == local_hash:
                    print(
                        f"✅ {relative_path} matches remote hash. Skipping transmission!"
                    )
                    continue

                # 🚨 UNIQUE MISMATCH DETECTED: We need to push data!
                # To push raw file chunks securely, we step into Raw REPL mode momentarily
                if not any_files_updated:
                    print(
                        "🛠️ Sync mismatch encountered. Entering Raw REPL upload state..."
                    )
                    ser.write(b"\x03\x03\x03")  # Halt main.py execution loop
                    time.sleep(0.05)
                    ser.write(b"\x01")  # Enter Raw REPL Mode safely
                    time.sleep(0.05)
                    any_files_updated = True

                push_file(ser, local_path, relative_path)
                print(f"🚀 Did push updated file asset: {local_path}")
                time.sleep(0.15)
                ser.reset_input_buffer()

        # 5. 🏁 HANDOVER AND LAUNCH APPLICATION MOTOR CORE TRACKING:
        print("🏁 Synchronization transactions finalized. Dropping REPL blocks...")

        # Explicitly exit Raw REPL mode and allow the board to fallback to storage boots
        ser.write(b"\x02")  # Ctrl+B
        time.sleep(0.05)

        # Fire a final clean soft reboot to launch main.py and pass control to app.run()
        ser.write(b"\x04")  # Ctrl+D
        time.sleep(0.1)
        print("✅ Pico successfully provisioned and running standalone!")

    except Exception as e:
        print(f"❌ Synchronization pipeline failure: {e}")
        sys.exit(1)
    finally:
        if ser is not None and ser.is_open:
            ser.close()
            print("🔒 Hardware port released safely.")
