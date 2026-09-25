import os
import time
import serial
import binascii

PICO_PORT = "/dev/ttyAMA10"
PICO_BAUD = 115200


def _txn(ser, line, retries=3):
    for _ in range(retries):
        ser.write(line.encode() + b"\n")
        resp = ser.readline().decode().strip()
        if resp == "OK":
            return
        if resp.startswith("ERR"):
            raise RuntimeError(f"{line[:20]}... -> {resp}")
        # empty = timeout, retry (Pico ignores duplicate DATA offsets)
    raise RuntimeError(f"No ack for {line[:20]}...")


def push_file(ser, local_path, remote_name, chunk=128):
    data = open(local_path, "rb").read()
    _txn(ser, f"U:BEGIN:{remote_name}:{len(data)}")
    for off in range(0, len(data), chunk):
        _txn(ser, f"U:DATA:{off}:{binascii.hexlify(data[off:off+chunk]).decode()}")
    crc = binascii.crc32(data) & 0xFFFFFFFF
    _txn(ser, f"U:END:{crc:08x}")


def deploy_pico_project(src_directory="target/Pico_Source"):
    print(f"Updating logic on BTT Pico with files from: {src_directory}")
    ser = None
    try:
        ser = serial.Serial(PICO_PORT, PICO_BAUD, timeout=1)

        _txn(ser, "U:HELLO")  # works if the Pico is in its boot window

        # Stream local folder assets
        print(f"📁 Processing assets from local directory: '{src_directory}/'")
        for root, dirs, files in os.walk(src_directory):
            for file in files:
                local_path = os.path.join(root, file)

                if not file.endswith("main.py"):
                    push_file(ser, local_path, file)
                    print(f"Did push file: {local_path}")
                else:
                    print(
                        "not overwriting main.py, that's only done with USB-C and Thonny. All modifications start in app.py"
                    )

                # Give the Pico 150ms to finish executing the code and sync its sectors
                time.sleep(0.15)

        # _txn(ser, "U:RESET")
        print("✅ Pico successfully provisioned and running standalone!")

    except Exception as e:
        print(f"❌ Synchronization failed: {e}")
    finally:
        if ser is not None and ser.is_open:
            ser.close()
            print("🔒 Hardware port released safely.")
