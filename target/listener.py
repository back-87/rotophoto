#allow other files to import this and not wind up with a fresh instance, kinda singleton-esque
import sys
if __name__ == '__main__' and 'target.listener' not in sys.modules:
    sys.modules['target.listener'] = sys.modules['__main__']

from flask import Flask, request, jsonify
from pathlib import Path
import config
from target import grabphoto
from target import rotation
from target import pir_sleep
from target import button_control
from target import enclosure_fan_control
import subprocess
import time
import os
import threading
import signal
import socket
import shutil
import json
import datetime
import hashlib
import paho.mqtt.client as mqtt
from PIL import Image, ImageFont, ImageDraw


app = Flask(__name__)

viewer_process = None
no_fade_next_photo_change = False #used to skip transitions to get a quick replacement (hopefully next to instant) if the next or previous control buttons are pressed
mqtt_client = None
PENDING_DESTINATION_PATH = None
PENDING_DESTINATION_ORIENTATION = None
LAST_OVERLAYED_IMAGE_HASH = None
LAST_RECEIVED_IMAGE_HASH = None
LAST_STAMPED_STRING_LEN = 0


def start_viewer_once():
    print('🔄 Automated Pipeline: Launching picframe viewer process...')
    global viewer_process, mqtt_client
    
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

    mqtt_client = mqtt.Client()
    mqtt_client.connect("127.0.0.1", 1883, 60)
    mqtt_client.on_message = on_message
    mqtt_client.subscribe("picframe/#") 
    mqtt_client.subscribe("homeassistant/sensor/picframe_image/#")
    mqtt_client.loop_start() 
    mqtt_client.publish("picframe/fade_time", config.PHOTO_FADE_TIME)
    
