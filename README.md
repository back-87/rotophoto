# rotophoto
target/server(BTT Pi 2) + source/client (*nix) for a monitor mounted on a NEMA 17 stepper motor. Displays photos after rotating the monitor to the correct orientation (landscape vs portrait type of thing)


Read the comment at the top of each py file to get an idea of how this system functions, perhaps start with iteratephotos.py (in the source directory) 

When running either target or source: 
	a) make a venv \ 
	b) pip install -r requirements.txt \
	Entry point for target: listener.py   ->    python3 -m target.listener \
	Entry point for source: iteratephotos.py   ->    python3 -m source.interatephotos \

Setting up the BTT Pico for motor control:
 a) ensure the BTT Pico UART pins (3 of the 5 pin header) are connected to the Pi's JST SH 1.0mm 3-pin UART header, you might need a cable or good soldering skills
 b) connect Pico to Pi via USB-C, use Thonny to install main.py and app.py. Use Thonny's package manager to install "binascii" and "threading". Disconnect USB-C forever
 * Using that main.py, the logic in the target package (runs on Pi, right?) will copy everything from target/Pico_Source over to the Pico as part of its init. This removes the need to leave USB-C connected or open any enclosure to update the motor logic on the Pico
 * main.py loads app.py <- this is where your entry point is. Don't modify main.py (the logic on the Pi won't let you anyways), make changes to app.py.


After installing requirements in your venv, while still with the venv active, navigate to ~/ and do $ picframe -i .

It is recommended to write over ~/picframe/config/configuration.yaml with the copy in this repo
