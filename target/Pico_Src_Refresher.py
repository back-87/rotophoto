import os
import time
import serial

PICO_PORT = "/dev/ttyAMA10"
PICO_BAUD = 115200

SAFE_BOOT_WINDOW = """# --- SAFE BOOT RUNWAY ---
import time
time.sleep_ms(100)
# ------------------------

"""


def deploy_pico_project(src_directory="target/Pico_Source"):
    print("🛰️  Initializing Zero-Echo Raw REPL Flash Engine...")
    ser = None
    try:
        # 1. Open your verified working serial channel layout
        ser = serial.Serial(
            port=PICO_PORT, baudrate=PICO_BAUD, timeout=1.0, rtscts=False, dsrdtr=False
        )

        # 2. Break any active code loops cleanly
        ser.write(b"\x03\x03\n")
        time.sleep(0.05)
        ser.reset_input_buffer()

        # 3. CRUCIAL: Enter programmatic Raw REPL Mode (Ctrl+A)
        # This completely disables all character terminal echoes!
        ser.write(b"\x01")
        time.sleep(0.05)
        ser.reset_input_buffer()
        print("🔓 Pure Serial Raw REPL Latch Engaged (Echo Disabled)!")

        # 4. Stream local folder assets down the wire using clean string formatting
        print(f"📁 Processing assets from local directory: '{src_directory}/'")
        for root, dirs, files in os.walk(src_directory):
            for file in files:
                local_path = os.path.join(root, file)
                remote_path = os.path.relpath(local_path, src_directory)

                with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
                    content_str = f.read()

                if remote_path == "main.py":
                    print(
                        f"   🛡️  Injecting 100ms Safe Boot runway into: {remote_path}"
                    )
                    content_str = SAFE_BOOT_WINDOW + content_str

                print(f"   ↳ Overwriting file asset: {remote_path}")

                # Format the write command using standard python representations
                escaped_raw_content = repr(content_str)
                atomic_write_cmd = f"f = open('{remote_path}', 'w'); f.write({escaped_raw_content}); f.close()\n"

                # Push the command statement string onto the quiet bus
                ser.write(atomic_write_cmd.encode("utf-8"))

                # --- THE HARDWARE COMPILE AND EXECUTE TRIGGER ---
                # Raw REPL mode strictly requires a Ctrl+D byte to tell the compiler
                # to execute the accumulated text statement buffer instantly!
                ser.write(b"\x04")

                # Give the Pico 150ms to finish executing the code and sync its sectors
                time.sleep(0.15)

        print("🔄 Issuing machine soft-reboot to activate fresh firmware layout...")
        # Send Ctrl+B to cleanly exit Raw REPL, then Ctrl+D to reset the system loops
        ser.write(b"\x02")
        time.sleep(0.05)
        ser.write(b"\x04")
        time.sleep(0.1)
        print("✅ Pico successfully provisioned and running standalone!")

    except Exception as e:
        print(f"❌ Synchronization failed: {e}")
    finally:
        if ser is not None and ser.is_open:
            ser.close()
            print("🔒 Hardware port released safely.")
