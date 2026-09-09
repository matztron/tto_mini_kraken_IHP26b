# SPDX-FileCopyrightText: © 2024 Tiny Tapeout / Matthias Musch
# SPDX-License-Identifier: Apache-2.0
"""I2C master write demo on uo[0]=SDA, uo[1]=SCL (external pull-ups required).

Default: START + write 0x00 to device 7-bit address 0x50 + STOP.

  mpremote cp sdk/kraken_loader.py :
  mpremote cp sdk/examples/i2c_master/i2c_master.hex sdk/examples/i2c_master/run.py :
  mpremote run sdk/examples/i2c_master/run.py
"""

import kraken_loader as kl

HEX_PATH = "i2c_master.hex"
CLOCK_HZ = 1_000_000
I2C_CLKDIV = 40
I2C_ADDR = 0x50
I2C_DATA = (0x00,)


def i2c_write_payload(addr7, data_bytes=()):
    """Build TX FIFO bytes: 8-bit addr (W), then optional data bytes."""
    payload = [(addr7 << 1) & 0xFE]
    payload.extend(b & 0xFF for b in data_bytes)
    return payload


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
    payload = i2c_write_payload(addr7, data)
    print(
        "IMEM words:", len(words),
        "FIFO bytes:", len(payload),
        "addr: 0x{:02x}".format(addr7),
        "data:", [hex(b) for b in payload],
    )

    loader.hardware_reset()
    loader.load_program(words)
    loader.configure_i2c_master(clkdiv, wrap_top=len(words) - 1)
    loader.enter_run_mode(sm_enable=True, tx_drive=True)

    if clock_hz:
        tt.clock_project_PWM(clock_hz)

    loader.tx_push_bytes(payload)

    print("I2C write sent on uo[0]=SDA, uo[1]=SCL")
    print("Scope or logic analyzer at ~{} Hz SCL (approx).".format(clock_hz // (8 * clkdiv)))


if __name__ == "__main__":
    main()
