import lgpio
import time
import signal
import sys


def set_half_duty_cycle():
    #Open the GPIO chip (gpiochip0 handles GPIOs 0-27 on Pi 5)
    h = lgpio.gpiochip_open(0)

    # Claim GPIO 13 (Physical Pin 33)
    lgpio.gpio_claim_output(h, 13)

    # Set PWM: chip handle, gpio, frequency (Hz), duty_cycle (PERCENTAGE 0-100)
    # 50% duty cycle at 1000Hz
    lgpio.tx_pwm(h, 13, 1000, 50) 

    print("PWM set on GPIO 13 (Pin 33) to 50%")

# Optional: Handle cleanup on exit
def stop_pwm():
    lgpio.gpio_free(h, 13)
    lgpio.gpiochip_close(h)