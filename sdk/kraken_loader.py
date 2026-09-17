# SPDX-FileCopyrightText: © 2024 Tiny Tapeout / Matthias Musch
# SPDX-License-Identifier: Apache-2.0
"""Kraken mini PIO pin loader for Tiny Tapeout demoboard (MicroPython).

Programs IMEM and SM config over ui/uio in config mode (uio[7]=1), then runs
the state machine in run mode (uio[7]=0).

Protocol packing lives in kraken_pin_protocol.py (from scripts/) — copy that
file next to this module on the demoboard so SDK and cocotb cannot drift.

Requires tt-micropython-firmware:
  https://github.com/TinyTapeout/tt-micropython-firmware
"""

try:
    from kraken_pin_protocol import (
        IMEM_DEPTH,
        OP_CLKDIV_HI,
        OP_CLKDIV_LO,
        OP_EXEC,
        OP_IMEM,
        OP_INPIN,
        OP_PIN,
        OP_SHIFT,
        OP_THRESH,
        PROJECT_NAME,
        UIO_OE_CONFIG,
        UIO_OE_RUN,
        load_hex,
        pack_inpin,
        pack_pin,
        pack_shift,
        pack_thresh,
        pack_wrap,
        uart_clkdiv,
        uio_cfg,
    )
except ImportError as exc:
    raise ImportError(
        "kraken_pin_protocol.py missing — copy scripts/kraken_pin_protocol.py "
        "next to kraken_loader.py (same protocol as cocotb tests)"
    ) from exc


