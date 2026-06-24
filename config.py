LINGER_TIME_PER_PHOTO = 20.0 #how long to display each photo
GROUP_BY_ORIENTATION = 0 #if it's desirable to lessen orientation, the photos can be displayed as all landscape first (1) or all portrait first (2)
ALBUM_DIRECTORY = "/mnt/main_storage/auto_rotate_current_album" #all [IMAGE_EXTENSIONS] photos in this directory will be displayed 
SOURCE_IP = "10.10.9.1"
TARGET_IP = "10.10.9.52"
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

SLEEP_TIMEOUT_SECONDS = 1200  # 20 minutes of no motion before sleep

MONITOR_LANDSCAPE_WIDTH = 3840
MONITOR_LANDSCAPE_HEIGHT = 2160 

PHOTO_FADE_TIME = 2.0

BUTTON_CHIP = 0
BUTTON_PREV_PIN = 24
BUTTON_NEXT_PIN = 25

ROTATION_DURATION = 5.6

PIR_CHIP = 4
PIR_PIN = 22  # Change to your actual PIR signal pin

LISTEN_PORT = 4207 #the port on which the target listens for "display this photo" *AND* the port on which the source listens on for "GET this photo"

TARGET_PHOTO_CACHE_PATH = "/home/back/photocache"
ACTIVE_DIR = "/home/back/photocache/active_view"
ACTIVE_PATH = ACTIVE_DIR + "/current.jpg"
TARGET_MAX_CACHE_GB = 200 #256GB SD Card, 225 free at the time of writing, going with 200GB for cache, adjust as necessary
TARGET_CACHE_TRIM_SIZE = 5 #in GB, size of oldest (last time since displayed, managed with mtime as photos are touched when shown). Will delete photos up to this size when the cache is full (greater than TARGET_MAX_CACHE_GB)