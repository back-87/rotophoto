import os
import shutil
from pathlib import Path
import config
import requests
from PIL import Image



def enforce_cache_limit():
    max_bytes = config.TARGET_MAX_CACHE_GB * (1024**3)
    target_bytes = (config.TARGET_MAX_CACHE_GB - config.TARGET_CACHE_TRIM_SIZE) * (1024**3)
    

    all_files = [
        f for f in Path(config.TARGET_PHOTO_CACHE_PATH).iterdir() 
        if f.is_file() and f.suffix.lower() in config.IMAGE_EXTENSIONS
     ]

    current_usage = sum(f.stat().st_size for f in all_files)
    
    if current_usage > max_bytes:
        # Sort the filtered list by modified time
        all_files.sort(key=os.path.getmtime)
        
        while current_usage > target_bytes and all_files:
            oldest = all_files.pop(0)
            size = oldest.stat().st_size
            oldest.unlink()
            current_usage -= size
            
        print(f"Cleanup finished. Current cache: {current_usage / 1024**3:.2f} GB")


def grab_photo(hash):

    #make sure we have cache space free before grabbing a photo to add to it:
    enforce_cache_limit()

    save_path = Path(config.TARGET_PHOTO_CACHE_PATH) / f"{hash}.jpg"

    try:
        source_url = f'http://{config.SOURCE_IP}:{config.LISTEN_PORT}/rotophoto/{hash}' 

        response = requests.get(source_url, stream=True, timeout=10)
        response.raise_for_status()


        temp_path = save_path.with_suffix(".tmp")
        
        with open(temp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        temp_path.replace(save_path)
        print(f"Successfully saved {hash}.jpg")
        return True

    except Exception as e:
        print(f"Failed to fetch photo {hash}: {e}")
        return False