class KrakenLoader:
    """Bit-bang the Kraken pin loader on a Tiny Tapeout DemoBoard."""

    def __init__(self, tt):
        self.tt = tt

    def setup_host_pins(self):
        """Pico drives ui and uio into the project (not DIP switches)."""
        from ttboard.mode import RPMode

        self.tt.mode = RPMode.ASIC_RP_CONTROL
        self.tt.uio_oe_pico = UIO_OE_CONFIG

    def rising_tick(self):
        """One project clock rising edge (idle low afterward)."""
        self.tt.pins.project_clk_driven_by_RP2(True)
        clk = self.tt.pins.rp_projclk
        clk(0)
        clk(1)
        clk(0)

    def hardware_reset(self, hold_ticks=10):
        """Pulse project reset, then release."""
        self.tt.ui_in = 0
        self.tt.uio_in = 0
        self.tt.reset_project(True)
        for _ in range(hold_ticks):
            self.rising_tick()
        self.tt.reset_project(False)
        for _ in range(2):
            self.rising_tick()

    def cfg_strobe(self, op, data):
        """Apply one config op; payload on ui_in, strobe on uio[0]."""
        base = uio_cfg(op, strobe=0)
        self.tt.ui_in = data & 0xFF
        self.tt.uio_in = base
        self.rising_tick()
        self.tt.uio_in = base | 1
        self.rising_tick()
        self.tt.uio_in = base
        self.rising_tick()

    def imem_write_word(self, addr, word):
        """Write one 16-bit instruction word (two half-byte strobes)."""
        lo = word & 0xFF
        hi = (word >> 8) & 0xFF

        self.tt.ui_in = lo
        self.tt.uio_in = uio_cfg(OP_IMEM, addr=addr, half=0, strobe=0)
        self.rising_tick()
        self.tt.uio_in = uio_cfg(OP_IMEM, addr=addr, half=0, strobe=1)
        self.rising_tick()
        self.tt.uio_in = uio_cfg(OP_IMEM, addr=addr, half=0, strobe=0)
        self.rising_tick()

        self.tt.ui_in = hi
        self.tt.uio_in = uio_cfg(OP_IMEM, addr=addr, half=1, strobe=0)
        self.rising_tick()
        self.tt.uio_in = uio_cfg(OP_IMEM, addr=addr, half=1, strobe=1)
        self.rising_tick()
        self.tt.uio_in = uio_cfg(OP_IMEM, addr=addr, half=1, strobe=0)
        self.rising_tick()

    def load_program(self, words):
        if len(words) > IMEM_DEPTH:
            raise ValueError("max {} IMEM words".format(IMEM_DEPTH))
        for addr, word in enumerate(words):
            self.imem_write_word(addr, word)

    def configure_hello_world(self):
        self.configure_blink()

    def configure_blink(self):
        self.configure_wrap(0, 1)
        self.cfg_strobe(OP_PIN, pack_pin(set_count=1))

    def configure_shift(self, in_shiftdir=0, out_shiftdir=1, autopush=0, autopull=0):
        self.cfg_strobe(
            OP_SHIFT,
            pack_shift(in_shiftdir, out_shiftdir, autopush, autopull),
        )

    def configure_thresh(self, push_thresh=0, pull_thresh=0):
        self.cfg_strobe(OP_THRESH, pack_thresh(push_thresh, pull_thresh))

    def configure_uart_tx(self, clkdiv, wrap_top=3):
        self.configure_wrap(0, wrap_top)
        self.cfg_strobe(
            OP_PIN,
            pack_pin(out_count=1, sideset_count=1, side_en=1),
        )
        self.configure_shift(autopull=1)
        self.configure_thresh(0, 0)
        self.configure_clkdiv(clkdiv)

    def configure_i2c_bitstream(self, clkdiv):
        self.configure_wrap(0, 0)
        self.cfg_strobe(OP_PIN, pack_pin(out_count=2))
        self.configure_shift(autopull=1)
        self.configure_thresh(0, 0)
        self.configure_clkdiv(clkdiv)

    def configure_inpin(self, in_base=0, jmp_pin=0):
        self.cfg_strobe(OP_INPIN, pack_inpin(in_base, jmp_pin))

    @staticmethod
    def uart_clkdiv(clock_hz, baud):
        return uart_clkdiv(clock_hz, baud)

    def configure_wrap(self, wrap_bottom, wrap_top):
        self.cfg_strobe(OP_EXEC, pack_wrap(wrap_bottom, wrap_top))

    def configure_pin(self, set_count, out_count=0, sideset_count=0, side_en=0, side_pindir=0):
        self.cfg_strobe(
            OP_PIN,
            pack_pin(set_count, out_count, sideset_count, side_en, side_pindir),
        )

    def configure_clkdiv(self, divider):
        self.cfg_strobe(OP_CLKDIV_LO, divider & 0xFF)
        self.cfg_strobe(OP_CLKDIV_HI, (divider >> 8) & 0xFF)

    def enter_run_mode(self, sm_enable=False, tx_drive=False):
        self.tt.ui_in = 0
        oe = 0
        if sm_enable:
            oe |= UIO_OE_RUN
        if tx_drive:
            oe |= 0x01
        self.tt.uio_oe_pico = oe
        self.tt.uio_in = (1 << 1) if sm_enable else 0

    def tx_full(self):
        return bool(self.tt.uo_out.value & 0x04)

    def tx_push(self, byte):
        while self.tx_full():
            self.rising_tick()
        self.tt.ui_in = byte & 0xFF
        base = self.tt.uio_in & ~0x01
        self.tt.uio_in = base
        self.rising_tick()
        self.tt.uio_in = base | 0x01
        self.rising_tick()
        self.tt.uio_in = base
        self.rising_tick()

    def tx_push_bytes(self, data):
        for b in data:
            self.tx_push(b)

    def sample_uo0(self, n=8):
        samples = []
        for _ in range(n):
            self.rising_tick()
            samples.append(self.tt.uo_out.value & 1)
        return samples


def enable_project(tt, name=PROJECT_NAME):
    design = getattr(tt.shuttle, name, None)
    if design is None:
        raise RuntimeError("project not found: {}".format(name))
    design.enable()
    return design
