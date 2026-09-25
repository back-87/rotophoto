from machine import Pin
import time
import machine  # 🟢 Import machine for soft resets


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

                    if "CW" in cmd_line:
                        dir_pin.value(1)
                        for _ in range(100):
                            step_pin.value(1)
                            time.sleep_us(1000)
                            step_pin.value(0)
                            time.sleep_us(1000)
        else:
            time.sleep_ms(5)
