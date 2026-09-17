# SPDX-FileCopyrightText: © 2024 Tiny Tapeout / Matthias Musch
# SPDX-License-Identifier: Apache-2.0
"""Cocotb helpers for the Kraken mini pin loader.

Uses scripts/kraken_pin_protocol.py so packing cannot drift from the SDK.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, NextTimeStep, RisingEdge, ReadOnly

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from kraken_pin_protocol import (  # noqa: E402
    IMEM_DEPTH,
    OP_CLKDIV_HI,
    OP_CLKDIV_LO,
    OP_EXEC,
    OP_IMEM,
    OP_INPIN,
    OP_PIN,
    OP_SHIFT,
    OP_THRESH,
    load_hex,
    pack_inpin,
    pack_pin,
    pack_shift,
    pack_thresh,
    pack_wrap,
    uio_cfg,
)

TEST_DIR = Path(__file__).resolve().parent
GEN_DIR = TEST_DIR / "generated"

# Status bits on uo when rx_hold is not active
UO_TX_FULL = 0x04
UO_RX_EMPTY = 0x08


async def start_clock(dut, period_ns: float = 10.0) -> None:
    cocotb.start_soon(Clock(dut.clk, period_ns, unit="ns").start())


async def reset(dut, cycles: int = 10) -> None:
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


async def cfg_strobe(dut, op: int, data: int) -> None:
    base = uio_cfg(op, strobe=0)
    dut.ui_in.value = data & 0xFF
    dut.uio_in.value = base
    await RisingEdge(dut.clk)
    dut.uio_in.value = base | 1
    await RisingEdge(dut.clk)
    dut.uio_in.value = base
    await RisingEdge(dut.clk)


async def imem_write_word(dut, addr: int, word: int) -> None:
    assert 0 <= addr < IMEM_DEPTH
    lo = word & 0xFF
    hi = (word >> 8) & 0xFF

    dut.ui_in.value = lo
    dut.uio_in.value = uio_cfg(OP_IMEM, addr=addr, half=0, strobe=0)
    await RisingEdge(dut.clk)
    dut.uio_in.value = uio_cfg(OP_IMEM, addr=addr, half=0, strobe=1)
    await RisingEdge(dut.clk)
    dut.uio_in.value = uio_cfg(OP_IMEM, addr=addr, half=0, strobe=0)
    await RisingEdge(dut.clk)

    dut.ui_in.value = hi
    dut.uio_in.value = uio_cfg(OP_IMEM, addr=addr, half=1, strobe=0)
    await RisingEdge(dut.clk)
    dut.uio_in.value = uio_cfg(OP_IMEM, addr=addr, half=1, strobe=1)
    await RisingEdge(dut.clk)
    dut.uio_in.value = uio_cfg(OP_IMEM, addr=addr, half=1, strobe=0)
    await RisingEdge(dut.clk)


async def load_program(dut, words: list[int], *, base: int = 0) -> None:
    assert len(words) + base <= IMEM_DEPTH, (
        f"program needs {len(words)} words at base {base}, IMEM_DEPTH={IMEM_DEPTH}"
    )
    for i, word in enumerate(words):
        await imem_write_word(dut, base + i, word)


async def configure_wrap(dut, wrap_bottom: int, wrap_top: int) -> None:
    await cfg_strobe(dut, OP_EXEC, pack_wrap(wrap_bottom, wrap_top))


async def configure_pin(
    dut,
    *,
    set_count: int = 0,
    out_count: int = 0,
    sideset_count: int = 0,
    side_en: int = 0,
    side_pindir: int = 0,
) -> None:
    await cfg_strobe(
        dut,
        OP_PIN,
        pack_pin(set_count, out_count, sideset_count, side_en, side_pindir),
    )


async def configure_shift(
    dut,
    *,
    in_shiftdir: int = 0,
    out_shiftdir: int = 1,
    autopush: int = 0,
    autopull: int = 0,
) -> None:
    await cfg_strobe(
        dut,
        OP_SHIFT,
        pack_shift(in_shiftdir, out_shiftdir, autopush, autopull),
    )


async def configure_thresh(dut, push_thresh: int = 0, pull_thresh: int = 0) -> None:
    await cfg_strobe(dut, OP_THRESH, pack_thresh(push_thresh, pull_thresh))


async def configure_inpin(dut, in_base: int = 0, jmp_pin: int = 0) -> None:
    await cfg_strobe(dut, OP_INPIN, pack_inpin(in_base, jmp_pin))


async def configure_clkdiv(dut, divider: int) -> None:
    await cfg_strobe(dut, OP_CLKDIV_LO, divider & 0xFF)
    await cfg_strobe(dut, OP_CLKDIV_HI, (divider >> 8) & 0xFF)


async def configure_blink(dut, *, wrap_bottom: int = 0, wrap_top: int = 1) -> None:
    await configure_wrap(dut, wrap_bottom, wrap_top)
    await configure_pin(dut, set_count=1)


async def configure_uart_tx(dut, clkdiv: int, *, wrap_top: int = 3) -> None:
    await configure_wrap(dut, 0, wrap_top)
    await configure_pin(dut, out_count=1, sideset_count=1, side_en=1)
    await configure_shift(dut, autopull=1)
    await configure_thresh(dut, 0, 0)
    await configure_clkdiv(dut, clkdiv)


async def configure_rx_shift(dut) -> None:
    """1-instr `in pins, 2` loop with autopush at 8 bits."""
    await configure_wrap(dut, 0, 0)
    await configure_pin(dut)  # counts unused for IN
    await configure_shift(dut, in_shiftdir=0, autopush=1)
    await configure_thresh(dut, push_thresh=0, pull_thresh=0)
    await configure_inpin(dut, in_base=0)


async def enter_run_mode(dut, *, sm_enable: bool = False) -> None:
    dut.ui_in.value = 0
    dut.uio_in.value = (1 << 1) if sm_enable else 0


def run_uio(sm_enable: bool = True, tx_push: int = 0, restart: int = 0, rx_pop: int = 0, rx_ack: int = 0) -> int:
    return (
        ((1 << 1) if sm_enable else 0)
        | ((tx_push & 1) << 0)
        | ((restart & 1) << 2)
        | ((rx_pop & 1) << 3)
        | ((rx_ack & 1) << 4)
    )


async def sample_uo(dut) -> int:
    """Sample uo_out after a rising edge; leave the ReadOnly phase afterward."""
    await RisingEdge(dut.clk)
    await ReadOnly()
    val = int(dut.uo_out.value)
    await NextTimeStep()
    return val


async def sample_uo0(dut, n: int) -> list[int]:
    samples = []
    for _ in range(n):
        samples.append((await sample_uo(dut)) & 1)
    return samples


def tx_full(uo: int) -> bool:
    return bool(uo & UO_TX_FULL)


def rx_empty(uo: int) -> bool:
    return bool(uo & UO_RX_EMPTY)


def irq_flags(uo: int) -> int:
    return (uo >> 4) & 0xF


async def tx_push_byte(dut, byte: int, *, sm_enable: bool = True) -> None:
    """Rising edge on uio[0] while SM enabled; ui holds the byte."""
    dut.ui_in.value = byte & 0xFF
    base = run_uio(sm_enable=sm_enable, tx_push=0)
    dut.uio_in.value = base
    await RisingEdge(dut.clk)
    dut.uio_in.value = run_uio(sm_enable=sm_enable, tx_push=1)
    await RisingEdge(dut.clk)
    dut.uio_in.value = base
    await RisingEdge(dut.clk)


async def pulse_restart(dut, *, sm_enable: bool = True) -> None:
    base = run_uio(sm_enable=sm_enable)
    dut.uio_in.value = base
    await RisingEdge(dut.clk)
    dut.uio_in.value = run_uio(sm_enable=sm_enable, restart=1)
    await RisingEdge(dut.clk)
    dut.uio_in.value = base
    await RisingEdge(dut.clk)


async def pulse_rx_pop(dut, *, sm_enable: bool = True) -> None:
    base = run_uio(sm_enable=sm_enable)
    dut.uio_in.value = base
    await RisingEdge(dut.clk)
    dut.uio_in.value = run_uio(sm_enable=sm_enable, rx_pop=1)
    await RisingEdge(dut.clk)
    dut.uio_in.value = base
    await RisingEdge(dut.clk)


async def pulse_rx_ack(dut, *, sm_enable: bool = True) -> None:
    base = run_uio(sm_enable=sm_enable)
    dut.uio_in.value = run_uio(sm_enable=sm_enable, rx_ack=1)
    await RisingEdge(dut.clk)
    dut.uio_in.value = base
    await RisingEdge(dut.clk)


def is_gate_level(dut) -> bool:
    """Gate-level netlists flatten hierarchy; RTL keeps kraken_mini_inst."""
    try:
        _ = dut.user_project.kraken_mini_inst
        return False
    except AttributeError:
        return True


def read_imem_word(dut, addr: int) -> int:
    """RTL hierarchical peek into instruction memory (not available in gate-level)."""
    mem = dut.user_project.kraken_mini_inst.u_imem.mem
    return int(mem[addr].value)


def require_hex(name: str) -> Path:
    path = GEN_DIR / name
    assert path.is_file(), f"missing {path}; run: make -C test assemble"
    return path
