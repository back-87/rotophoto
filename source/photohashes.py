from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os
import hashlib
import config
import threading
from pathlib import Path

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


def hash_file(filepath):
    with open(filepath, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def build_hash_db(directory):
    base_path = Path(directory)
    temp_photo_db = {}
    temp_reverse_db = {}

    for item in base_path.iterdir():
        # Check if it's a file AND if the extension matches our set
        if item.is_file() and item.suffix.lower() in config.IMAGE_EXTENSIONS:
            filepath = str(item)
            file_hash = hash_file(filepath)
            
            temp_photo_db[file_hash] = filepath
            temp_reverse_db[filepath] = file_hash

    global photo_hash_db, reverse_hash_db
    photo_hash_db = temp_photo_db
    reverse_hash_db = temp_reverse_db
    print(f"DB rebuilt: {len(photo_hash_db)} images found.")

def handle_event(event):
    global debounce_timer

    interesting_events = ['modified', 'created', 'moved', 'deleted']
    if not event.is_directory and event.event_type in interesting_events:

        if debounce_timer is not None:
            debounce_timer.cancel()

        debounce_timer = threading.Timer(1.0, build_hash_db, args=[config.ALBUM_DIRECTORY])
        debounce_timer.start()




