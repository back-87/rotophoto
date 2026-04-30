import gpiod
import time
import sys

# --- PINS (BTT Pi 2) ---
STEP_PIN = 23  # On chip0
DIR_PIN = 0    # On chip1
EN_PIN = 1     # On chip1
HALL_PIN = 10  # On chip4

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

req_chip0 = None
req_chip1 = None
req_chip4 = None

def execute_pulse(delay_ns):
    global req_chip0, req_chip1, req_chip4
    """Generates a single precise physical step pulse using your verified chip map."""
    req_chip0.set_value(STEP_PIN, gpiod.line.Value.ACTIVE)
    t_start = time.perf_counter_ns()
    while time.perf_counter_ns() - t_start < delay_ns: pass
    
    req_chip0.set_value(STEP_PIN, gpiod.line.Value.INACTIVE)
    t_start = time.perf_counter_ns()
    while time.perf_counter_ns() - t_start < delay_ns: pass

def run_boot_homing_sweep():
    global req_chip0, req_chip1, req_chip4
    """Safely sweeps the monitor to guarantee an absolute, perfectly level baseline."""
    print("🔍 Scanning physical sensors to determine current position...")
    
    # CASE A: Magnet is detected right away, but could be resting crookedly at the outer edge
    if req_chip4.get_value(HALL_PIN) == gpiod.line.Value.INACTIVE:
        print("🧲 Magnet detected instantly on boot! Verifying absolute alignment...")
        
        # 1. Step away toward Portrait until we clear the magnetic field entirely
        req_chip1.set_value(DIR_PIN, gpiod.line.Value.ACTIVE) 
        time.sleep(0.1)
        
        escape_steps = 0
        while req_chip4.get_value(HALL_PIN) == gpiod.line.Value.INACTIVE and escape_steps < 15000:
            execute_pulse(START_DELAY)
            escape_steps += 1
            
        print(f"🔄 Cleared magnetic edge after {escape_steps} steps. Re-entering from baseline...")
        time.sleep(0.2)
        
        # 2. Re-approach Landscape normally using your precise tracking loop
        req_chip1.set_value(DIR_PIN, gpiod.line.Value.INACTIVE) 
        time.sleep(0.1)
        
        while req_chip4.get_value(HALL_PIN) != gpiod.line.Value.INACTIVE:
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
    req_chip1.set_value(DIR_PIN, gpiod.line.Value.INACTIVE) 
    time.sleep(0.1)
    
    homed_successfully = False
    
    # 45,333 steps equals ~100 degrees of travel. 
    # This safely bridges the distance if it boots completely up at Portrait (90 degrees).
    MAX_HOMING_STEPS = 45333 
    
    for step_count in range(MAX_HOMING_STEPS):
        if req_chip4.get_value(HALL_PIN) == gpiod.line.Value.INACTIVE:
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
        req_chip1.set_value(EN_PIN, gpiod.line.Value.ACTIVE) # Disable motor
        sys.exit(1)

def initialize():
    global CURRENT_STATE, TRANSITION_IN_PROGRESS
    global req_chip0, req_chip1, req_chip4

    if TRANSITION_IN_PROGRESS == False:
        with gpiod.Chip('/dev/gpiochip0') as chip0, \
             gpiod.Chip('/dev/gpiochip1') as chip1, \
             gpiod.Chip('/dev/gpiochip4') as chip4:

            out_settings = gpiod.LineSettings(direction=gpiod.line.Direction.OUTPUT)
            hall_settings = gpiod.LineSettings(direction=gpiod.line.Direction.INPUT, bias=gpiod.line.Bias.PULL_UP)

            req_chip0 = chip0.request_lines(config={STEP_PIN: out_settings}, consumer="monitor_flip")
            req_chip1 = chip1.request_lines(config={DIR_PIN: out_settings, EN_PIN: out_settings}, consumer="monitor_flip")
            req_chip4 = chip4.request_lines(config={HALL_PIN: hall_settings}, consumer="monitor_flip")

            with req_chip0, req_chip1, req_chip4:
                try:
                    print("⚡ Energizing motor driver (Holding Weight)...")
                    req_chip1.set_value(EN_PIN, gpiod.line.Value.INACTIVE) 
                    time.sleep(0.2)
                    TRANSITION_IN_PROGRESS = True
                    CURRENT_STATE = run_boot_homing_sweep()
                    TRANSITION_IN_PROGRESS = False
                    while True:
                        time.sleep(0.5) #hold forever until process ends

                except KeyboardInterrupt:
                    print("\n🛑 Shutting down system cleanly...")
                finally:
                    req_chip1.set_value(EN_PIN, gpiod.line.Value.ACTIVE) 
                    print("👋 Holding torque released. System offline.")
    else:
        print("❌ LOGICAL ERROR: told to initialize but it seems a transition is already in progress")

