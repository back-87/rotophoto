import gpiod
import time
import sys
import threading
import queue
import config as local_config
from target.ADC_Monitor import ADC_Monitor

if __name__ == "__main__" and "target.rotation" not in sys.modules:
    sys.modules["target.rotation"] = sys.modules["__main__"]

# --- MOTOR & GEOMETRY SETTINGS ---
TOTAL_STEPS = 40800  # 90 degrees at 1/8 microstepping
MAX_RUNTIME_CAP = 43000  # 95-degree absolute cap if sensor wire fails mid-run

START_DELAY = 120000  # Slow start for max torque (nanoseconds)
TARGET_DELAY = 28000  # "Decent" cruise speed (nanoseconds)
RAMP_STEPS = 12500  # Long ramp to power through the 45° wall

# --- NEW SAFE HOMING SPEEDS FOR 3-SCREW SURVIVAL ---
HOMING_TARGET_DELAY = (
    60000  # Safe, capped top speed for the short framing burst (2x slower than cruise)
)

# --- YOUR EXACT PHYSICAL FRAMING TUNING ---
COAST_LANDSCAPE = 9100  # Steps needed to level out square at Landscape (0°)
COAST_PORTRAIT = 7450  # Steps needed to level out square at Portrait (90°)

TRANSITION_IN_PROGRESS = False
CURRENT_STATE = "HOMING_INCOMPLETE"
rotation_queue = queue.LifoQueue()

# --- DIRECTION FOR LEGIBILITY ---
CLOCKWISE = gpiod.line.Value(0)
COUNTER_CLOCKWISE = gpiod.line.Value(1)

req_rp1 = None
rp1_chip = None
adc_monitor = ADC_Monitor()


def execute_pulse(delay_ns):
    global req_rp1

    # 1. Pulse HIGH
    req_rp1.set_value(local_config.MOTOR_STEP_PIN, gpiod.line.Value.ACTIVE)
    t_start = time.perf_counter_ns()
    while time.perf_counter_ns() - t_start < delay_ns:
        pass

    # 2. Pulse LOW
    req_rp1.set_value(local_config.MOTOR_STEP_PIN, gpiod.line.Value.INACTIVE)
    t_start = time.perf_counter_ns()

    # CRITICAL FIX: The driver chip gates require this exact rest window
    # to discharge down to 0V before the next loop iteration spikes them!
    while time.perf_counter_ns() - t_start < delay_ns:
        pass


def run_boot_homing_sweep():
    """
    global req_rp1
    #Safely sweeps the monitor to guarantee an absolute, perfectly level baseline.

    print("🔍 Scanning physical sensors to determine current position...")
    # CASE A: Magnet is detected right away, but could be resting crookedly at the outer edge
    if rotation_sensor_landscape.is_triggered:
        print("🧲 Magnet detected instantly on boot! Verifying absolute alignment...")

        # 1. Step away toward Portrait until we clear the magnetic field entirely
        req_rp1.set_value(local_config.MOTOR_DIR_PIN, gpiod.line.Value(0))
        time.sleep(0.1)

        escape_steps = 0
        while rotation_sensor_landscape.is_triggered and escape_steps < 15000:
            execute_pulse(START_DELAY)
            escape_steps += 1

        print(f"🔄 Cleared magnetic edge after {escape_steps} steps. Re-entering from baseline...")
        time.sleep(0.2)

        # 2. Re-approach Landscape normally using your precise tracking loop
        req_rp1.set_value(local_config.MOTOR_DIR_PIN, gpiod.line.Value(1))
        time.sleep(0.1)

        while not rotation_sensor_landscape.is_triggered:
            execute_pulse(START_DELAY)

        # 3. Apply the exact level offset with a true, gentle acceleration ramp
        print(f"🚗 Aligning: Executing {COAST_LANDSCAPE} final Landscape framing steps...")
        for coast_step in range(COAST_LANDSCAPE):
            # True acceleration: Starts at START_DELAY (slow) and ramps smoothly down to HOMING_TARGET_DELAY (medium)
            curr_delay = START_DELAY - ((START_DELAY - HOMING_TARGET_DELAY) * coast_step // COAST_LANDSCAPE)
            execute_pulse(curr_delay)

        return "LANDSCAPE"

    # CASE B: No magnet detected (Panel is hanging at 45° sag OR perfectly balanced at 90° Portrait)
    print("⚠️ Position unknown. Executing single-direction fail-safe sweep toward Landscape...")

    # Force direction exclusively toward Landscape (INACTIVE) to prevent over-rotation
    req_rp1.set_value(local_config.MOTOR_DIR_PIN, gpiod.line.Value(1))
    time.sleep(0.1)

    homed_successfully = False
    MAX_HOMING_STEPS = 45333

    for step_count in range(MAX_HOMING_STEPS):
        if rotation_sensor_landscape.is_triggered:
            print(f"🏁 Home acquired after {step_count} steps!")
            homed_successfully = True
            break
        execute_pulse(START_DELAY)

    # --- EVALUATE HOMING RESULTS FROM SWEEP ---
    if homed_successfully:
        print(f"🚗 Aligning: Executing {COAST_LANDSCAPE} final Landscape framing steps...")
        for coast_step in range(COAST_LANDSCAPE):
            # True acceleration: Starts at START_DELAY (slow) and ramps smoothly down to HOMING_TARGET_DELAY (medium)
            curr_delay = START_DELAY - ((START_DELAY - HOMING_TARGET_DELAY) * coast_step // COAST_LANDSCAPE)
            execute_pulse(curr_delay)
        return "LANDSCAPE"
    else:
        print("❌ CRITICAL ERROR: 100-degree sweep failed to find the sensor!")
        print("🛑 Emergency Shutdown to protect HDMI path.")
        req_rp1.set_value(local_config.MOTOR_EN_PIN, gpiod.line.Value(1)) # Disable motor
        sys.exit(1)
    """


