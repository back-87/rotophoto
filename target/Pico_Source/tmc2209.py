import time
from machine import UART, Pin


class TMC2209:
    def __init__(self, log):
        self.log = log

    def wake_up_driver_stage(self):
        """
        Initialises the shared internal TMC2209 configuration bus (UART1).
        Disables software safety standby locks for the X-axis (Address 0).
        """
        try:
            # Open the hardware bus (UART1, GP8, GP9)
            tmc_uart = UART(1, baudrate=115200, tx=Pin(8), rx=Pin(9), timeout=50)

            def tmc_write(addr, reg, data_bytes):
                # Frame string payload structure: Sync (0x05) + Node Addr + Reg Addr + Data Bytes
                msg = bytearray([0x05, addr, reg | 0x80])
                msg.extend(data_bytes)

                # Verified hardware standard Dallas CRC-8 Checksum calculation
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
                time.sleep_ms(10)  # Let the chip register settle securely

            self.log("Flashing hardware registers for X-Axis driver (Address 0)...")

            # 1. IHOLD_IRUN (Reg 0x10): Set operational current parameters
            # Sets IRUN to a safe runtime current and gives IHOLD active holding force
            tmc_write(0, 0x10, [0x08, 0x10, 0x00, 0x00])

            # 2. CHOPCONF (Reg 0x6C): Disable the software power down locks!
            # Sets TOFF = 4 (enables the driver gates) and configures microsteps
            tmc_write(0, 0x6C, [0x04, 0x00, 0x00, 0x10])

            # 3. PWMCONF (Reg 0x70): Enable stealthChop PWM voltage autoscale modes
            tmc_write(0, 0x70, [0x04, 0x04, 0x00, 0x00])

            self.log("TMC2209 configuration registers flashed successfully!")

        except Exception as e:
            self.log(f"💥 Driver initialization failed: {repr(e)}")

    def write_reg(self, reg, value):
        buf = bytearray(
            [
                0x05,
                0x00,
                reg | 0x80,
                (value >> 24) & 0xFF,
                (value >> 16) & 0xFF,
                (value >> 8) & 0xFF,
                value & 0xFF,
            ]
        )
        crc = 0
        for b in buf:
            for _ in range(8):
                if (crc ^ b) & 0x01:
                    crc = (crc >> 1) ^ 0x8C
                else:
                    crc >>= 1
                b >>= 1
        buf.append(crc)
        self.uart.write(buf)
        time.sleep_ms(5)

    def configure_driver(self, rms_current_ma=800, microsteps=16):
        self.log(
            f"🔧 Calibrating TMC2209: Current={rms_current_ma}mA, Microsteps=1/{microsteps}"
        )
        self.write_reg(0x00, 0x00000004)  # Enable StealthChop2

        cs = min(31, max(0, int((rms_current_ma * 32) / 1414) - 1))
        self.write_reg(0x10, cs << 16)  # Set IHOLD_IRUN

        mstep_lookup = {1: 8, 2: 7, 4: 6, 8: 5, 16: 4, 32: 3, 64: 2, 128: 1, 256: 0}
        deduced_val = mstep_lookup.get(microsteps, 4)
        self.write_reg(0x6C, deduced_val << 24 | 0x100000)  # Enable interpolation
