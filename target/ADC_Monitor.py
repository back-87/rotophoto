import time
import threading
import board
import busio
from adafruit_ads1x15 import ads1x15
from adafruit_ads1x15.ads1115 import ADS1115
from adafruit_ads1x15.analog_in import AnalogIn
from adafruit_ads1x15.ads1x15 import Mode


class ADC_Monitor:
    v0 = 0.0
    v1 = 0.0

    on_entered_edge_fx = lambda: print("on entered edge function not set")
    on_left_edge_fx = lambda: print("on left edge function not set")

    NORTH_POLE = "NORTH_POLE"
    SOUTH_POLE = "SOUTH_POLE"

    # --- Configuration ---
    LOW_THRESHOLD = 1.0  # Volts
    HIGH_THRESHOLD = 4.3  # Volts

    def __init__(self):
        # --- Initialize I2C and ADS1115 ---
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.ads = ADS1115(self.i2c)

        # Set gain to 1 (±4.096V range) which covers 0-3.3V well
        self.ads.gain = 1

        self.ads.data_rate = 860  # Run at max hardware speed

        # Use the explicit Pin mapping enum (A0 and A1)
        self.chan0 = AnalogIn(self.ads, ads1x15.Pin.A0)
        self.chan1 = AnalogIn(self.ads, ads1x15.Pin.A1)

        self.state_0 = "NORMAL"
        self.state_1 = "NORMAL"

        # --- Correct Adafruit Mode & Comparator Setup ---
        # 1. Mode configures the chip sampling cycle (SINGLE or CONTINUOUS)
        self.ads.mode = Mode.SINGLE

        # 2. Window thresholds are mapped using explicit comparator attributes
        from adafruit_ads1x15.ads1x15 import Comp_Mode

        self.ads.comparator_mode = Comp_Mode.WINDOW
        self.ads.low_threshold = 16800
        self.ads.high_threshold = 23200

        self.running = False
        self._thread = None

    def _loop(self):
        while self.running:
            # 1. Physically read and update A0
            self.v0 = self.chan0.voltage
            self.state_0 = self.check_edges("A0", self.v0)

            # 2. Give the multiplexer a brief moment to settle if ghosting persists
            # time.sleep(0.002)

            # 3. Physically read and update A1
            self.v1 = self.chan1.voltage
            self.state_1 = self.check_edges("A1", self.v1)

            # Keep your original cycle delay
            time.sleep(0.5)

    def check_edges(self, channel_name, voltage):
        """
        Checks voltage against thresholds and prints edge events.
        Returns the new state.
        """
        voltage = 0.0

        if channel_name == "A0":
            # Flush the multiplexer ghost charge
            _ = self.chan0.voltage
            time.sleep(0.0015)  # Micro-delay to let the voltage settle

            # Take the real reading
            voltage = self.v0 = self.chan0.voltage
            print(f"read A0 voltage: {voltage}")

        elif channel_name == "A1":
            # Flush the multiplexer ghost charge
            _ = self.chan1.voltage
            time.sleep(0.0015)

            # Take the real reading
            voltage = self.v1 = self.chan1.voltage
            print(f"read A1 voltage: {voltage}")

        new_state = self.state_0 if channel_name == "A0" else self.state_1

        # Determine current zone
        if voltage < self.LOW_THRESHOLD:
            zone = "LOW"
        elif voltage > self.HIGH_THRESHOLD:
            zone = "HIGH"
        else:
            zone = "NORMAL"

        if channel_name == "A0":
            if zone != self.state_0:
                # Falling Below 2.1V
                if self.state_0 == "NORMAL" and zone == "LOW":
                    self.on_entered_edge_fx(channel_name, self.NORTH_POLE)
                    print(
                        f"[{channel_name}] FALLING EDGE: Dropped below {self.LOW_THRESHOLD}V ({voltage:.2f}V)"
                    )

                # Rising Above 2.1V (Recovering from Low)
                elif self.state_0 == "LOW" and zone == "NORMAL":
                    self.on_left_edge_fx(channel_name, self.NORTH_POLE)
                    print(
                        f"[{channel_name}] RISING EDGE: Recovered above {self.LOW_THRESHOLD}V ({voltage:.2f}V)"
                    )
                    # ACTION: e.g., Reset low-flag

                # Rising Above 2.9V
                elif self.state_0 == "NORMAL" and zone == "HIGH":
                    self.on_entered_edge_fx(channel_name, self.SOUTH_POLE)
                    print(
                        f"[{channel_name}] RISING EDGE: Spiked above {self.HIGH_THRESHOLD}V ({voltage:.2f}V)"
                    )

                # Falling Below 2.9V (Recovering from High)
                elif self.state_0 == "HIGH" and zone == "NORMAL":
                    self.on_left_edge_fx(channel_name, self.SOUTH_POLE)
                    print(
                        f"[{channel_name}] FALLING EDGE: Dropped below {self.HIGH_THRESHOLD}V ({voltage:.2f}V)"
                    )
        elif channel_name == "A1":
            if zone != self.state_1:
                # Falling Below 2.1V
                if self.state_1 == "NORMAL" and zone == "LOW":
                    self.on_entered_edge_fx(channel_name, self.NORTH_POLE)
                    print(
                        f"[{channel_name}] FALLING EDGE: Dropped below {self.LOW_THRESHOLD}V ({voltage:.2f}V)"
                    )

                # Rising Above 2.1V (Recovering from Low)
                elif self.state_1 == "LOW" and zone == "NORMAL":
                    self.on_left_edge_fx(channel_name, self.NORTH_POLE)
                    print(
                        f"[{channel_name}] RISING EDGE: Recovered above {self.LOW_THRESHOLD}V ({voltage:.2f}V)"
                    )
                    # ACTION: e.g., Reset low-flag

                # Rising Above 2.9V
                elif self.state_1 == "NORMAL" and zone == "HIGH":
                    self.on_entered_edge_fx(channel_name, self.SOUTH_POLE)
                    print(
                        f"[{channel_name}] RISING EDGE: Spiked above {self.HIGH_THRESHOLD}V ({voltage:.2f}V)"
                    )

                # Falling Below 2.9V (Recovering from High)
                elif self.state_1 == "HIGH" and zone == "NORMAL":
                    self.on_left_edge_fx(channel_name, self.SOUTH_POLE)
                    print(
                        f"[{channel_name}] FALLING EDGE: Dropped below {self.HIGH_THRESHOLD}V ({voltage:.2f}V)"
                    )

        return zone

    def start(self):
        """Starts the background ADC loop without blocking"""
        if not self.running:
            self.running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self):
        """Safely stops the thread"""
        self.running = False
        if self._thread:
            self._thread.join()
