# SPDX-FileCopyrightText: © 2024 Tiny Tapeout / Matthias Musch
# SPDX-License-Identifier: Apache-2.0
"""UART TX example on uo[0] (connect to USB-serial adapter RX, GND common).

  mpremote cp sdk/kraken_loader.py :
  mpremote cp sdk/examples/uart_tx/uart_tx.hex sdk/examples/uart_tx/run.py :
  mpremote run sdk/examples/uart_tx/run.py
"""

import kraken_loader as kl

HEX_PATH = "uart_tx.hex"
MESSAGE = b"Hello from Kraken mini PIO!\r\n"
CLOCK_HZ = 1_000_000
BAUD = 115200


def main(hex_path=HEX_PATH, message=MESSAGE, clock_hz=CLOCK_HZ, baud=BAUD):
    from ttboard.demoboard import DemoBoard

    tt = DemoBoard.get()
    kl.enable_project(tt)
    loader = kl.KrakenLoader(tt)
    loader.setup_host_pins()

    words = kl.load_hex(hex_path)
    clkdiv = kl.KrakenLoader.uart_clkdiv(clock_hz, baud)
    eff_baud = clock_hz // (8 * clkdiv)
    print("IMEM words:", len(words), "clkdiv:", clkdiv, "~baud:", eff_baud)

    loader.hardware_reset()
    loader.load_program(words)
    loader.configure_uart_tx(clkdiv)
    loader.enter_run_mode(sm_enable=True, tx_drive=True)

    if clock_hz:
        tt.clock_project_PWM(clock_hz)

    loader.tx_push_bytes(message)
    print("Sent:", message)
    print("Scope uo[0] or open serial adapter at", eff_baud, "8N1")


if __name__ == "__main__":
    main()
