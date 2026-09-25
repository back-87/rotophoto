from machine import Pin
import time
import machine  # 🟢 Import machine for soft resets
import tmc2209


def run(uart, log):
    log("Stream consumer active. Awaiting serial commands...")

    # Ensure these variables are aligned identically
    step_pin = Pin(11, Pin.OUT)
    dir_pin = Pin(10, Pin.OUT)
    enable_pin = Pin(12, Pin.OUT)
    enable_pin.value(0)

    buffer = ""

    while True:
        if uart.any() > 0:
            raw_bytes = uart.read(uart.any())
            if raw_bytes:
                if b"\x03" in raw_bytes or b"\x04" in raw_bytes:
                    import machine

                    machine.reset()

                buffer += raw_bytes.decode("utf-8", "ignore")

                if "U:HELLO" in buffer:
                    import machine

                    machine.reset()

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    cmd_line = line.strip()
                    if not cmd_line:
                        continue

                    if "M:TEST" in cmd_line:
                        log("Executing motor test")
                        tmc2209.run(log)
                        log("Finished executing motor test")

        else:
            time.sleep_ms(5)
