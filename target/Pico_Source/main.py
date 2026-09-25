from machine import UART, Pin
import time

# this is a test

time.sleep_ms(500)

uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))

from tmc2209 import TMC2209

driver = TMC2209(uart_instance=uart)
driver.configure_driver(rms_current_ma=700, microsteps=16)

step_pin = Pin(11, Pin.OUT)
dir_pin = Pin(10, Pin.OUT)
en_pin = Pin(12, Pin.OUT)
en_pin.value(1)


def run_motion_profile(steps, direction, delay_us):
    dir_pin.value(direction)
    en_pin.value(0)
    time.sleep_ms(2)

    for i in range(steps):
        if uart.any():
            if uart.read(1) == b"S":
                en_pin.value(1)
                return i
        step_pin.value(1)
        time.sleep_us(delay_us)
        step_pin.value(0)
        time.sleep_us(delay_us)

    en_pin.value(1)
    return steps


print("Pico Passive Shell Matrix Active. Standing by...")

while uart.any():
    uart.read(1)

rx_buffer = ""

while True:
    while uart.any():
        raw_char = uart.read(1)

        if raw_char == b"\n" or raw_char == b"\r":
            cmd = rx_buffer.strip()
            rx_buffer = ""

            if cmd == "PING":
                uart.write("PONG\n")

            elif cmd == "ROTATE_PORTRAIT":
                uart.write("MOVING\n")
                actual_steps = run_motion_profile(40800, 1, 400)
                uart.write(f"COMPLETED:{actual_steps}\n")

            elif len(cmd) > 0:
                uart.write(f"RECEIVED_UNKNOWN:{cmd}\n")
        else:
            try:
                rx_buffer += raw_char.decode("utf-8", "ignore")
            except Exception:
                pass

    time.sleep_ms(5)