def initialize():
    global rotation_queue, TRANSITION_IN_PROGRESS, CURRENT_STATE
    global req_rp1, rp1_chip

    adc_monitor.on_entered_edge_fx = on_entered_edge
    adc_monitor.on_left_edge_fx = on_left_edge
    adc_monitor.start()

    if not TRANSITION_IN_PROGRESS:
        rp1_chip = gpiod.Chip("/dev/gpiochip4")

        # Output settings
        out_settings = gpiod.LineSettings(direction=gpiod.line.Direction.OUTPUT)

        req_rp1 = rp1_chip.request_lines(
            config={
                local_config.MOTOR_STEP_PIN: out_settings,
                local_config.MOTOR_DIR_PIN: out_settings,
                local_config.MOTOR_EN_PIN: out_settings,
            },
            consumer="monitor_flip",
        )
        TRANSITION_IN_PROGRESS = True
        try:
            print(" Energizing TMC2209 driver (Holding Weight)...")
            req_rp1.set_value(local_config.MOTOR_EN_PIN, gpiod.line.Value(0))
            time.sleep(0.2)

            CURRENT_STATE = run_boot_homing_sweep()

            TRANSITION_IN_PROGRESS = False

            while True:
                last_received_rotation_instruction = None
                try:
                    last_received_rotation_instruction = rotation_queue.get_nowait()
                except queue.Empty:
                    time.sleep(1.1)

                if last_received_rotation_instruction is not None:
                    rotation_queue = (
                        queue.LifoQueue()
                    )  # not interested in stale rotation requests, discard them
                    stepper_interaction(last_received_rotation_instruction)

        except KeyboardInterrupt:
            print("\n🛑 Shutting down system cleanly...")
            eq_rp1.set_value(local_config.MOTOR_EN_PIN, gpiod.line.Value(1))
            print("👋  Holding torque released. System offline.")

    else:
        print(
            "❌ LOGICAL ERROR: told to initialize but it seems a transition is already in progress"
        )


def on_entered_edge(analog_channel, magnet_polarity):
    if analog_channel == "A0":
        if magnet_polarity == ADC_Monitor.SOUTH_POLE:
            print("ON ENTERED EDGE OF **SAFETY** beyond portrait")
        else:
            print("ON ENTERED EDGE OF **SAFETY** beyond landscape")
    elif analog_channel == "A1":
        if magnet_polarity == ADC_Monitor.NORTH_POLE:
            print("ON ENTERED EDGE OF rotation magnet portrait")
        else:
            print("ON ENTERED EDGE OF rotation magnet landscape")


def on_left_edge(analog_channel, magnet_polarity):
    if analog_channel == "A0":
        if magnet_polarity == ADC_Monitor.SOUTH_POLE:
            print("ON LEFT EDGE OF **SAFETY** beyond portrait")
        else:
            print("ON LEFT EDGE OF **SAFETY** beyond landscape")
    elif analog_channel == "A1":
        if magnet_polarity == ADC_Monitor.NORTH_POLE:
            print("ON LEFT EDGE OF rotation magnet portrait")
        else:
            print("ON LEFT EDGE OF rotation magnet landscape")


def peek_last_received_rotation_instruction():
    if CURRENT_STATE is None:
        return "UNSET"

    if rotation_queue is not None and not rotation_queue.empty():
        with rotation_queue.mutex:
            return rotation_queue.queue[-1].upper()  # Return target in flight

    # 🏁 FALLBACK: If the queue is empty, the system is resting!
    # The active display matches the physical orientation perfectly.
    return CURRENT_STATE.upper()


def rotate_to_landscape():
    rotation_queue.put_nowait("LANDSCAPE")
    print(
        f"rotate landscape called, rotation queue contents: {list(reversed(rotation_queue.queue))}"
    )


def rotate_to_portrait():
    rotation_queue.put_nowait("PORTRAIT")
    print(
        f"rotate portrait called, rotation queue contents: {list(reversed(rotation_queue.queue))} id of queue: {id(rotation_queue)}"
    )


def cleanup():
    req_rp1.set_value(local_config.MOTOR_EN_PIN, gpiod.line.Value(1))  # Disable motor


if __name__ == "__main__":
    initialize()
