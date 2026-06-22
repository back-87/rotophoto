# rotophoto
target/server(BTT Pi 2) + source/client (*nix) for a monitor mounted on a NEMA 17 stepper motor. Displays photos after rotating the monitor to the correct orientation (landscape vs portrait type of thing)


Read the comment at the top of each py file to get an idea of how this system functions, perhaps start with iteratephotos.py (in the source directory) 

When running either target or source: 
	a) make a venv \ 
	b) pip install -r requirements.txt \
	Entry point for target: listener.py   ->    python3 -m target.listener \
	Entry point for source: iteratephotos.py   ->    python3 -m source.interatephotos \


After installing requirements in your venv, while still with the venv active, navigate to ~/ and do $ picframe -i .
edit ~/picframe_data/config/configuration.yaml so that:

viewer:
  # ... your other working settings (use_glx: True, width/height) ...
  
  # 1. Turn this to TRUE to stretch/scale images to fill every pixel of the 4K panel
  fit: True 
  
  # 2. Change this to FALSE to strip away the border matting entirely
  edge_alpha: 0.0 
  
  # 3. Drop the blur to 0 to completely eliminate any background letterboxing shadows
  blur_amount: 0 

  
April 30 2026
