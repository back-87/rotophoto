import os
from machine import UART, Pin

uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1), rxbuf=4096, timeout=200)
os.dupterm(uart, 0)
uart.irq(os.dupterm_notify, UART.IRQ_RXIDLE)