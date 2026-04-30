# this simply allows the target to retrieve a photo by using a GET with the photo's hash. 
# This occurs when the target is told to display a photo hash and its cache doesn't contain that hash (and the corresponding photo)

from flask import Flask, send_file
import os
import config
import threading
from source import photohashes
from PIL import Image
import io

app = Flask(__name__)


@app.route('/rotophoto/<hash>')
def serve_photo(hash):
    print("Serving file with hash: {hash}")

    file_path = photohashes.photo_hash_db[hash]

    if not file_path:
        return "Photo not found for hash", 404

    try:
        with Image.open(file_path) as img:
            target_size = (100,100)
            width, height = img.size
            print(f"SERVE Dimensions: {width}x{height}")
            if width > height:
                target_size = (config.MONITOR_LANDSCAPE_WIDTH, config.MONITOR_LANDSCAPE_HEIGHT)
            else:
                target_size = (config.MONITOR_LANDSCAPE_HEIGHT, config.MONITOR_LANDSCAPE_WIDTH) 


            try:
                with Image.open(file_path) as img:
                    # Use that 5800X muscle for the high-quality decode
                    img.draft('RGB', target_size) 
                    
                    # Matchstick Resize: Keeps aspect ratio perfect
                    img.thumbnail(target_size, Image.Resampling.LANCZOS)
                    
                    # Save to RAM buffer - no NVMe wear here!
                    img_io = io.BytesIO()
                    img.save(img_io, 'JPEG', quality=92, subsampling=0, optimize=True)
                    img_io.seek(0)
                    
                    return send_file(img_io, mimetype='image/jpeg')
                
            except Exception as e:
                print(f"Server Error: {e}")
                return "Server error", 500

    except (IOError, OSError) as e:
        print(f"Error opening {file_path.name}: {e}")

    photo_hash = photohashes.reverse_hash_db.get(file_str)
    print(f"Instructing target to display photo with hash: {photo_hash}")
    



    try:
        #return send_from_directory(UPLOAD_FOLDER, filename)
        print('iterate directory to find image matching hash here')
    except FileNotFoundError:
        return "File not found", 404

def standup():
    print(f"standing up server listening on {config.LISTEN_PORT}")
    server_thread = threading.Thread(target=run_server)
    
    server_thread.daemon = True
    
    server_thread.start()

def run_server():
    app.run(host='0.0.0.0', port=config.LISTEN_PORT, debug=True, use_reloader=False)

