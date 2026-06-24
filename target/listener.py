from flask import Flask, request, jsonify
from pathlib import Path
import config
from target import grabphoto
from target import rotation
from target import pir_sleep
from target import button_control
import subprocess
import time
import os
import sys
import threading
import signal
import socket
import shutil
import json
import paho.mqtt.publish as publish
from PIL import Image


app = Flask(__name__)

viewer_process = None
current_orientation = 1

def start_viewer_once():
    print('🔄 Automated Pipeline: Launching picframe viewer process...')
    global viewer_process
    
    # Clean out the old database to ensure fresh cached files index cleanly
    DB_PATH = "/home/back/picframe_data/data/pictureframe.db3"
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print("🧹 Flushed old picframe database for a clean boot.")
        except Exception as e:
            print(f"⚠️ Could not clear DB cache: {e}")

    # Set modern X11 environment parameters for the Pi 5 desktop session
    os.environ["DISPLAY"] = ":0"
    os.environ["XAUTHORITY"] = "/home/back/.Xauthority"

    # Launch Pi3D PictureFrame natively
    cmd = [
        "picframe", 
        "/home/back/picframe_data/config/configuration.yaml"
    ]

    viewer_process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL, # Mute logs since we are in automated production mode
        stderr=subprocess.DEVNULL,
        start_new_session=True     # Detach cleanly from the Flask lifecycle
    )
    
    # Give the Pi 5 GPU context 3 seconds to fully allocate its GLX layers
    print("🟢 Viewer is alive and rendering fullscreen natively.")


def display_local_image(path, orientation):
    global current_orientation
    
    ACTIVE_DIR = "/home/back/photocache/active_view"
    STATIC_TARGET = os.path.join(ACTIVE_DIR, "current.jpg")
    
    try:
        # 1. VERIFY FILE AND GENERATE CLEAN ENVIRONMENT BOUNDS
        if not os.path.exists(path):
            print(f"⚠️ Error: File {path} not found!")
            return
        os.makedirs(ACTIVE_DIR, exist_ok=True)

        # 2. RUN SIMULTANEOUS HARDWARE STEPPER MOTOR FLIPS
        if orientation != current_orientation:
            print("🔄 Launching physical stepper motor frame rotation...")
            if orientation == 2: # Portrait
                t = threading.Thread(target=rotation.rotate_to_portrait, daemon=True)
                t.start()
            else: # Landscape
                t = threading.Thread(target=rotation.rotate_to_landscape, daemon=True)
                t.start()
            current_orientation = orientation

        # 3. WRITE THE IMAGE FILES TO DISK (This instantly kicks off the mid-air crossfade!)
        with Image.open(path) as img:
            if orientation == 2: # Portrait
                print("📐 Pre-rotating pixels 90° and saving Portrait file to disk...")
                rotated_img = img.transpose(Image.Transpose.ROTATE_90)
                exif_data = img.info.get('exif')
                if exif_data:
                    rotated_img.save(STATIC_TARGET, "JPEG", quality=95, exif=exif_data)
                else:
                    rotated_img.save(STATIC_TARGET, "JPEG", quality=95)
                shutil.copystat(path, STATIC_TARGET)
            else: # Landscape
                print("📐 Saving native Landscape file to disk...")
                shutil.copyfile(path, STATIC_TARGET)
                shutil.copystat(path, STATIC_TARGET)

        print("✅ Image saved. Picframe watchdog is handling the crossfade natively.")

    except Exception as e:
        print(f"⚠️ Automation Control Error: {e}")


            
# deprecated, not called, might be useful
def display_local_image_no_transition(path, orientation):
    print(f' displaying local image at path: {path} and orientation: {orientation}')
    cmd = ["fbi", "-T", "1", "-d", "/dev/fb0", "-a", "-1", "--noverbose", path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

@app.route('/showphoto/<hash>', methods=['POST'])
def handle_photo_display_post(hash):
    print(f'request to display photo with hash: {hash}')
    data = request.get_json()

    if data is None:
        return jsonify({"status": "error", "message": "Missing JSON body"}), 400

    print(f"Received request to show photo with data: {data}")

    target_hash = data["hash"]
    target_orientation = data['orientation']

    local_path = f"{config.TARGET_PHOTO_CACHE_PATH}/{hash}.jpg"

    if not Path(local_path).exists():
        grabphoto.grab_photo(hash)

    if pir_sleep.SCREEN_IS_AWAKE:
        display_local_image(local_path,target_orientation)
    #display_local_image_no_transition(local_path, target_orientation)
    else:
        print("Screen is NOT awake, ignoring request to display image")


    return jsonify({
        "status": "success", 
        "keys_processed": list(data.keys())
    }), 200

def clean_and_exit(signum, frame):
    cleanup()
    sys.exit(0);


def cleanup():
    global viewer_process
    print("\nCleaning up...")

    if viewer_process:
        print("🛑 Terminating picframe process...")
        viewer_process.terminate()
        try:
            # Give it 2 seconds to close gracefully
            viewer_process.wait(timeout=2)
            print("✅ Picframe stopped gracefully.")
        except subprocess.TimeoutExpired:
            print("⚠️ Graceful shutdown timed out. Force killing...")
            viewer_process.kill()
            viewer_process.wait() # Wait indefinitely for kill to finish
            print("💀 Picframe killed.")

    # No socket to remove for picframe
    os.system("stty sane")
    print("Terminal restored. Goodbye.")
    sys.exit(0)   


def pir_monitor_loop():
    global last_motion_time
    print("👀 PIR Motion Monitor Activated Background Thread...")
    
    # Initialize the input pin using gpiod
    chip = gpiod.Chip(f"gpiochip{PIR_CHIP}")
    pir_line = chip.get_line(PIR_PIN)
    pir_line.request(consumer="PIR_Sleep", type=gpiod.LINE_REQ_DIR_IN)
    
    while True:
        # Read the raw sensor state (1 = Motion, 0 = Quiet)
        # Note: If your PIR is active-low, swap this to gpiod.line.Value.INACTIVE
        if pir_line.get_value() == gpiod.line.Value.ACTIVE:
            last_motion_time = time.time()
            wake_screen()
        else:
            # Check if the quiet time has exceeded your timeout cap
            if time.time() - last_motion_time > SLEEP_TIMEOUT_SECONDS:
                sleep_screen()
                
        time.sleep(0.5) # Poll twice a second to keep CPU overhead near 0%

if __name__ == '__main__':

    rotation_thread = threading.Thread(target=rotation.initialize)
    rotation_thread.daemon = True
    rotation_thread.start()

    signal.signal(signal.SIGINT, clean_and_exit)
    signal.signal(signal.SIGTERM, clean_and_exit)
    start_viewer_once()
    pir_thread = threading.Thread(target=pir_sleep.pir_monitor_loop, daemon=True)
    pir_thread.start()
    button_control_thread = threading.Thread(target=button_control.handle_inputs, daemon=True)
    button_control_thread.start()
    app.run(host='0.0.0.0', port=config.LISTEN_PORT)
