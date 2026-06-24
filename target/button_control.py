import time
import gpiod
import config

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
                time.sleep(0.05)
                
                latest_a = req_prev.get_value(config.BUTTON_PREV_PIN)
                latest_b = req_next.get_value(config.BUTTON_NEXT_PIN)
                
                # Case C: Both buttons pressed together
                if latest_a == gpiod.line.Value.INACTIVE and latest_b == gpiod.line.Value.INACTIVE:
                    print("Action C: Both Buttons Pressed!")
                    while req_prev.get_value(config.BUTTON_PREV_PIN) == gpiod.line.Value.INACTIVE or req_next.get_value(config.BUTTON_NEXT_PIN) == gpiod.line.Value.INACTIVE:
                        time.sleep(0.01)
                        
                # Case A: Previous Slide Button (GPIO 24)
                elif latest_a == gpiod.line.Value.INACTIVE:
                    print("Action A: Button A (Previous Slide) Pressed!")
                    while req_prev.get_value(config.BUTTON_PREV_PIN) == gpiod.line.Value.INACTIVE:
                        time.sleep(0.01)
                        
                # Case B: Next Slide Button (GPIO 25)
                elif latest_b == gpiod.line.Value.INACTIVE:
                    print("Action B: Button B (Next Slide) Pressed!")
                    while req_next.get_value(config.BUTTON_NEXT_PIN) == gpiod.line.Value.INACTIVE:
                        time.sleep(0.01)
                        
            time.sleep(0.01) # Keep CPU thread consumption near 0%
