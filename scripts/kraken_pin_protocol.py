# SPDX-FileCopyrightText: © 2024 Tiny Tapeout / Matthias Musch
# SPDX-License-Identifier: Apache-2.0
"""Shared Kraken mini pin-loader protocol (MicroPython + CPython).

Single source of truth for opcodes and uio/ui packing used by:
  - sdk/kraken_loader.py (demoboard)
  - test/kraken_tb.py (cocotb)

Must stay aligned with src/kraken_tt_loader.sv and docs/info.md.
"""

# Config-mode ops: IMEM when uio[6]=0 (addr uio[4:2]); other ops uio[6]=1
OP_IMEM = 0
OP_EXEC = 1
OP_PIN = 2
OP_CLKDIV_LO = 3
OP_CLKDIV_HI = 4
OP_SHIFT = 5
OP_THRESH = 6
OP_INPIN = 7

IMEM_DEPTH = 8
IMEM_ADDR_MASK = IMEM_DEPTH - 1  # 0x7
PROJECT_NAME = "tt_um_mini_kraken"

# Pico OE helpers (demoboard only; harmless elsewhere)
UIO_OE_CONFIG = 0xFF
UIO_OE_RUN = 0x02
UIO_OE_RUN_TX = 0x03


def uio_cfg(op, addr=0, half=0, strobe=0):
    """Build uio_in byte for config mode (uio[7]=1)."""
    if op == OP_IMEM:
        return (
            (1 << 7)
            | ((addr & IMEM_ADDR_MASK) << 2)
            | ((half & 0x1) << 1)
            | (strobe & 0x1)
        )
    return (
        (1 << 7)
        | (1 << 6)
        | ((op & 0x7) << 3)
        | (strobe & 0x1)
    )


def pack_wrap(wrap_bottom, wrap_top):
    """EXEC payload: ui[3:0]=bottom, ui[7:4]=top (hardware uses low PC_W bits)."""
    return (wrap_bottom & 0xF) | ((wrap_top & 0xF) << 4)


def pack_pin(set_count=0, out_count=0, sideset_count=0, side_en=0, side_pindir=0):
    return (
        ((side_en & 1) << 7)
        | ((side_pindir & 1) << 6)
        | ((sideset_count & 0x3) << 4)
        | ((out_count & 0x3) << 2)
        | (set_count & 0x3)
    )


def pack_shift(in_shiftdir=0, out_shiftdir=1, autopush=0, autopull=0):
    return (
        (in_shiftdir & 1)
        | ((out_shiftdir & 1) << 1)
        | ((autopush & 1) << 2)
        | ((autopull & 1) << 3)
    )


def pack_thresh(push_thresh=0, pull_thresh=0):
    """Threshold 0 = full DATA_W (8) per kraken_pkg thresh_decode."""
    return (push_thresh & 0x1F) | ((pull_thresh & 0x7) << 5)


def pack_inpin(in_base=0, jmp_pin=0):
    return (in_base & 0x1F) | ((jmp_pin & 0x7) << 5)


def uart_clkdiv(clock_hz, baud):
    """Integer clkdiv for 8n1 UART (8 SM cycles per bit)."""
    return max(1, clock_hz // (8 * baud))


def load_hex(path):
    """Load pioasm -o hex words from a text file (path is a string)."""
    words = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in "#/":
                continue
            words.append(int(line, 16))
    return words
