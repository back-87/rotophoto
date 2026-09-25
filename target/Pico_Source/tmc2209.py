import time


class TMC2209:
    def __init__(self, uart_instance):
        # Bind straight onto the pre-stabilized global serial line
        self.uart = uart_instance

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
        print(
            f"🔧 Calibrating TMC2209: Current={rms_current_ma}mA, Microsteps=1/{microsteps}"
        )
        self.write_reg(0x00, 0x00000004)  # Enable StealthChop2

        cs = min(31, max(0, int((rms_current_ma * 32) / 1414) - 1))
        self.write_reg(0x10, cs << 16)  # Set IHOLD_IRUN

        mstep_lookup = {1: 8, 2: 7, 4: 6, 8: 5, 16: 4, 32: 3, 64: 2, 128: 1, 256: 0}
        deduced_val = mstep_lookup.get(microsteps, 4)
        self.write_reg(0x6C, deduced_val << 24 | 0x100000)  # Enable interpolation
