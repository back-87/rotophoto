import serial
import threading
import time
import config
import sys
import atexit
import signal


class PicoConnection:
    def __init__(self, port=config.PICO_PORT, baud=config.PICO_BAUD, timeout=0.5):
        self.ser = serial.Serial(port, baud, timeout=timeout)
        self._running = False
        self._listener_thread = None

        # Register cleanups for standard exits and crashes
        atexit.register(self.purge_serial_lines)

        # Register cleanups for OS interruption signals
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        # 🟢 THE LIFELINE EVENT FLAG: Initialize as False (unset)
        self._ready_event = threading.Event()

        self.on_log_received = lambda msg: print(f" 📺 [Pico App Log]: {msg}")

        # 1. Immediately spin up the background serial monitoring loop
        self.start_monitoring()

        # 2. BLOCK HERE! Wait for the Pico to send 'U:READY' down the line.
        # If it doesn't arrive within 5 seconds, it returns False (Timeout)
        print("⏳ Waiting for Pico to finish bootloader phase and signal ready...")


        deadline = time.time() + 15.0
        ready_received = False
        while time.time() < deadline:
            self.ser.write(b"U:PING\n")
            if self._ready_event.wait(timeout=1.0):
                ready_received = True
                break
            else:
                print("Timed out, retrying...")

        print("✅ Pico is ready. Control channel unblocked")




    def purge_serial_lines(self, *args):
        # Using *args allows this method to safely ingest:
        # - 'self' (passed automatically as an instance method)
        # - Nothing (when called by atexit)
        # - signum, frame (when called by signal.signal)

        if self.ser and self.ser.is_open:
            print("\n🛑 [Teardown]: Sanitizing serial lines before exit...")
            try:
                self.ser.write(b"\x03\r\n")
                self.ser.flush()
                time.sleep(0.05)

                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()

                self.ser.close()
                print("🔒 [Teardown]: Hardware port released safely and flushed.")
            except Exception as e:
                print(f"⚠️ [Teardown Error]: Cleanup failed: {e}")

        # If this was fired by an OS signal, kill the process cleanly
        if args and not isinstance(args[0], PicoConnection):
            import sys
            sys.exit(0)

    def handle_signal(signum, frame):
        # Intercepts Ctrl+C (SIGINT) or kill commands (SIGTERM)
        purge_serial_lines()
        sys.exit(0)

    def _listen_loop(self):
        """Background thread that constantly drains line traffic."""
        while self._running:
            try:
                if self.ser.in_waiting > 0:
                    raw_line = self.ser.readline()
                    if not raw_line:
                        continue

                    line = raw_line.decode("utf-8", errors="ignore").strip()

                    print(f"RAW LINE: {line}")
                    if "U:READY" in line or "U:PONG" in line:
                        self._ready_event.set()
                        continue

                    if "U:LOG:" in line:
                        clean_msg = line.replace("U:LOG:", "")
                        self.on_log_received(clean_msg)
                        continue

            except Exception as e:
                print(f"⚠️ Serial reader thread encountered error: {e}")
                time.sleep(0.1)
            time.sleep(0.005)  # Keep CPU core consumption lean


    def start_monitoring(self):
        """Starts the background telemetry pipeline."""
        if not self._running:
            self._running = True
            self._listener_thread = threading.Thread(
                target=self._listen_loop, daemon=True
            )
            self._listener_thread.start()
            print("🚀 Pi 5 background serial monitoring active.")

    def stop_monitoring(self):
        self._running = False
        if self._listener_thread:
            self._listener_thread.join()

    def send_cmd(self, cmd_string):
        try:
            formatted_cmd = cmd_string.strip() + "\n"
            self.ser.write(formatted_cmd.encode('utf-8'))
            print(f"PicoConnection did send_cmd: {formatted_cmd.encode("utf-8")}")
            self.ser.flush()

            # 🟢 THE RACE FIX: Give the Pico's zero-timeout buffer ring accumulator
            # loop a micro-delay window to scoop up these explicit command bytes completely!
            time.sleep(0.02)

        except Exception as e:
            print(f"💥 Failed to transmit command: {e}")



