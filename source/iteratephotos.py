# loops through photos in ALBUM_DIRECTORY and: 1) generates a hash of the current photo 2) determines orientation 3) asks the target to display the hash at the orientation
# if the target doesn't have a photo for the hash, it will hit the endpoint defined in servephotos.py to GET said photo and cache it

#allow other files to import this and not wind up with a fresh instance, kinda singleton-esque
import sys
if __name__ == '__main__' and 'source.iteratephotos' not in sys.modules:
    sys.modules['source.iteratephotos'] = sys.modules['__main__']


import time
import threading
import config
import requests
from PIL import Image
from pathlib import Path
from source import servephotos
from source import photohashes

current_photo_index = 0
is_paused = False
photo_timer = None
current_files = None

def run():
    global photo_timer
    photohashes.init()
    servephotos.standup()

    # Make sure the server is up so we don't instruct the target to display a photo 
    # and have it GET before the server is accepting connections
    time.sleep(2) 

    # Show the first photo right away, then wait for timer expiry for subsequent iterations
    show_photo_at_current_index(False) 
    photo_timer = ResettableTimer(config.LINGER_TIME_PER_PHOTO, next_photo, args=[False,])
    photo_timer.start()

    # --- KEEP MAIN THREAD ALIVE EFFICIENTLY ---
    print("Application successfully running. Press CTRL+C to exit.")
    try:
        while True:
            time.sleep(1) # Sleep 1 second at a time, taking 0% CPU
    except KeyboardInterrupt:
        print("\nShutting down rotophoto...")

def reset_timer():
    global current_photo_index, photo_timer
    if is_paused:
        print("Photo roll is paused, ignoring call to reset timer.")
    elif photo_timer is not None:
        photo_timer.reset()


def pause_unpause():
    global is_paused, current_photo_index, photo_timer
    if is_paused:
        is_paused = False
        next_photo(False)
    else: 
        is_paused = True
        if photo_timer is not None:
            photo_timer.cancel()
        else:
            print("in pause_unpause(): no photo_timer to cancel!")

def next_photo(force):
    print("call to next_photo")
    global current_photo_index

    if current_files is None or len(current_files) == 0:  # Fixed: converted .len() to len()
        print("No photos to show the next of! Doing nothing")
        reset_timer()
        return

    current_photo_index += 1
    if current_photo_index >= len(current_files):  # Fixed: added colon and fixed len()
        current_photo_index = 0

    show_photo_at_current_index(force)
    reset_timer()

def previous_photo(force):
    global current_photo_index
    if current_files is None or len(current_files) == 0:  # Fixed: converted .len to len()
        print("No photos to show the next of! Doing nothing")
        reset_timer()
        return

    current_photo_index -= 1
    if current_photo_index < 0:
        current_photo_index = len(current_files) - 1  # Fixed: converted .len() to len()

    show_photo_at_current_index(force)
    reset_timer()

def refresh_file_list():
    global current_files  # Fixed: added global keyword to allow modification
    current_files = list(photohashes.reverse_hash_db.keys())

def show_photo_at_current_index(force):
    global current_photo_index, current_files
 
    if is_paused and not force:
        print("Photo roll is paused, not sending a REST request to display a new photo. Resetting timer")
        return

    if current_files is None:
        current_files = list(photohashes.reverse_hash_db.keys())

    if not current_files:
        print("No photos found. Waiting...")
        return

    file_str = current_files[current_photo_index]
    file_path = Path(file_str)
   
    print(f"\nDisplaying photo: {file_path.name}")

    try:
        with Image.open(file_path) as img:
            width, height = img.size
            orientation = "landscape" if width > height else "portrait"
            print(f"Dimensions: {width}x{height} ({orientation})")

        photo_hash = photohashes.reverse_hash_db.get(file_str)
        print(f"Instructing target to display photo with hash: {photo_hash}")

        payload = {
            "hash": photo_hash,
            "orientation": "landscape" if width > height else "portrait" 
        }

        try:
            url = f'http://{config.TARGET_IP}:{config.LISTEN_PORT}/showphoto/{photo_hash}'
            print(f'POST to URL: {url}')
            response = requests.post(url, json=payload)
            
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.json()}")

        except Exception as e:
            print(f"Failed to connect: {e}")

        # Fixed: Removed time.sleep(config.LINGER_TIME_PER_PHOTO) to prevent double lag
        
    except (IOError, OSError) as e:
        print(f"Error opening {file_path.name}: {e}")
        return  # Fixed: changed continue to return


class ResettableTimer:
    def __init__(self, interval, function, args=None, kwargs=None):
        self.interval = interval
        self.function = function
        self.args = args or []
        self.kwargs = kwargs or {}
        self.timer = threading.Timer(self.interval, self.function, self.args, self.kwargs)

    def start(self):
        self.timer.start()

    def reset(self):
        self.timer.cancel()
        self.timer = threading.Timer(self.interval, self.function, self.args, self.kwargs)
        self.timer.start()

    def cancel(self):
        print("timer cancelled")
        self.timer.cancel()


if __name__ == '__main__':
    run()
