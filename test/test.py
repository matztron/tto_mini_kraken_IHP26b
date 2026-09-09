# SPDX-FileCopyrightText: © 2024 Tiny Tapeout / Matthias Musch
# SPDX-License-Identifier: Apache-2.0
"""Cocotb: load hello_world.pio via the pin loader and check SET pin square wave."""

from __future__ import annotations

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, ReadOnly

TEST_DIR = Path(__file__).resolve().parent
HEX_PATH = TEST_DIR / "generated" / "hello_world.hex"

# Golden words from pioasm (SET pins,1 [1] / SET pins,0 [1])
EXPECTED_WORDS = [0xE101, 0xE100]

# Config-mode ops on uio[6:4] (uio[7]=1)
OP_IMEM = 0
OP_EXEC = 1
OP_PIN = 2


def load_hex(path: Path) -> list[int]:
    words: list[int] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        words.append(int(line, 16))
    return words


def _uio_cfg(op: int, *, addr: int = 0, half: int = 0, strobe: int = 0) -> int:
    """Build uio_in for config mode."""
    return (
        (1 << 7)
        | ((op & 0x7) << 4)
        | ((addr & 0x3) << 2)
        | ((half & 0x1) << 1)
        | (strobe & 0x1)
    )


async def reset(dut, cycles: int = 10) -> None:
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


async def cfg_strobe(dut, op: int, data: int) -> None:
    """Pulse uio[0] once in config mode to apply `op` with payload `data` on ui."""
    base = _uio_cfg(op, strobe=0)
    dut.ui_in.value = data & 0xFF
    dut.uio_in.value = base
    await RisingEdge(dut.clk)
    dut.uio_in.value = base | 1
    await RisingEdge(dut.clk)
    dut.uio_in.value = base
    await RisingEdge(dut.clk)


async def imem_write_word(dut, addr: int, word: int) -> None:
    """Write one 16-bit IMEM word via the two-strobe half-byte protocol."""
    lo = word & 0xFF
    hi = (word >> 8) & 0xFF

    # Low byte: latch addr/half while strobe=0, then rising edge.
    dut.ui_in.value = lo
    dut.uio_in.value = _uio_cfg(OP_IMEM, addr=addr, half=0, strobe=0)
    await RisingEdge(dut.clk)
    dut.uio_in.value = _uio_cfg(OP_IMEM, addr=addr, half=0, strobe=1)
    await RisingEdge(dut.clk)
    dut.uio_in.value = _uio_cfg(OP_IMEM, addr=addr, half=0, strobe=0)
    await RisingEdge(dut.clk)

    # High byte: completes the IMEM write.
    dut.ui_in.value = hi
    dut.uio_in.value = _uio_cfg(OP_IMEM, addr=addr, half=1, strobe=0)
    await RisingEdge(dut.clk)
    dut.uio_in.value = _uio_cfg(OP_IMEM, addr=addr, half=1, strobe=1)
    await RisingEdge(dut.clk)
    dut.uio_in.value = _uio_cfg(OP_IMEM, addr=addr, half=1, strobe=0)
    await RisingEdge(dut.clk)


async def load_program(dut, words: list[int]) -> None:
    assert len(words) <= 4, "pin loader only addresses 4 IMEM words (uio[3:2])"
    for addr, word in enumerate(words):
        await imem_write_word(dut, addr, word)


async def configure_hello_world(dut) -> None:
    """wrap 0..1, SET_COUNT=1; CLKDIV already resets to 1."""
    await cfg_strobe(dut, OP_EXEC, 0x10)  # wrap_top=1, wrap_bottom=0
    await cfg_strobe(dut, OP_PIN, 0x01)  # set_count=1


async def enter_run_mode(dut, *, sm_enable: bool = False) -> None:
    """Leave config mode. Do not wait a clock — first sample edge should see enable."""
    dut.ui_in.value = 0
    dut.uio_in.value = (1 << 1) if sm_enable else 0


@cocotb.test()
async def test_hello_world_square_wave(dut):
    """uo[0] toggles 1,1,0,0,... after loading pioasm hello_world via the pin loader."""
    assert HEX_PATH.is_file(), f"missing {HEX_PATH}; run: make -C test assemble"
    words = load_hex(HEX_PATH)
    assert words == EXPECTED_WORDS, f"got {[hex(w) for w in words]}"

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    await load_program(dut, words)
    await configure_hello_world(dut)
    await enter_run_mode(dut, sm_enable=True)

    samples = []
    for _ in range(8):
        await RisingEdge(dut.clk)
        await ReadOnly()
        samples.append(int(dut.uo_out.value) & 0x1)

    expected = [1, 1, 0, 0, 1, 1, 0, 0]
    assert samples == expected, f"got {samples}, expected {expected}"
