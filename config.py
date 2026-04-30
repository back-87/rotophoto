LINGER_TIME_PER_PHOTO = 20 #how long to display each photo
GROUP_BY_ORIENTATION = 0 #if it's desirable to lessen orientation, the photos can be displayed as all landscape first (1) or all portrait first (2)
ALBUM_DIRECTORY = "/mnt/main_storage/auto_rotate_current_album" #all [IMAGE_EXTENSIONS] photos in this directory will be displayed 
SOURCE_IP = "10.10.9.1"
TARGET_IP = "10.10.9.52"
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

class Orientation:
    LANDSCAPE = 1
    PORTRAIT  = 2

SLEEP_TIMEOUT_SECONDS = 1200  # 20 minutes of no motion before sleep

MONITOR_LANDSCAPE_WIDTH = 3840
MONITOR_LANDSCAPE_HEIGHT = 2160 
#MONITOR_LANDSCAPE_WIDTH = 1920
#MONITOR_LANDSCAPE_HEIGHT = 1080 
# ^^ obviously these are swapped for conversion if the image is portrait

PIR_CHIP = 0
PIR_PIN = 6  # Change to your actual PIR signal pin

LISTEN_PORT = 4207 #the port on which the target listens for "display this photo" *AND* the port on which the source listens on for "GET this photo"

PHOTO_TRANSITION_TIME = 6 #in seconds, this should probably match the time it takes for the monitor to rotate 90 degrees. The plan is to do a fade from the current to the next photo, or something

TARGET_PHOTO_CACHE_PATH = "/home/biqu/photocache"
TARGET_MAX_CACHE_GB = 200 #256GB SD Card, 225 free at the time of writing, going with 200GB for cache, adjust as necessary
TARGET_CACHE_TRIM_SIZE = 5 #in GB, size of oldest (last time since displayed, managed with mtime as photos are touched when shown). Will delete photos up to this size when the cache is full (greater than TARGET_MAX_CACHE_GB)