from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os
import hashlib
import config
import threading
from pathlib import Path
from source import iteratephotos

photo_hash_db = {} #hash to file
reverse_hash_db = {} #file to hash
debounce_timer = None

def init():
    event_handler = FileSystemEventHandler()
    event_handler.on_any_event = handle_event
    observer = Observer()
    observer.schedule(event_handler, config.ALBUM_DIRECTORY, recursive=True)
    observer.start()
    build_hash_db(config.ALBUM_DIRECTORY)


def hash_image(filepath):
    """Reads an image in binary mode and generates a true hash based strictly on its bytes."""
    sha256_hash = hashlib.sha256()
    
    # Read the file in 64KB binary chunks to handle large 4K files efficiently
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
            
    # This returns a flawless, un-fakeable fingerprint of the literal image content
    return sha256_hash.hexdigest()

def build_hash_db(directory):
    base_path = Path(directory)
    temp_photo_db = {}
    temp_reverse_db = {}

    for item in base_path.iterdir():
        # Check if it's a file AND if the extension matches our set
        if item.is_file() and item.suffix.lower() in config.IMAGE_EXTENSIONS:
            filepath = str(item)
            file_hash = hash_image(filepath)
            
            temp_photo_db[file_hash] = filepath
            temp_reverse_db[filepath] = file_hash
            print(f"generated image hash: {file_hash}")

    global photo_hash_db, reverse_hash_db
    photo_hash_db = temp_photo_db
    reverse_hash_db = temp_reverse_db
    print(f"DB rebuilt: {len(photo_hash_db)} images found. Telling iterator to refresh its file list")
    iteratephotos.refresh_file_list()

def handle_event(event):
    global debounce_timer

    interesting_events = ['modified', 'created', 'moved', 'deleted']
    if not event.is_directory and event.event_type in interesting_events:

        if debounce_timer is not None:
            debounce_timer.cancel()

        debounce_timer = threading.Timer(1.0, build_hash_db, args=[config.ALBUM_DIRECTORY])
        debounce_timer.start()







