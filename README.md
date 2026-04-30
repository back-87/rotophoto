# rotophoto
target/server(BTT Pi 2) + source/client (*nix) for a monitor mounted on a NEMA 17 stepper motor. Displays photos after rotating the monitor to the correct orientation (landscape vs portrait type of thing)


Read the comment at the top of each py file to get an idea of how this system functions, perhaps start with iteratephotos.py (in the source directory) 

When running either target or source: 
	a) make a venv \ 
	b) pip install -r requirements.txt \
	Entry point for target: listener.py   ->    python3 -m target.listener \
	Entry point for source: iteratephotos.py   ->    python3 -m source.interatephotos \

April 30 2026
