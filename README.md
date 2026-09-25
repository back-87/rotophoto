# rotophoto
target/server(BTT Pi 2) + source/client (*nix) for a monitor mounted on a NEMA 17 stepper motor. Displays photos after rotating the monitor to the correct orientation (landscape vs portrait type of thing)


Read the comment at the top of each py file to get an idea of how this system functions, perhaps start with iteratephotos.py (in the source directory) 

When running either target or source: 
	a) make a venv \ 
	b) pip install -r requirements.txt \
	Entry point for target: listener.py   ->    python3 -m target.listener \
	Entry point for source: iteratephotos.py   ->    python3 -m source.interatephotos \

Firmware Update Pipeline & Pico Setup
The control logic on the BTT Pico (RP2040) is updated automatically over UART by the parent service running on the Raspberry Pi 5. Once the physical connections are made, you never need to connect a USB-C cable or open the hardware enclosure to update the motor logic.
1. Physical Hardware Connection
• Connect UART0 on the BTT Pico (3 pins out of the 5-pin header) to the Raspberry Pi 5’s JST-SH 1.0mm 3-pin UART connector.
• Note: Ensure your TX and RX lines cross correctly (Pi TX \(\rightarrow \) Pico RX, Pi RX \(\rightarrow \) Pico TX) and share a common ground.
2. One-Time Initial Provisioning
Before sealing the enclosure, connect the Pico via USB-C one last time to load the base bootloader using Thonny:
1. Open Thonny's package manager and install the threading package on the Pico. (Native uhashlib and ubinascii are already built into the MicroPython firmware, so no extra hash packages are required).
2. Copy boot.py and main.py from target/Pico_Source/ straight into the root directory of the Pico.
3. Disconnect the USB-C cable forever.
3. How Updates Work Deployments
Whenever the parent service launches on the Raspberry Pi 5, the target.listener orchestrator automatically manages the Pico's lifecycle:
• The Intercept Sequence: The Pi fires a low-level serial salute (Ctrl+B \(\rightarrow \) Ctrl+C \(\rightarrow \) Ctrl+D) down the UART line to cleanly break the Pico out of any active motor loops and force a soft reboot.
• Smart Delta Synchronization: The Pi asks for a U:SCAN manifest. The Pico streams back a lean memory-safe dictionary of its local files and MD5 hashes.
• Differential Flash Writes: The Pi cross-references this manifest and only transmits files that have changed or are missing, saving flash memory wear and avoiding UART traffic jams.
4. Developer Rule of Thumb
• Your Application Entry Point is app.py.
• The synchronization logic strictly protects boot.py and main.py from being overwritten over UART. Put all of your motor controls, main loops, and logic inside app.py. The pipeline handles recursively creating any parent directories and relative asset structures you add to target/Pico_Source/ automatically!


After installing requirements in your venv, while still with the venv active, navigate to ~/ and do $ picframe -i .

It is recommended to write over ~/picframe/config/configuration.yaml with the copy in this repo
