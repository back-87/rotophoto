import time


def run(uart, poll_update):
    print("App starting...")

    try:
        while True:
            print("App is alive and running")
            # line = uart.readline()
            # if line:
            #   line = line.decode().strip()
            #   if line.startswith("U:"):
            #       poll_update(line)
            time.sleep_ms(100)
            # uart.write("alive\n")
    except KeyboardInterrupt:
        print("\nDetected Ctrl+C. Soft resetting...")
        import machine

        machine.soft_reset()
