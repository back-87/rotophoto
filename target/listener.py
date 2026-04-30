from flask import Flask, request, jsonify
from pathlib import Path
import config
from target import grabphoto
from target import rotation
from target import pir_sleep
import subprocess
import time
import os
import sys
import threading
import signal
import socket
import json


app = Flask(__name__)

viewer_process = None
current_orientation = 1

def start_viewer_once():
    print('starting viewer process once')
    global viewer_process
    

    os.environ["DISPLAY"] = ":0"
    os.environ["XAUTHORITY"] = "/home/biqu/.Xauthority"

    # Python can safely delete its own socket file natively
    if os.path.exists("/tmp/mpvsocket"):
        try:
            os.remove("/tmp/mpvsocket")
        except OSError as e:
            print(f"Warning: Could not remove old socket: {e}")


    # SET YOUR TARGET HERE: Use "1920x1080" for tonight, change to "3840x2160" tomorrow!
     
    
    print(f"🚀 Waking up HDMI transmitter and setting resolution to {config.MONITOR_LANDSCAPE_WIDTH}x{config.MONITOR_LANDSCAPE_HEIGHT}...")
    try:
        # 1. Let the hardware settle after a reboot sequence
        time.sleep(2)
        
        # 2. Lock the performance profiles back in place
        subprocess.run("echo performance | sudo tee /sys/class/devfreq/fde60000.gpu/governor", shell=True, stdout=subprocess.DEVNULL)
        subprocess.run("echo performance | sudo tee /sys/class/devfreq/dmc/governor", shell=True, stdout=subprocess.DEVNULL)

        # 3. Clean list execution to target the 4K mode safely
        subprocess.run(
            [
                "xrandr", 
                "--output", "HDMI-1", 
                "--mode", f"{config.MONITOR_LANDSCAPE_WIDTH}x{config.MONITOR_LANDSCAPE_HEIGHT}", 
                "--refresh", "24"  # Forcing 24 removes the green tint and sparkles entirely
            ],
            check=True
        )
        print("⚡ HDMI transmitter is fully energized at 4K.")
    except Exception as e:
        print(f"⚠️ Resolution switch failed: {e}")

    # Paint the base canvas black
    subprocess.run(["env", "DISPLAY=:0", "xsetroot", "-solid", "#000000"], check=False)

    # Clean MPV execution block
    cmd = [
        "/usr/bin/mpv",
        "--fs",                           
        "--screen-name=HDMI-1",           
        "--geometry=3840x2160+0+0",        # <-- FORCE MPV TO SNAP TO THE CHOSEN HARDWARE GRID
        "--vo=gpu",                        
        "--autofit-larger=100%x100%",     
        "--panscan=0.0",             
        "--video-unscaled=no",            
        "--idle=yes",
        "--no-terminal",
        "--image-display-duration=inf",
        "--reset-on-next-file=none",
        "--input-ipc-server=/tmp/mpvsocket"
    ]

    """
    cmd = [
        "/usr/bin/mpv",
        "--geometry=3840x2160",           # Lock the hardware canvas strictly to 4K
        "--video-aspect-override=16:9",   # Forces standard widescreen HDMI timings
        "--video-unscaled=no",            # Tells mpv to scale the image INSIDE the 4K box
        "--idle=yes",
        "--no-terminal",
        "--image-display-duration=inf",
        "--reset-on-next-file=none",
        "--input-ipc-server=/tmp/mpvsocket"
    ]
    """
    viewer_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    time.sleep(2)
    
    if viewer_process.poll() is not None:
        stdout, stderr = viewer_process.communicate()
        print(f"!!! MPV DIED IMMEDIATELY !!!")
        print(f"Exit Code: {viewer_process.returncode}")
        print(f"Error Output: {stderr}")
    else:
        # No chmod needed anymore since the socket is owned by biqu
        print("Viewer is alive and socket is open.")



def display_local_image(path, orientation):
    global current_orientation
    rot = 270 if orientation == 2 else 0

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2.0)
            client.connect("/tmp/mpvsocket")

            # ---------------------------------------------------------
            # 1. FADE OUT TO BLACK (Before physical rotation starts)
            # ---------------------------------------------------------
            print("🌑 Fading photo out to black...")
            # Smoothly drop contrast from 0 (normal) to -100 (solid black screen)
            for level in range(0, -101, -20):
                client.sendall(json.dumps({"command": ["set_property", "contrast", level]}).encode() + b'\n')
                client.recv(1024)
                time.sleep(0.05) # Determines fade speed (0.25 seconds total)

            # ---------------------------------------------------------
            # 2. THE BLOCKING PHYSICAL MOTOR ROTATION
            # ---------------------------------------------------------
            if current_orientation != orientation:
                print("🔄 Swapping physical frame layout...")
                if orientation == config.Orientation.LANDSCAPE:
                    rotation.rotate_to_landscape()  # Blocks until locked
                elif orientation == config.Orientation.PORTRAIT:
                    rotation.rotate_to_portrait()   # Blocks until locked

            current_orientation = orientation

            # ---------------------------------------------------------
            # 3. SWAP THE PIXELS COVERTLY WHILE SCREEN IS PITCH BLACK
            # ---------------------------------------------------------
            # Clear previous image and prep orientation rules
            client.sendall(json.dumps({"command": ["stop"]}).encode() + b'\n')
            client.recv(1024)
            time.sleep(0.1)

            client.sendall(json.dumps({"command": ["set_property", "video-rotate", rot]}).encode() + b'\n')
            client.recv(1024)

            # Load the new Nikon Z7 photo
            client.sendall(json.dumps({"command": ["loadfile", str(path), "replace"]}).encode() + b'\n')
            client.recv(1024)
            
            # ---------------------------------------------------------
            # 4. FADE IN FROM BLACK (Now that the frame is mechanically locked)
            # ---------------------------------------------------------
            print("✨ Fading new photo into view...")
            # Smoothly restore contrast back to normal 0 level
            for level in range(-100, 1, 20):
                client.sendall(json.dumps({"command": ["set_property", "contrast", level]}).encode() + b'\n')
                client.recv(1024)
                time.sleep(0.05)

            print(f"✅ Forced Swap Complete: {path}")

    except Exception as e:
        print(f"⚠️ Fade Transition IPC Error: {e}")



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
    if viewer_process:
        print("\nCleaning up mpv process...")
        viewer_process.terminate()
        try:
            viewer_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            viewer_process.kill()
    
    # Remove the stale socket cleanly without sudo
    if os.path.exists("/tmp/mpvsocket"):
        try:
            os.remove("/tmp/mpvsocket")
        except PermissionError:
            print("Permission error deleting socket file.")
        
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
    app.run(host='0.0.0.0', port=config.LISTEN_PORT)
