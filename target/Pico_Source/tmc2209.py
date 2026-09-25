import time
from machine import Pin, UART

# --- 1. Hardware Pin Layout for BTT Pico Z1 ---
STEP_PIN = 11
DIR_PIN = 10
EN_PIN = 12
Z1_ADDRESS = 2  # BTT Pico maps Z-Axis driver to UART Address 2

step = Pin(STEP_PIN, Pin.OUT)
direction = Pin(DIR_PIN, Pin.OUT)
enable = Pin(EN_PIN, Pin.OUT, value=1)  # Start disabled (Active High for OFF)

# --- 2. Your Verified UART Setup ---
tmc_uart = UART(1, baudrate=115200, tx=Pin(8), rx=Pin(9), timeout=50)


def tmc_write(addr, reg, data_bytes):
    """Sends a formatted, CRC-checked configuration packet to the TMC2209."""
    msg = bytearray([0x05, addr, reg | 0x80])
    msg.extend(data_bytes)

    # Your verified Dallas CRC-8 Checksum
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


# --- 3. Driver Initialization ---
def init_z1_driver():
    print("Flashing hardware registers for Z1-Axis driver (Address 2)...")

    # Enable driver power via hardware GPIO pin first
    enable.value(0)
    time.sleep_ms(10)

    # Reg 0x00 (GCONF): Enable StealthChop (silent mode) and internal sense resistors
    # [0x04, 0x00, 0x00, 0x00] enables pdn_disable to allow UART control configuration
    tmc_write(Z1_ADDRESS, 0x00, [0x04, 0x00, 0x00, 0x00])

    # Reg 0x10 (IHOLD_IRUN): Set operational current parameters
    # [IHOLD, IRUN, IHOLDDELAY, 0x00]
    # 0x10 (16) for IRUN provides roughly 50-60% of max driver current.
    # 0x08 (8) for IHOLD keeps a solid holding torque so the monitor doesn't droop when stopped!
    tmc_write(Z1_ADDRESS, 0x10, [0x08, 0x10, 0x02, 0x00])

    # Reg 0x6C (CHOPCONF): Set microstepping.
    # Defaulting to 1/16 microstepping for silky smooth monitor rotation.
    # [0x00, 0x00, 0x00, 0x04] -> MRES=4 (1/16 microstepping)
    tmc_write(Z1_ADDRESS, 0x6C, [0x00, 0x00, 0x00, 0x04])


# --- 4. Motion Test Function ---
def move_motor(steps, delay_seconds, move_clockwise=True):
    direction.value(1 if move_clockwise else 0)
    print(f"Moving {steps} steps...")

    for _ in range(steps):
        step.value(1)
        time.sleep_us(10)
        step.value(0)
        time.sleep_us(int(delay_seconds * 1_000_000))


def run():
    # --- Execution ---
    try:
        # 1. Fire up the UART settings
        init_z1_driver()
        print("Driver configured via UART successfully. Starting movement in 2s...")
        time.sleep(2)

        # 2. Run the test
        # Because we set 1/16 microstepping in CHOPCONF, a standard 200-step motor
        # now needs 3,200 steps to do one full rotation. Let's do a 1/4 turn test (800 steps).
        move_motor(steps=800, delay_seconds=0.001, move_clockwise=True)

        time.sleep(1.5)

        move_motor(steps=800, delay_seconds=0.001, move_clockwise=False)

        # Note: We are LEAVING the driver enabled here because IHOLD will keep
        # your monitor locked in place. If you want to completely release it, call enable.value(1).

    except KeyboardInterrupt:
        enable.value(1)  # Safety shutoff
        print("\nTest interrupted. Motor powered down.")
