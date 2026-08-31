# SPDX-FileCopyrightText: © 2024 Tiny Tapeout / Matthias Musch
# SPDX-License-Identifier: Apache-2.0
"""Kraken mini PIO pin loader for Tiny Tapeout demoboard (MicroPython).

Programs IMEM and SM config over ui/uio in config mode (uio[7]=1), then runs
the state machine in run mode (uio[7]=0). Matches test/test.py and kraken_tt_loader.sv.

Requires tt-micropython-firmware on the demoboard:
  https://github.com/TinyTapeout/tt-micropython-firmware
"""

# Config-mode ops: IMEM when uio[6]=0 (addr uio[5:2]+ui[4]); other ops uio[6]=1
OP_IMEM = 0
OP_EXEC = 1
OP_PIN = 2
OP_CLKDIV_LO = 3
OP_CLKDIV_HI = 4
OP_SHIFT = 5
OP_THRESH = 6
OP_INPIN = 7

IMEM_DEPTH = 32
PROJECT_NAME = "tt_um_mini_kraken"

# Pico drives all uio bits while bit-banging the loader.
UIO_OE_CONFIG = 0xFF
# Run mode: host drives uio[1]=sm_enable; uio[0]=tx_push when sending FIFO data.
UIO_OE_RUN = 0x02
UIO_OE_RUN_TX = 0x03


def uio_cfg(op, addr=0, half=0, strobe=0, wrap_top_sel=0):
    """Build uio_in byte for config mode (uio[7]=1)."""
    if op == OP_IMEM:
        return (
            (1 << 7)
            | ((addr & 0xF) << 2)
            | ((half & 0x1) << 1)
            | (strobe & 0x1)
        )
    return (
        (1 << 7)
        | (1 << 6)
        | ((op & 0x7) << 3)
        | ((wrap_top_sel & 0x1) << 2)
        | (strobe & 0x1)
    )


def imem_addr_ui(addr):
    """ui[4] carries IMEM address bit 4 while uio[5:2] carries bits [3:0]."""
    return (addr >> 4) & 0x1


def load_hex(path):
    """Load pioasm -o hex words from a text file."""
    words = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in "#/":
                continue
            words.append(int(line, 16))
    return words


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

    def cfg_strobe(self, op, data, wrap_top_sel=0):
        """Apply one config op; payload on ui_in, strobe on uio[0]."""
        base = uio_cfg(op, strobe=0, wrap_top_sel=wrap_top_sel)
        self.tt.ui_in = data & 0xFF
        self.tt.uio_in = base
        self.rising_tick()
        self.tt.uio_in = base | 1
        self.rising_tick()
        self.tt.uio_in = base
        self.rising_tick()

    def imem_write_word(self, addr, word):
        """Write one 16-bit instruction word."""
        lo = word & 0xFF
        hi = (word >> 8) & 0xFF

        self.tt.ui_in = imem_addr_ui(addr)
        self.tt.uio_in = uio_cfg(OP_IMEM, addr=addr, half=0, strobe=0)
        self.rising_tick()
        self.tt.ui_in = lo
        self.tt.uio_in = uio_cfg(OP_IMEM, addr=addr, half=0, strobe=1)
        self.rising_tick()
        self.tt.uio_in = uio_cfg(OP_IMEM, addr=addr, half=0, strobe=0)
        self.rising_tick()

        self.tt.ui_in = imem_addr_ui(addr)
        self.tt.uio_in = uio_cfg(OP_IMEM, addr=addr, half=1, strobe=0)
        self.rising_tick()
        self.tt.ui_in = hi
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
        """Alias for configure_blink (legacy name)."""
        self.configure_blink()

    def configure_blink(self):
        """wrap 0..1, SET_COUNT=1; clkdiv defaults to 1."""
        self.configure_wrap(0, 1)
        self.cfg_strobe(OP_PIN, 0x01)

    def configure_shift(self, in_shiftdir=0, out_shiftdir=1, autopush=0, autopull=0):
        data = (
            (in_shiftdir & 1)
            | ((out_shiftdir & 1) << 1)
            | ((autopush & 1) << 2)
            | ((autopull & 1) << 3)
        )
        self.cfg_strobe(OP_SHIFT, data)

    def configure_thresh(self, push_thresh=0, pull_thresh=0):
        """Threshold 0 = full 8-bit width (see kraken_pkg thresh_decode)."""
        data = (push_thresh & 0x1F) | ((pull_thresh & 0x7) << 5)
        self.cfg_strobe(OP_THRESH, data)

    def configure_uart_tx(self, clkdiv, wrap_top=3):
        """Side-set + OUT on pin 0, 8-bit autopull, wrap over uart_tx.pio."""
        self.configure_wrap(0, wrap_top)
        # side_en | sideset_count=1 | out_count=1
        self.cfg_strobe(OP_PIN, 0x94)
        self.configure_shift(autopull=1)
        self.configure_thresh(0, 0)
        self.configure_clkdiv(clkdiv)

    def configure_i2c_bitstream(self, clkdiv):
        """OUT on pins [1:0], 8-bit autopull, one-instruction loop."""
        self.configure_wrap(0, 0)
        # out_count=2
        self.cfg_strobe(OP_PIN, 0x08)
        self.configure_shift(autopull=1)
        self.configure_thresh(0, 0)
        self.configure_clkdiv(clkdiv)

    @staticmethod
    def uart_clkdiv(clock_hz, baud):
        """Integer clkdiv for 8n1 UART (8 cycles per bit)."""
        return max(1, clock_hz // (8 * baud))

    def configure_wrap(self, wrap_bottom, wrap_top):
        self.cfg_strobe(OP_EXEC, wrap_bottom & 0x1F, wrap_top_sel=0)
        self.cfg_strobe(OP_EXEC, wrap_top & 0x1F, wrap_top_sel=1)

    def configure_pin(self, set_count, out_count=0, sideset_count=0, side_en=0, side_pindir=0):
        data = (
            (side_en << 7)
            | (side_pindir << 6)
            | ((sideset_count & 0x3) << 4)
            | ((out_count & 0x3) << 2)
            | (set_count & 0x3)
        )
        self.cfg_strobe(OP_PIN, data)

    def configure_clkdiv(self, divider):
        self.cfg_strobe(OP_CLKDIV_LO, divider & 0xFF)
        self.cfg_strobe(OP_CLKDIV_HI, (divider >> 8) & 0xFF)

    def enter_run_mode(self, sm_enable=False, tx_drive=False):
        """Leave config mode (uio[7]=0). Optionally drive sm_enable and/or tx_push."""
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
        """Push one byte into the TX FIFO (run mode, uio[7]=0)."""
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
        """Sample uo[0] after n rising clock edges (for quick sanity checks)."""
        samples = []
        for _ in range(n):
            self.rising_tick()
            samples.append(self.tt.uo_out.value & 1)
        return samples


def enable_project(tt, name=PROJECT_NAME):
    """Select tt_um_mini_kraken on ASIC shuttle or FPGA bitstream."""
    design = getattr(tt.shuttle, name, None)
    if design is None:
        raise RuntimeError("project not found: {}".format(name))
    design.enable()
    return design