def draw_date_location_overlay_on_current_image(text_string):
    global LAST_RECEIVED_IMAGE_HASH, LAST_OVERLAYED_IMAGE_HASH, LAST_STAMPED_STRING_LEN
    
    incoming_len = len(text_string)
    
    #4kBlack.jpg has the year set to 1987 as a flag to skip overlaying attributes
    if "1987" in text_string:
        return 

    if LAST_RECEIVED_IMAGE_HASH == LAST_OVERLAYED_IMAGE_HASH:
        print(f"DEUBG LAST_OVERLAYED_IMAGE_HASH {LAST_OVERLAYED_IMAGE_HASH}  *did* equal current_file_hash: {LAST_RECEIVED_IMAGE_HASH}")
        if incoming_len <= LAST_STAMPED_STRING_LEN:
            return 
            
    else:
        print(f"DEUBG LAST_OVERLAYED_IMAGE_HASH {LAST_OVERLAYED_IMAGE_HASH}  did *not* equal current_file_hash: {LAST_RECEIVED_IMAGE_HASH}")
        LAST_OVERLAYED_IMAGE_HASH = LAST_RECEIVED_IMAGE_HASH
        print(f"DEUBG LAST_OVERLAYED_IMAGE_HASH Now set to: {LAST_RECEIVED_IMAGE_HASH} ")
        LAST_STAMPED_STRING_LEN = 0

    with Image.open(config.ACTIVE_PATH) as image_object:
        LAST_STAMPED_STRING_LEN = incoming_len
        exif_data = image_object.info.get('exif')
        if exif_data is None:
            return

        target_orientation = rotation.peek_last_received_rotation_instruction()

        # 📏 Set your maximum safe canvas width for Portrait mode
        MAX_PORTRAIT_WIDTH = 2160 - 160  # 2160px minus 80px side padding on each edge
        
        # Start at your default crisp target font size
        font_size = 42
        
        # Run a dynamic scaling loop to automatically compress long location strings
        while True:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except IOError:
                font = ImageFont.load_default()
                break # Default font cannot be resized, break early to prevent infinite loops

            # Measure the bounding box at the current font size
            bbox = font.getbbox(text_string)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # 🛠️ THE RULE: If we are in Portrait and the text is wider than the screen, shrink it!
            if target_orientation == "PORTRAIT" and text_width > MAX_PORTRAIT_WIDTH:
                font_size -= 2 # Step down by 2 points and recalculate
                if font_size < 20: # Floor limit safety cap so text never becomes microscopic
                    break
            else:
                break # Text fits safely within boundaries, exit loop!

        bbox = font.getbbox(text_string)
        text_width = bbox[2] - bbox[0]   # Right minus Left [1]
        text_height = bbox[3] - bbox[1]  # Bottom minus Top [1

        padding = 20

        if target_orientation == "PORTRAIT":
            # 🌅 Restored your exact vertical coordinate baseline from before:
            text_x = image_object.width - 120 
            text_y = image_object.height - text_width - 80                      

            box_x1 = text_x - padding
            box_y1 = text_y - padding
            box_x2 = text_x + text_height + padding 
            box_y2 = text_y + text_width + padding
        else:
            text_x = 80
            text_y = image_object.height - 120

            box_x1 = text_x - padding
            box_y1 = text_y - padding
            box_x2 = text_x + text_width + padding
            box_y2 = text_y + text_height + padding

        overlay = Image.new("RGBA", image_object.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle([box_x1, box_y1, box_x2, box_y2], fill=(0, 0, 0, 102))

        final_img = image_object.convert("RGBA")
        final_img = Image.alpha_composite(final_img, overlay)
        final_draw = ImageDraw.Draw(final_img)

        if target_orientation == "PORTRAIT":
            text_canvas = Image.new("RGBA", (text_width + (padding * 2), text_height + (padding * 2)), (0, 0, 0, 0))
            canvas_draw = ImageDraw.Draw(text_canvas)
            canvas_draw.text((padding, padding), text_string, font=font, fill=(255, 255, 255, 255))
            
            # 🔄 FIX: Changed from ROTATE_270 to ROTATE_90 to flip the characters 180° 
            # and align them right-side up against the physical room floor.
            rotated_text_layer = text_canvas.transpose(Image.Transpose.ROTATE_90)
            final_img.paste(rotated_text_layer, (box_x1, box_y1), rotated_text_layer)
        else:
            final_draw.text((text_x, text_y), text_string, font=font, fill=(255, 255, 255, 255))

        final_img = final_img.convert("RGB")
        final_img.save(os.path.join(config.ACTIVE_DIR, "temp_overlayed.jpg"), "JPEG", quality=95, exif=exif_data)
        mqtt_client.publish("picframe/fade_time", 0.0)
        if not no_fade_next_photo_change:
            os.replace(os.path.join(config.ACTIVE_DIR, "temp_overlayed.jpg"), os.path.join(config.ACTIVE_PATH))
        else:
            os.remove(os.path.join(config.ACTIVE_DIR, "temp_overlayed.jpg"))
        mqtt_client.publish("picframe/fade_time", config.PHOTO_FADE_TIME)


def on_message(client, userdata, msg):
    global no_fade_next_photo_change, PENDING_DESTINATION_PATH, PENDING_DESTINATION_ORIENTATION
    # Check if the topic matches and we are actively waiting for a fast skip
    if msg.topic == "homeassistant/sensor/picframe_image/state" and no_fade_next_photo_change:
        if no_fade_next_photo_change and PENDING_DESTINATION_PATH is not None:
            print("🎯 Screen is confirmed PITCH BLACK. Launching physical rotation loop...")
            
            # 1. Fire the stepper motor queue via your existing safe functions
            if PENDING_DESTINATION_ORIENTATION == "portrait":
                rotation.rotate_to_portrait()
            else:
                rotation.rotate_to_landscape()
            
            time.sleep(config.ROTATION_DURATION)
            # 2. The frame is turning mid-air. Now trigger the processing of the real photo file!
            # We call display_local_image again, but now the physical rotation.CURRENT_STATE 
            # will match, bypassing the black transition block and writing the real pixels!
            no_fade_next_photo_change = False
            display_local_image(PENDING_DESTINATION_PATH, PENDING_DESTINATION_ORIENTATION, LAST_RECEIVED_IMAGE_HASH)
            # 3. Clear our temporary target cache tracking variables
            PENDING_DESTINATION_PATH = None
            PENDING_DESTINATION_ORIENTATION = None
        else:
            print("🎯 Picframe confirmed image swap! Restoring default fade...")
            mqtt_client.publish("picframe/fade_time", config.PHOTO_FADE_TIME)
            no_fade_next_photo_change = False
    elif msg.topic == "homeassistant/sensor/picframe_image/attributes": #apply our own text overlay using Pillow so it's oriented correctly
        date_str = None
        location_str = None
        m_decode = str(msg.payload.decode("utf-8", "ignore"))
        try:
            m_in = json.loads(m_decode)
            date_str = datetime.datetime.fromtimestamp(m_in["EXIF DateTimeOriginal"]).strftime("%B %e, %Y")
            location_str = m_in["location"]
            overlay_text = (("" if location_str is None else f"{location_str}. ") + ("" if date_str is None else date_str))
            draw_date_location_overlay_on_current_image(overlay_text)
            print(f"Overlay text: {overlay_text}")
        except json.JSONDecodeError:
            print("Payload is not valid JSON")

def display_local_image(path, orientation, post_req_hash):
    global current_orientation, no_fade_next_photo_change,PENDING_DESTINATION_PATH, PENDING_DESTINATION_ORIENTATION,LAST_RECEIVED_IMAGE_HASH
    rotation_will_happen = False
    no_fade_next_was_used = False
    STATIC_TARGET = os.path.join(config.ACTIVE_DIR, "temp_current.jpg")
    
    LAST_RECEIVED_IMAGE_HASH = post_req_hash
    try:
        # 1. VERIFY FILE AND GENERATE CLEAN ENVIRONMENT BOUNDS
        if not os.path.exists(path):
            print(f"⚠️ Error: File {path} not found!")
            return
        os.makedirs(config.ACTIVE_DIR, exist_ok=True)

        if orientation.upper() != rotation.CURRENT_STATE and PENDING_DESTINATION_PATH is None:
            print("🎬 Step 1: Initiating transition to black before hardware swing...")
            
            # Drop the fade time to zero so it cuts/snaps to black instantly
            no_fade_next_photo_change = True
            mqtt_client.publish("picframe/fade_time", "0.0")

            # Cache the actual destination details so our background thread knows what to load next
            PENDING_DESTINATION_PATH = path
            PENDING_DESTINATION_ORIENTATION = orientation

            # Perform your atomic replace with the black asset
            MODULE_DIR = Path(__file__).resolve().parent
            BLACK_IMG_SRC = os.path.join(MODULE_DIR, "4kBlack.jpg")
            shutil.copy2(BLACK_IMG_SRC, os.path.join(MODULE_DIR, "4kBlackCopy.jpg"))
            os.replace(os.path.join(MODULE_DIR, "4kBlackCopy.jpg"), os.path.join(config.ACTIVE_PATH))

            return # Exit! We halt execution completely until the black image lands.
        else:
            if no_fade_next_photo_change:
                no_fade_next_was_used = True
                print(f"display_local_image: istener.no_fade_next_photo_change is set")
                mqtt_client.publish("picframe/fade_time", "0.0")
                if orientation == "portrait": 
                    rotation.rotate_to_portrait()
                else: # Landscape
                    rotation.rotate_to_landscape()



        # 3. WRITE THE IMAGE FILES TO DISK (This instantly kicks off the mid-air crossfade!)
        with Image.open(path) as img:
            if orientation == "portrait": # Portrait
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

        os.replace(config.ACTIVE_DIR + "/temp_current.jpg", config.ACTIVE_PATH)
        print("Image replaced to current.jpg")

    except Exception as e:
        print(f"⚠️ Automation Control Error: {e}")

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
        display_local_image(local_path,target_orientation, hash)
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

    enclosure_fan_control.stop_pwm()

    rotation.cleanup();
    print("Motor hold released...")

    if mqtt_client:
        mqtt_client.disconnect()

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


if __name__ == '__main__':
    enclosure_fan_control.set_half_duty_cycle()
    rotation_thread = threading.Thread(target=rotation.initialize, daemon=True)
    rotation_thread.start()
    signal.signal(signal.SIGINT, clean_and_exit)
    signal.signal(signal.SIGTERM, clean_and_exit)
    start_viewer_once()
    while not getattr(rotation, 'req_rp1', None):
        time.sleep(0.1)
    pir_sleep.SCREEN_IS_AWAKE = False #the screen might be already awake, but just set this boolean so it tries to wake it in case it's not
    pir_sleep.wake_screen()
    pir_thread = threading.Thread(target=pir_sleep.pir_monitor_loop, daemon=True, args=[rotation.req_rp1,])
    pir_thread.start()
    button_control_thread = threading.Thread(target=button_control.handle_inputs, daemon=True)
    button_control_thread.start()
    app.run(host='0.0.0.0', port=config.LISTEN_PORT)
