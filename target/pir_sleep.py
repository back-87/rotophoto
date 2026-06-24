import threading
import time
import subprocess
import os
import gpiod
import config
from target import rotation


SCREEN_IS_AWAKE = True
last_motion_time = time.time()

def wake_screen():
    global SCREEN_IS_AWAKE
    if not SCREEN_IS_AWAKE:
        print("🏃 Motion detected! Energizing 32\" monitor via xrandr...")
        try:
            # 🛠️ Simply pass the X11 DISPLAY target in the environment dict
            env = {"DISPLAY": ":0"}
            subprocess.run(["xrandr", "--output", "HDMI-1", "--auto"], check=True, env=env)
            SCREEN_IS_AWAKE = True
            print("🟢 Monitor is fully energized.")
        except Exception as e:
            print(f"⚠️ Wake failed: {e}")

def sleep_screen():
    global SCREEN_IS_AWAKE
    if SCREEN_IS_AWAKE:
        print("💤 Room is quiet. Cutting X11 video signal to monitor...")
        try:
            env = {"DISPLAY": ":0"}
            subprocess.run(["xrandr", "--output", "HDMI-1", "--off"], check=True, env=env)
            SCREEN_IS_AWAKE = False
            print("🌙 Standby command delivered cleanly.")
        except Exception as e:
            print(f"⚠️ Sleep failed: {e}")

def pir_monitor_loop(req_pir):
    global last_motion_time
    print("👀 PIR Motion Monitor Activated Background Thread...")
    
    while True:
        # Read the raw sensor state (1 = Motion, 0 = Quiet)
        # Note: If your PIR is active-low, swap this to gpiod.line.Value.INACTIVE
        if not rotation.TRANSITION_IN_PROGRESS:
            
            current_state = req_pir.get_value(config.PIR_PIN)
            current_time = time.time()
            if current_state == gpiod.line.Value.ACTIVE:
                print("🌙 PIR saw motion, resetting sleep timer")
                last_motion_time = time.time()
                wake_screen()
            else:
                # Check if the quiet time has exceeded your timeout cap
                if time.time() - last_motion_time > config.SLEEP_TIMEOUT_SECONDS:
                    sleep_screen()
                
        time.sleep(0.5) # Poll twice a second to keep CPU overhead near 0%