def rotate_to_landscape():
    global CURRENT_STATE, TRANSITION_IN_PROGRESS
    global req_chip0, req_chip1, req_chip4

    if TRANSITION_IN_PROGRESS == False:
        TRANSITION_IN_PROGRESS = True
          # --- ROTATING TO LANDSCAPE (WHILE TRUE SENSOR HUNTING) ---
        if CURRENT_STATE == "PORTRAIT":
            print(f"🚀 Moving panel from {CURRENT_STATE} to LANDSCAPE...")
            req_chip1.set_value(DIR_PIN, gpiod.line.Value.INACTIVE) 
            time.sleep(0.1)
            
            steps_taken = 0
            while req_chip4.get_value(HALL_PIN) != gpiod.line.Value.INACTIVE:
                if steps_taken < RAMP_STEPS:
                    curr_delay = START_DELAY - ((START_DELAY - TARGET_DELAY) * steps_taken // RAMP_STEPS)
                elif steps_taken > (TOTAL_STEPS - RAMP_STEPS):
                    j = steps_taken - (TOTAL_STEPS - RAMP_STEPS)
                    curr_delay = TARGET_DELAY + ((START_DELAY - TARGET_DELAY) * j // RAMP_STEPS)
                else:
                    curr_delay = TARGET_DELAY

                execute_pulse(curr_delay)
                steps_taken += 1

                if steps_taken > MAX_RUNTIME_CAP:
                    print("❌ EMERGENCY ABORT: Landscape sensor missed! Hard stopping.")
                    req_chip1.set_value(EN_PIN, gpiod.line.Value.ACTIVE)
                    sys.exit(1)

            print(f"🚗 Aligning: Executing {COAST_LANDSCAPE} final Landscape framing steps...")
            for coast_step in range(COAST_LANDSCAPE):
                curr_delay = TARGET_DELAY + ((START_DELAY - TARGET_DELAY) * coast_step // COAST_LANDSCAPE)
                execute_pulse(curr_delay)
            CURRENT_STATE = "LANDSCAPE"
            TRANSITION_IN_PROGRESS = False
        else:
            print("❌ LOGICAL ERROR: told to rotate to LANDSCAPE, panel appears to already be in LANDSCAPE")

        print(f"🏁 Rotation Complete! Locked cleanly at {CURRENT_STATE}.")
    else:
        print("❌ LOGICAL ERROR: told to rotate to landscape but it seems a transition is already in progress")

def rotate_to_portrait():
    global CURRENT_STATE, TRANSITION_IN_PROGRESS
    global req_chip0, req_chip1, req_chip4

    if TRANSITION_IN_PROGRESS == False:
        TRANSITION_IN_PROGRESS = True
        # --- ROTATING TO PORTRAIT (FIXED STEP RUN) ---
        if CURRENT_STATE == "LANDSCAPE":
            print(f"🚀 Moving panel from {CURRENT_STATE} to PORTRAIT...")
            req_chip1.set_value(DIR_PIN, gpiod.line.Value.ACTIVE) 
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
            TRANSITION_IN_PROGRESS = False
        else:
            print("❌ LOGICAL ERROR: told to rotate to PORTRAIT, panel appears to already be in PORTRAIT")
    else:
        print("❌ LOGICAL ERROR: told to rotate to portrait but it seems a transition is already in progress")


  




