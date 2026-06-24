import time
import threading
import gpiod
import config
import requests
from target import listener
next_prev_lock = threading.Lock()

def handle_inputs():
    """Target function for background Thread-3 using isolated single-line PIR architecture"""
    print("🔘 Control Box Buttons Active Background Thread...")
    
    with gpiod.Chip(f"/dev/gpiochip{config.BUTTON_CHIP}") as chip:
        button_settings = gpiod.LineSettings(
            direction=gpiod.line.Direction.INPUT,
            bias=gpiod.line.Bias.PULL_UP
        )
        
        # Isolate the requests into completely separate objects just like the PIR script does
        req_prev = chip.request_lines(config={config.BUTTON_PREV_PIN: button_settings}, consumer="btn_prev")
        req_next = chip.request_lines(config={config.BUTTON_NEXT_PIN: button_settings}, consumer="btn_next")
        
        while True:
            # Read the state objects directly from their independent channels
            val_a = req_prev.get_value(config.BUTTON_PREV_PIN)
            val_b = req_next.get_value(config.BUTTON_NEXT_PIN)
            
            # Check if either button goes INACTIVE (pressed/grounded)
            if val_a == gpiod.line.Value.INACTIVE or val_b == gpiod.line.Value.INACTIVE:
                # 50ms overlap window to catch simultaneous dual-press actions
                time.sleep(0.1)
                
                latest_a = req_prev.get_value(config.BUTTON_PREV_PIN)
                latest_b = req_next.get_value(config.BUTTON_NEXT_PIN)
                

               # one (maybe both) of the button was pressed, set up a request now
                try:
                    base_url = f'http://{config.SOURCE_IP}:{config.LISTEN_PORT}/rotophoto/backchannel/' 
                    action = None  # Track if a valid action happened

                    # Case C: Both buttons pressed together
                    if latest_a == gpiod.line.Value.INACTIVE and latest_b == gpiod.line.Value.INACTIVE:
                        print("Action C: Both Buttons (pause photo roll) Pressed!")
                        while req_prev.get_value(config.BUTTON_PREV_PIN) == gpiod.line.Value.INACTIVE or req_next.get_value(config.BUTTON_NEXT_PIN) == gpiod.line.Value.INACTIVE:
                            time.sleep(0.01)
                        action = "pause"
                            
                    # Case A: Previous Slide Button (GPIO 24)
                    elif latest_a == gpiod.line.Value.INACTIVE:
                        print("Action A: Button A (Previous Slide) Pressed!")
                        listener.PENDING_DESTINATION_PATH = None
                        listener.PENDING_DESTINATION_ORIENTATION = None
                        while req_prev.get_value(config.BUTTON_PREV_PIN) == gpiod.line.Value.INACTIVE:
                            time.sleep(0.01)
                        action = "previous"
                            
                    # Case B: Next Slide Button (GPIO 25)
                    elif latest_b == gpiod.line.Value.INACTIVE:
                        print("Action B: Button B (Next Slide) Pressed!")
                        listener.PENDING_DESTINATION_PATH = None
                        listener.PENDING_DESTINATION_ORIENTATION = None
                        while req_next.get_value(config.BUTTON_NEXT_PIN) == gpiod.line.Value.INACTIVE:
                            time.sleep(0.01)
                        action = "next"

                    # ONLY send the request if a button action actually registered!
                    if action is not None:
                        source_url = base_url + action
                        response = requests.get(source_url, stream=True, timeout=10)
                        response.raise_for_status()
                        print(f"Successfully sent {source_url}")
                        
                        # Software Debounce: Ignore microsecond vibrations right after firing
                        time.sleep(0.2) 
                    else:
                        # Ghost input loop iteration; safely skip
                        pass

                except Exception as e:
                    print(f"Failed to send {source_url}: {e}")

                        
            time.sleep(0.01) # Keep CPU thread consumption near 0%
