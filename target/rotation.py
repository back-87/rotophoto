import gpiod
import time
import sys

# =========================================================
# ⚙️ SYSTEM TRANSFERS FOR YOUR EXACT PHYSICAL TABLE
# =========================================================
# Physical Pin 11 -> System 17 (Enable)
# Physical Pin 12 -> System 18 (Step Pulse)
# Physical Pin 13 -> System 27 (Direction)
# Physical Pin 15 -> System 22 (PIR Signal)
# Physical Pin 16 -> System 23 (Hall Sensor Signal)

EN_PIN   = 17   # Physical Pin 11
STEP_PIN = 18   # Physical Pin 12
DIR_PIN  = 27   # Physical Pin 13
PIR_PIN  = 22   # Physical Pin 15
HALL_PIN = 23   # Physical Pin 16

# --- MOTOR & GEOMETRY SETTINGS ---
TOTAL_STEPS = 40800     # 90 degrees at 1/8 microstepping
MAX_RUNTIME_CAP = 43000  # 95-degree absolute cap if sensor wire fails mid-run

START_DELAY = 120000    # Slow start for max torque (nanoseconds)
TARGET_DELAY = 28000    # "Decent" cruise speed (nanoseconds)
RAMP_STEPS = 12500      # Long ramp to power through the 45° wall

# --- YOUR EXACT PHYSICAL FRAMING TUNING ---
COAST_LANDSCAPE = 9100  # Steps needed to level out square at Landscape (0°)
COAST_PORTRAIT = 7450   # Steps needed to level out square at Portrait (90°)

TRANSITION_IN_PROGRESS = False
CURRENT_STATE = "HOMING_INCOMPLETE"

# Unified single kernel handle for the Pi 5's RP1 chip
req_rp1 = None

def execute_pulse(delay_ns):
    global req_rp1
    """Generates a single precise physical step pulse using the single RP1 driver."""
    req_rp1.set_value(STEP_PIN, gpiod.line.Value.ACTIVE)
    t_start = time.perf_counter_ns()
    while time.perf_counter_ns() - t_start < delay_ns: pass
    
    req_rp1.set_value(STEP_PIN, gpiod.line.Value.INACTIVE)
    t_start = time.perf_counter_ns()
    while time.perf_counter_ns() - t_start < delay_ns: pass

