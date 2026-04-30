# loops through photos in ALBUM_DIRECTORY and: 1) generates a hash of the current photo 2) determines orientation 3) asks the target to display the hash at the orientation
# if the target doesn't have a photo for the hash, it will hit the endpoint defined in servephotos.py to GET said photo and cache it

import os
import time
import config
from config import Orientation
from source import servephotos
from source import photohashes
import requests
from PIL import Image
from pathlib import Path

photohashes.init()
servephotos.standup()

time.sleep(2) #make sure the server is up so we don't instruct the target to display a photo and have it GET before the server is accepting connections

while True:
    current_files = list(photohashes.reverse_hash_db.keys())

    if not current_files:
        print("No photos found. Waiting...")
        time.sleep(5)
        continue

    for file_str in current_files:
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
                "orientation": config.Orientation.LANDSCAPE if width > height else config.Orientation.PORTRAIT
            }

            try:
                url = 'http://' + config.TARGET_IP + f':{config.LISTEN_PORT}' + '/showphoto/' + photo_hash
                print(f'POST to URL: {url}')
                response = requests.post(url, json=payload)
                
                print(f"Status Code: {response.status_code}")
                print(f"Response: {response.json()}")

            except Exception as e:
                print(f"Failed to connect: {e}")

            time.sleep(config.LINGER_TIME_PER_PHOTO)
            
        except (IOError, OSError) as e:
            print(f"Error opening {file_path.name}: {e}")
            continue