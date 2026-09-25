from machine import Pin
import time
import machine  # 🟢 Import machine for soft resets


def run(uart, log):
    log("Stream consumer active. Awaiting serial commands...")

    # Define minimal pin wrappers strictly for conditional tracking
    step_pin = Pin(11, Pin.OUT)
    dir_pin = Pin(10, Pin.OUT)
    enable_pin = Pin(12, Pin.OUT)
    enable_pin.value(0)

    buffer = ""

    while True:
        # Check if characters are physically waiting on the wire
        if uart.any() > 0:
            raw_bytes = uart.read(uart.any())
            if raw_bytes:
                # 🟢 EMERGENCY ESCAPE: If a manual Ctrl+C (\x03) or Ctrl+D (\x04) lands,
                # self-destruct instantly so Core 0 can cleanly take back the line!
                if b"\x03" in raw_bytes or b"\x04" in raw_bytes:
                    import machine

                    machine.soft_reset()

                buffer += raw_bytes.decode("utf-8", "ignore")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    cmd_line = line.strip()
                    if not cmd_line:
                        continue

                    # Loose substring checking guarantees matching regardless of trailing artifacts
                    if "CW" in cmd_line:
                        dir_pin.value(1)
                        # Balanced square wave execution loop
                        for _ in range(100):
                            step_pin.value(1)
                            time.sleep_us(1000)
                            step_pin.value(0)
                            time.sleep_us(1000)
        else:
            # 🟢 THE CRITICAL VALVE:
            # By sleeping for 5ms when quiet, you leave the hardware registers wide open
            # for Core 0's REPL interpreter to catch your Pi's initial bootloader handshake!
            time.sleep_ms(5)
