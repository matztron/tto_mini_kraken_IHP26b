# SPDX-FileCopyrightText: © 2024 Tiny Tapeout / Matthias Musch
# SPDX-License-Identifier: Apache-2.0
"""Legacy entry point — prefer sdk/examples/blink/run.py."""

import kraken_loader as kl

HELLO_WORLD_HEX = "hello_world.hex"
EXPECTED_SAMPLES = [1, 1, 0, 0, 1, 1, 0, 0]


def main(hex_path=HELLO_WORLD_HEX, clock_hz=1_000_000):
    from ttboard.demoboard import DemoBoard

    tt = DemoBoard.get()
    kl.enable_project(tt)
    loader = kl.KrakenLoader(tt)
    loader.setup_host_pins()

    words = kl.load_hex(hex_path)
    print("IMEM words:", [hex(w) for w in words])

    loader.hardware_reset()
    loader.load_program(words)
    loader.configure_blink()
    loader.enter_run_mode(sm_enable=True)

    if clock_hz:
        tt.clock_project_PWM(clock_hz)

    samples = loader.sample_uo0(len(EXPECTED_SAMPLES))
    print("uo[0] samples:", samples)

    if samples == EXPECTED_SAMPLES:
        print("PASS: blink square wave")
    else:
        print("WARN: expected", EXPECTED_SAMPLES)

    return samples


if __name__ == "__main__":
    main()
