import time
from machine import Pin, UART

# --- 1. REPL & DMA HARDWARE PURGE PHASE ---
time.sleep_ms(500)

try:
    old_uart = UART(1)
    old_uart.deinit()
    time.sleep_ms(100)
except:
    pass

# --- FORCE LINE FLUSH ---
# Hard-force both serial lines down to Ground for 100ms
# This breaks any hanging REPL/DMA states and forces a clean edge reset
tx_purge = Pin(8, Pin.OUT, value=0)
rx_purge = Pin(9, Pin.OUT, value=0)
time.sleep_ms(100)

# Release pins back to high-impedance input states before handing them to UART
tx_purge.init(Pin.IN)
rx_purge.init(Pin.IN)
time.sleep_ms(20)

# --- 2. PIN ASSIGNMENTS ---
STEP_PIN = 6
DIR_PIN = 5
EN_PIN = 7
Y_ADDRESS = 2

step = Pin(STEP_PIN, Pin.OUT, value=1)
direction = Pin(DIR_PIN, Pin.OUT)
# Explicitly force the driver's hardware Enable pin LOW to ground immediately
# This bypasses any register delays and locks the motor shafts instantly
enable = Pin(EN_PIN, Pin.OUT, value=0)

# Re-instantiate a pristine UART channel
tmc_uart = UART(1, baudrate=115200, tx=Pin(8), rx=Pin(9), timeout=20)


def tmc_write(addr, reg, data_bytes):
    # Deep purge: aggressively dump any trailing bytes left over from the manifest transfer
    while tmc_uart.any():
        tmc_uart.read()

    msg = bytearray([0x05, addr, reg | 0x80])
    msg.extend(data_bytes)

    # Calculate Trinamic CRC8
    crc = 0
    for b in msg:
        for _ in range(8):
            if (crc ^ b) & 0x01:
                crc = (crc >> 1) ^ 0x8C
            else:
                crc >>= 1
            b >>= 1
    msg.append(crc)

    tmc_uart.write(msg)
    time.sleep_ms(10)

    # Empty the single-wire physical loopback echo completely
    while tmc_uart.any():
        tmc_uart.read()


def run(log_fx):
    log_fx("Initializing TMC2209 with robust 1/16 high-torque curve...")

    enable.value(0)
    time.sleep_ms(50)

    # 1. UART Unlock
    tmc_write(Y_ADDRESS, 0x00, [0x00, 0x00, 0x00, 0x02])
    time.sleep_ms(20)

    # 2. CHOPCONF: 1/16 Microstepping default
    tmc_write(Y_ADDRESS, 0x6C, [0x10, 0x00, 0x00, 0x53])
    time.sleep_ms(20)

    # 3. IHOLD_IRUN: High torque profile
    tmc_write(Y_ADDRESS, 0x10, [0x00, 0x01, 0x1F, 0x0A])
    time.sleep_ms(50)

    log_fx("Launching step train with sustainable acceleration...")
    direction.value(1)  # Change to 0 if it sweeps the wrong way!
    time.sleep_ms(10)

    # Widened delays to maximize mechanical torque and avoid driver back-EMF trips
    start_delay = 1800  # Broad 1.8ms starting delay to guarantee initial breakthrough
    end_delay = 450  # Safe, sustainable cruise speed (450us interval)
    ramp_steps = (
        15000  # Long, gradual 15,000-step runway to ease the monitor into motion
    )
    total_steps = 81600  # Exact 90-degree turn past a 51:1 gear at 1/16 microstepping

    for i in range(total_steps):
        step.value(1)

        if i < ramp_steps:
            current_delay = start_delay - int(
                (start_delay - end_delay) * (i / ramp_steps)
            )
        else:
            current_delay = end_delay

        time.sleep_us(current_delay)

        step.value(0)
        time.sleep_us(current_delay)

    log_fx("Sequence complete. Locking load.")
    enable.value(0)
