import threading
import time
import subprocess
import gpiod
import config
from target import rotation


SCREEN_IS_AWAKE = True
last_motion_time = time.time()

def wake_screen():
    global SCREEN_IS_AWAKE
    if not SCREEN_IS_AWAKE:
        print("🏃 Motion detected! Waking up 32\" monitor...")
        # Force the HDMI line back on to your stable resolution
        subprocess.run(["env", "DISPLAY=:0", "xrandr", "--output", "HDMI-1", "--mode", f"{config.MONITOR_LANDSCAPE_WIDTH}x{config.MONITOR_LANDSCAPE_HEIGHT}"])
        SCREEN_IS_AWAKE = True

def sleep_screen():
    global SCREEN_IS_AWAKE
    if SCREEN_IS_AWAKE:
        print("💤 Room is quiet. Sending monitor to power-saving mode...")
        # Forcibly shut down the HDMI clock pipeline to drop the monitor to sleep
        subprocess.run(["env", "DISPLAY=:0", "xrandr", "--output", "HDMI-1", "--off"])
        SCREEN_IS_AWAKE = False

def pir_monitor_loop():
    global last_motion_time
    print("👀 PIR Motion Monitor Activated Background Thread...")
    
    with gpiod.Chip(f"/dev/gpiochip{config.PIR_CHIP}") as chip:
        # 1. Define modern line settings for a basic digital input
        pir_settings = gpiod.LineSettings(
            direction=gpiod.line.Direction.INPUT
        )
        
        # 2. Request the specific line offset from the chip
        req_pir = chip.request_lines(
            config={config.PIR_PIN: pir_settings}, 
            consumer="pir_fake_sleep"
        )
    
        while True:
            # Read the raw sensor state (1 = Motion, 0 = Quiet)
            # Note: If your PIR is active-low, swap this to gpiod.line.Value.INACTIVE
            if not rotation.TRANSITION_IN_PROGRESS:
                current_state = req_pir.get_value(config.PIR_PIN)
                current_time = time.time()
                if current_state == gpiod.line.Value.ACTIVE:
                    last_motion_time = time.time()
                    wake_screen()
                else:
                    # Check if the quiet time has exceeded your timeout cap
                    if time.time() - last_motion_time > config.SLEEP_TIMEOUT_SECONDS:
                        sleep_screen()
                    
            time.sleep(0.5) # Poll twice a second to keep CPU overhead near 0%