def run_boot_homing_sweep():
    global req_rp1
    """Safely sweeps the monitor to guarantee an absolute, perfectly level baseline."""
    print("🔍 Scanning physical sensors to determine current position...")
    
    # CASE A: Magnet is detected right away, but could be resting crookedly at the outer edge
    if req_rp1.get_value(HALL_PIN) == gpiod.line.Value.INACTIVE:
        print("🧲 Magnet detected instantly on boot! Verifying absolute alignment...")
        
        # 1. Step away toward Portrait until we clear the magnetic field entirely
        req_rp1.set_value(DIR_PIN, gpiod.line.Value(0)) 
        time.sleep(0.1)
        
        escape_steps = 0
        while req_rp1.get_value(HALL_PIN) == gpiod.line.Value.INACTIVE and escape_steps < 15000:
            execute_pulse(START_DELAY)
            escape_steps += 1
            
        print(f"🔄 Cleared magnetic edge after {escape_steps} steps. Re-entering from baseline...")
        time.sleep(0.2)
        
        # 2. Re-approach Landscape normally using your precise tracking loop
        req_rp1.set_value(DIR_PIN, gpiod.line.Value(1)) 
        time.sleep(0.1)
        
        while req_rp1.get_value(HALL_PIN) != gpiod.line.Value.INACTIVE:
            execute_pulse(START_DELAY)
            
        # 3. Apply the exact level offset
        print(f"🚗 Aligning: Executing {COAST_LANDSCAPE} final Landscape framing steps...")
        for coast_step in range(COAST_LANDSCAPE):
            curr_delay = TARGET_DELAY + ((START_DELAY - TARGET_DELAY) * coast_step // COAST_LANDSCAPE)
            execute_pulse(curr_delay)
            
        return "LANDSCAPE"

    # CASE B: No magnet detected (Panel is hanging at 45° sag OR perfectly balanced at 90° Portrait)
    print("⚠️ Position unknown. Executing single-direction fail-safe sweep toward Landscape...")
    
    # Force direction exclusively toward Landscape (INACTIVE) to prevent over-rotation
    req_rp1.set_value(DIR_PIN, gpiod.line.Value(1)) 
    time.sleep(0.1)
    
    homed_successfully = False
    MAX_HOMING_STEPS = 45333 
    
    for step_count in range(MAX_HOMING_STEPS):
        if req_rp1.get_value(HALL_PIN) == gpiod.line.Value.INACTIVE:
            print(f"🏁 Home acquired after {step_count} steps!")
            homed_successfully = True
            break
        execute_pulse(START_DELAY)

    # --- EVALUATE HOMING RESULTS FROM SWEEP ---
    if homed_successfully:
        print(f"🚗 Aligning: Executing {COAST_LANDSCAPE} final Landscape framing steps...")
        for coast_step in range(COAST_LANDSCAPE):
            curr_delay = TARGET_DELAY + ((START_DELAY - TARGET_DELAY) * coast_step // COAST_LANDSCAPE)
            execute_pulse(curr_delay)
        return "LANDSCAPE"
    else:
        print("❌ CRITICAL ERROR: 100-degree sweep failed to find the sensor!")
        print("🛑 Emergency Shutdown to protect HDMI path.")
        req_rp1.set_value(EN_PIN, gpiod.line.Value(1)) # Disable motor
        sys.exit(1)

def initialize():
    global CURRENT_STATE, TRANSITION_IN_PROGRESS
    global req_rp1

    if not TRANSITION_IN_PROGRESS:
        with gpiod.Chip('/dev/gpiochip4') as rp1_chip:

            # Output settings
            out_settings = gpiod.LineSettings(direction=gpiod.line.Direction.OUTPUT)
            
            # Input settings for sensors with external pull-downs (Hall)
            in_settings_disabled = gpiod.LineSettings(
                direction=gpiod.line.Direction.INPUT, 
                bias=gpiod.line.Bias.DISABLED
            )
            
            # Input settings for sensors needing internal pull-ups (e.g., PIR)
            in_settings_pullup = gpiod.LineSettings(
                direction=gpiod.line.Direction.INPUT, 
                bias=gpiod.line.Bias.PULL_UP
            )

            req_rp1 = rp1_chip.request_lines(
                config={
                    STEP_PIN: out_settings,
                    DIR_PIN:  out_settings,
                    EN_PIN:   out_settings,
                    # Use PULL_UP if your PIR needs it, otherwise switch to DISABLED if it has external resistors
                    PIR_PIN:  in_settings_pullup, 
                    # Use DISABLED to let your external 10k resistor do the work
                    HALL_PIN: in_settings_disabled 
                }, 
                consumer="monitor_flip"
            )

            with req_rp1:
                try:
                    print("⚡ Energizing TMC2209 driver (Holding Weight)...")
                    req_rp1.set_value(EN_PIN, gpiod.line.Value(0)) 
                    time.sleep(0.2)
                    TRANSITION_IN_PROGRESS = True
                    CURRENT_STATE = run_boot_homing_sweep()
                    TRANSITION_IN_PROGRESS = False
                    
                    print("🟢 Setup complete. Staging active loop listening for PIR...")
                    while True:
                        # Baseline polling structure for your motion sensors
                        if req_rp1.get_value(PIR_PIN) == gpiod.line.Value.ACTIVE:
                            print("🏃 PIR Triggered! Adjusting display profile...")
                        time.sleep(0.5)

                except KeyboardInterrupt:
                    print("\n🛑 Shutting down system cleanly...")
                finally:
                    req_rp1.set_value(EN_PIN, gpiod.line.Value(1)) 
                    print("👋 Holding torque released. System offline.")
    else:
        print("❌ LOGICAL ERROR: told to initialize but it seems a transition is already in progress")

def rotate_to_landscape():
    global CURRENT_STATE, TRANSITION_IN_PROGRESS
    global req_rp1

    if not TRANSITION_IN_PROGRESS:
        TRANSITION_IN_PROGRESS = True
        if CURRENT_STATE == "PORTRAIT":
            print(f"🚀 Moving panel from PORTRAIT to LANDSCAPE...")
            req_rp1.set_value(DIR_PIN, gpiod.line.Value(1)) 
            time.sleep(0.1)
            
            steps_taken = 0

            # --- FIXED DEBOUNCE FILTER VARIABLES ---
            consecutive_inactive_reads = 0
            REQUIRED_CONFIRMATIONS = 8 # Number of clean reads required to confirm real magnet presence
            
            while True:
                # Read the raw physical sensor state
                sensor_now = req_rp1.get_value(HALL_PIN)
                
                if sensor_now == gpiod.line.Value.INACTIVE:
                    consecutive_inactive_reads += 1
                else:
                    consecutive_inactive_reads = 0 # Instantly reset counter if it was just a noise glitch
                
                # Only break the loop if the sensor is consistently INACTIVE
                if consecutive_inactive_reads >= REQUIRED_CONFIRMATIONS:
                    break

                # 1. Acceleration Phase (First 12,500 steps)
                if steps_taken < RAMP_STEPS:
                    curr_delay = START_DELAY - ((START_DELAY - TARGET_DELAY) * steps_taken // RAMP_STEPS)
                # 2. Maintain uniform cruise speed
                else:
                    curr_delay = TARGET_DELAY

                execute_pulse(curr_delay)
                steps_taken += 1

                if steps_taken > MAX_RUNTIME_CAP:
                    print("❌ EMERGENCY ABORT: Landscape sensor missed! Hard stopping.")
                    req_rp1.set_value(EN_PIN, gpiod.line.Value(1))
                    sys.exit(1)

            print(f"🚗 Aligning after {steps_taken} steps because pin is {req_rp1.get_value(HALL_PIN)}. Executing {COAST_LANDSCAPE} final Landscape framing steps...")
            for coast_step in range(COAST_LANDSCAPE):
                curr_delay = TARGET_DELAY + ((START_DELAY - TARGET_DELAY) * coast_step // COAST_LANDSCAPE)
                execute_pulse(curr_delay)
            CURRENT_STATE = "LANDSCAPE"
            print(f"🏁 Rotation Complete! Locked cleanly at {CURRENT_STATE}.")
            TRANSITION_IN_PROGRESS = False
        else:
            print("❌ LOGICAL ERROR: told to rotate to LANDSCAPE, panel appears to already be in LANDSCAPE")
            TRANSITION_IN_PROGRESS = False
    else:
        print("❌ LOGICAL ERROR: told to rotate to landscape but it seems a transition is already in progress")

def rotate_to_portrait():
    global CURRENT_STATE, TRANSITION_IN_PROGRESS
    global req_rp1

    if not TRANSITION_IN_PROGRESS:
        TRANSITION_IN_PROGRESS = True
        if CURRENT_STATE == "LANDSCAPE":
            print(f"🚀 Moving panel from LANDSCAPE to PORTRAIT...")
            req_rp1.set_value(DIR_PIN, gpiod.line.Value(0)) 
            time.sleep(0.1)
            
            for i in range(TOTAL_STEPS):
                if i < RAMP_STEPS:
                    curr_delay = START_DELAY - ((START_DELAY - TARGET_DELAY) * i // RAMP_STEPS)
                elif i > (TOTAL_STEPS - RAMP_STEPS):
                    j = i - (TOTAL_STEPS - RAMP_STEPS)
                    curr_delay = TARGET_DELAY + ((START_DELAY - TARGET_DELAY) * j // RAMP_STEPS)
                else:
                    curr_delay = TARGET_DELAY
                
                execute_pulse(curr_delay)
            CURRENT_STATE = "PORTRAIT"
            print(f"🏁 Rotation Complete! Locked cleanly at {CURRENT_STATE}.")
            TRANSITION_IN_PROGRESS = False
        else:
            print("❌ LOGICAL ERROR: told to rotate to PORTRAIT, panel appears to already be in PORTRAIT")
            TRANSITION_IN_PROGRESS = False
    else:
        print("❌ LOGICAL ERROR: told to rotate to portrait but it seems a transition is already in progress")
