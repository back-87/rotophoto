import time
from machine import Pin, UART

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DRIVER_BAUD_RATE = 115200  # TMC2209 auto-detects baud from the sync byte.
# Raise later if you want; drop back down if reads get flaky.

STEP_PIN = 6
DIR_PIN = 5
EN_PIN = 7
Y_ADDRESS = 2  # UART address of the Y driver on the SKR Pico

MICROSTEPS = 16
FULL_STEPS_PER_REV = 200
GEAR_RATIO = 51  # 51:1 gearbox (actual planetary ratios are often ~50.9)
STEPS_PER_OUTPUT_REV = FULL_STEPS_PER_REV * MICROSTEPS * GEAR_RATIO  # 163,200

# Start modest, ramp up once you see it moving. 0-31 scale.
IRUN = 16
IHOLD = 8
IHOLDDELAY = 1

# Register map
REG_GCONF = 0x00
REG_GSTAT = 0x01
REG_IFCNT = 0x02
REG_IOIN = 0x06
REG_IHOLD_IRUN = 0x10
REG_CHOPCONF = 0x6C
REG_DRV_STATUS = 0x6F
REG_PWMCONF = 0x70

# ---------------------------------------------------------------------------
# UART init
# ---------------------------------------------------------------------------
time.sleep_ms(500)

try:
    UART(1).deinit()
except Exception:
    pass

tmc_uart = UART(1, baudrate=DRIVER_BAUD_RATE, tx=Pin(8), rx=Pin(9), timeout=20)

# ---------------------------------------------------------------------------
# Motion pins
# ---------------------------------------------------------------------------
step = Pin(STEP_PIN, Pin.OUT, value=0)
direction = Pin(DIR_PIN, Pin.OUT)
enable = Pin(EN_PIN, Pin.OUT, value=1)  # active-low: 1 = disabled


# ---------------------------------------------------------------------------
# TMC2209 UART protocol
# ---------------------------------------------------------------------------
def crc8(data):
    """TMC CRC8 (poly 0x07), computed over ALL bytes incl. the 0x05 sync byte."""
    crc = 0
    for byte in data:
        for _ in range(8):
            if (crc >> 7) ^ (byte & 0x01):
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
            byte >>= 1
    return crc


def _flush():
    while tmc_uart.any():
        tmc_uart.read()


def tmc_write(addr, reg, value):
    """Write a 32-bit register. The TMC2209 does not ACK; verify via IFCNT."""
    msg = bytearray(
        [
            0x05,
            addr,
            reg | 0x80,
            (value >> 24) & 0xFF,
            (value >> 16) & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        ]
    )
    msg.append(crc8(msg))
    _flush()
    tmc_uart.write(msg)
    time.sleep_ms(5)
    _flush()  # discard our own echo (single-wire UART)


def tmc_read(addr, reg):
    """Read a 32-bit register. Returns int, or None on failure."""
    msg = bytearray([0x05, addr, reg])
    msg.append(crc8(msg))
    _flush()
    tmc_uart.write(msg)
    time.sleep_ms(5)
    resp = tmc_uart.read(12)  # 4-byte echo + 8-byte reply
    if not resp or len(resp) < 12:
        return None
    reply = resp[4:]
    if reply[0] != 0x05 or reply[2] != reg or crc8(reply[:7]) != reply[7]:
        return None
    return int.from_bytes(reply[3:7], "big")  # MSB first


def fmt(val):
    return "READ FAILED" if val is None else "{:#010x}".format(val)


# ---------------------------------------------------------------------------
# Driver setup
# ---------------------------------------------------------------------------
def init_driver(log_fx=print):
    ifcnt_before = tmc_read(Y_ADDRESS, REG_IFCNT)
    log_fx("IFCNT before: {}".format(ifcnt_before))

    # Comms sanity check: IOIN top byte is the chip version (0x21 for TMC2209)
    ioin = tmc_read(Y_ADDRESS, REG_IOIN)
    if ioin is None:
        log_fx("WARNING: no valid reply from driver. Check wiring/address/VMOT.")
    else:
        log_fx("IOIN: {} (version byte should be 0x21)".format(fmt(ioin)))

    # Clear reset / drv_err / uv_cp flags
    tmc_write(Y_ADDRESS, REG_GSTAT, 0x00000007)

    # GCONF: pdn_disable (bit6) + mstep_reg_select (bit7) + multistep_filt (bit8)
    tmc_write(Y_ADDRESS, REG_GCONF, 0x000001C0)

    # CHOPCONF: 1/16 microstepping (MRES=4) + interpolation to 256 (intpol)
    tmc_write(Y_ADDRESS, REG_CHOPCONF, 0x14000053)

    # IHOLD_IRUN
    ihold_irun = (IHOLDDELAY << 16) | (IRUN << 8) | IHOLD
    tmc_write(Y_ADDRESS, REG_IHOLD_IRUN, ihold_irun)

    ifcnt_after = tmc_read(Y_ADDRESS, REG_IFCNT)
    log_fx("IFCNT after:  {} (should be 4 higher than before)".format(ifcnt_after))

    if ifcnt_before is not None and ifcnt_after is not None:
        delta = (ifcnt_after - ifcnt_before) & 0xFF
        if delta == 4:
            log_fx("UART comms OK: all 4 writes accepted.")
        else:
            log_fx("UART comms PROBLEM: only {} of 4 writes accepted.".format(delta))


def dump_registers(log_fx=print):
    log_fx("GSTAT:       {}".format(fmt(tmc_read(Y_ADDRESS, REG_GSTAT))))
    log_fx("GCONF:       {}".format(fmt(tmc_read(Y_ADDRESS, REG_GCONF))))
    log_fx("CHOPCONF:    {}".format(fmt(tmc_read(Y_ADDRESS, REG_CHOPCONF))))
    log_fx("PWMCONF:     {}".format(fmt(tmc_read(Y_ADDRESS, REG_PWMCONF))))
    log_fx("DRV_STATUS:  {}".format(fmt(tmc_read(Y_ADDRESS, REG_DRV_STATUS))))
    # IHOLD_IRUN is write-only on the TMC2209, so it can't be read back.
    # DRV_STATUS bits of interest: 0=otpw (overtemp warn), 1=ot (overtemp shutdown),
    # 2/3=short to GND A/B, 4/5=short to supply, 6/7=open load A/B, 31=stst (standstill)


init_driver()


# ---------------------------------------------------------------------------
# Motion
# ---------------------------------------------------------------------------
def run(log_fx):
    log_fx("Initializing motor...")

    enable.value(0)  # enable driver (active-low)
    time.sleep_ms(50)

    direction.value(1)  # flip to 0 to reverse
    time.sleep_ms(10)

    start_delay = 1800  # us per half-period at start
    end_delay = 500  # us per half-period at cruise (minimum 500)
    ramp_steps = 15000
    total_steps = STEPS_PER_OUTPUT_REV * 90 // 360  # 90 degrees at the output shaft

    log_fx("Starting motor movement ({} steps)...".format(total_steps))
    for i in range(total_steps):
        if i < ramp_steps:
            current_delay = start_delay - int(
                (start_delay - end_delay) * (i / ramp_steps)
            )
        else:
            current_delay = end_delay

        step.value(1)
        time.sleep_us(current_delay)
        step.value(0)
        time.sleep_us(current_delay)

    log_fx("Movement complete. Register dump:")
    dump_registers(log_fx)
    enable.value(1)  # disable driver
