# SPDX-FileCopyrightText: © 2024 Tiny Tapeout / Matthias Musch
# SPDX-License-Identifier: Apache-2.0
"""I2C master write demo on uo[1:0] (SDA=0, SCL=1). External pull-ups required.

Default transaction: START, write 0x00 to device 7-bit address 0x50, STOP.
Change I2C_ADDR / I2C_DATA for your sensor or EEPROM.

  mpremote cp sdk/kraken_loader.py :
  mpremote cp sdk/examples/i2c_bitstream/*.py sdk/examples/i2c_bitstream/*.hex :
  mpremote run sdk/examples/i2c_bitstream/run.py
"""

import kraken_loader as kl
import i2c_encode as ie

HEX_PATH = "i2c_bitstream.hex"
CLOCK_HZ = 1_000_000
# Bit period ≈ 8 * clkdiv / clock_hz seconds (one OUT per line sample).
I2C_CLKDIV = 40
I2C_ADDR = 0x50
I2C_DATA = (0x00,)


def main(
    hex_path=HEX_PATH,
    clock_hz=CLOCK_HZ,
    clkdiv=I2C_CLKDIV,
    addr7=I2C_ADDR,
    data=I2C_DATA,
):
    from ttboard.demoboard import DemoBoard

    tt = DemoBoard.get()
    kl.enable_project(tt)
    loader = kl.KrakenLoader(tt)
    loader.setup_host_pins()

    words = kl.load_hex(hex_path)
    payload = ie.encode_write(addr7, data)
    print("IMEM words:", len(words), "FIFO bytes:", len(payload), "addr: 0x{:02x}".format(addr7))

    loader.hardware_reset()
    loader.load_program(words)
    loader.configure_i2c_bitstream(clkdiv)
    loader.enter_run_mode(sm_enable=True, tx_drive=True)

    if clock_hz:
        tt.clock_project_PWM(clock_hz)

    for b in payload:
        loader.tx_push(b)

    print("I2C waveform sent on uo[0]=SDA, uo[1]=SCL")
    print("Use a scope or logic analyzer; verify pull-ups and device wiring.")


if __name__ == "__main__":
    main()
