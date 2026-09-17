# SPDX-FileCopyrightText: © 2024 Tiny Tapeout / Matthias Musch
# SPDX-License-Identifier: Apache-2.0
"""Cocotb suite for Kraken mini — pin loader, SM, FIFO, UART, IRQ, RX."""

from __future__ import annotations

import cocotb
from cocotb.triggers import ClockCycles, NextTimeStep, RisingEdge, ReadOnly

import kraken_tb as tb
from kraken_pin_protocol import IMEM_DEPTH, load_hex


# ---------------------------------------------------------------------------
# 1) Baseline blink (FPGA-proven)
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_blink_square_wave(dut):
    """uo[0] toggles 1,1,0,0,... with hello_world.pio (SET + delay 1)."""
    words = load_hex(str(tb.require_hex("hello_world.hex")))
    assert words == [0xE101, 0xE100], [hex(w) for w in words]

    await tb.start_clock(dut)
    await tb.reset(dut)
    await tb.load_program(dut, words)
    await tb.configure_blink(dut)
    await tb.enter_run_mode(dut, sm_enable=True)

    samples = await tb.sample_uo0(dut, 8)
    assert samples == [1, 1, 0, 0, 1, 1, 0, 0], samples


# ---------------------------------------------------------------------------
# 2) Full 8-word IMEM addressability
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_imem_all_eight_words(dut):
    """Pin loader must write distinct values to every IMEM address 0..7."""
    # Unique non-zero payloads (not relying on opcode legality for storage).
    pattern = [0xA000 | (i << 8) | (0x5A ^ i) for i in range(IMEM_DEPTH)]

    await tb.start_clock(dut)
    await tb.reset(dut)
    await tb.load_program(dut, pattern)

    for addr, want in enumerate(pattern):
        got = tb.read_imem_word(dut, addr)
        assert got == want, f"IMEM[{addr}]: got 0x{got:04x}, want 0x{want:04x}"


@cocotb.test()
async def test_imem_execute_wrap_at_top(dut):
    """Blink at words 6..7; words 0..5 are `jmp 6` so PC must honor wrap + IMEM[6:7]."""
    blink = load_hex(str(tb.require_hex("hello_world.hex")))
    jmp6 = 0x0006  # JMP ALWAYS → address 6

    await tb.start_clock(dut)
    await tb.reset(dut)
    await tb.load_program(dut, [jmp6] * 6, base=0)
    await tb.load_program(dut, blink, base=6)
    await tb.configure_blink(dut, wrap_bottom=6, wrap_top=7)
    await tb.enter_run_mode(dut, sm_enable=True)

    # One cycle may be spent on the initial jmp 6 from reset PC=0.
    samples = await tb.sample_uo0(dut, 9)
    # Find the 1,1,0,0 motif (allow one leading setup cycle).
    ok = any(samples[i : i + 8] == [1, 1, 0, 0, 1, 1, 0, 0] for i in range(2))
    assert ok, samples


# ---------------------------------------------------------------------------
# 3) UART TX bit timing
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_uart_tx_byte(dut):
    """8N1 frame on uo[0]: idle high, start 0, LSB-first data, stop 1.

    uart_tx.pio with clkdiv=1 uses 8 SM cycles per bit (side-set / delay).
    """
    words = load_hex(str(tb.require_hex("uart_tx.hex")))
    assert len(words) == 4, words
    payload = 0x55  # 01010101 — alternating bits, easy to mis-sample

    await tb.start_clock(dut)
    await tb.reset(dut)
    await tb.load_program(dut, words)
    await tb.configure_uart_tx(dut, clkdiv=1)
    await tb.enter_run_mode(dut, sm_enable=True)

    # Reach blocking pull; line is driven mark (1) by side-set on pull once data exists.
    # Before push the SM stalls on pull — pin may be X/0; push then captures frame.
    await ClockCycles(dut.clk, 4)
    await tb.tx_push_byte(dut, payload)

    raw = [(await tb.sample_uo(dut)) & 1 for _ in range(12 + 10 * 8)]

    # Start bit: first index where a run of ≥6 zeros begins after a one (or at 0).
    start = None
    for i in range(len(raw) - 8):
        if all(b == 0 for b in raw[i : i + 6]):
            if i == 0 or raw[i - 1] == 1:
                start = i
                break
    assert start is not None, f"no UART start bit in {raw}"

    def bit_at(index: int) -> int:
        pos = start + index * 8 + 4  # mid-bit
        assert pos < len(raw), f"frame truncated at bit {index}: {raw}"
        return raw[pos]

    assert bit_at(0) == 0, f"start bit, raw={raw}"
    for i in range(8):
        want = (payload >> i) & 1
        got = bit_at(1 + i)
        assert got == want, (
            f"data bit {i}: got {got}, want {want} (payload=0x{payload:02x}) raw={raw}"
        )
    assert bit_at(9) == 1, f"stop bit, raw={raw}"


# ---------------------------------------------------------------------------
# 4) TX FIFO depth / full flag
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_tx_fifo_full(dut):
    """With SM spinning (no pull), depth-2 TX FIFO: 2 pushes OK, then tx_full."""
    words = load_hex(str(tb.require_hex("idle_spin.hex")))

    await tb.start_clock(dut)
    await tb.reset(dut)
    await tb.load_program(dut, words)
    await tb.configure_wrap(dut, 0, 0)
    await tb.enter_run_mode(dut, sm_enable=True)
    await ClockCycles(dut.clk, 4)

    uo = await tb.sample_uo(dut)
    assert not tb.tx_full(uo), "FIFO empty at start"

    await tb.tx_push_byte(dut, 0x11)
    await tb.tx_push_byte(dut, 0x22)

    uo = await tb.sample_uo(dut)
    assert tb.tx_full(uo), f"expected tx_full after 2 pushes, uo=0x{uo:02x}"

    # Third rising edge must not accept data: still full afterward.
    await tb.tx_push_byte(dut, 0x33)
    uo = await tb.sample_uo(dut)
    assert tb.tx_full(uo), "tx_full must remain set when pushing into a full FIFO"


# ---------------------------------------------------------------------------
# 5) Clock divider
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_clkdiv_stretches_blink(dut):
    """clkdiv=N stretches each blink phase by N chip clocks (phase is 2 SM cycles)."""
    words = load_hex(str(tb.require_hex("hello_world.hex")))
    clkdiv = 3
    phase = 2 * clkdiv  # SET + delay[1] each take one SM tick

    await tb.start_clock(dut)
    await tb.reset(dut)
    await tb.load_program(dut, words)
    await tb.configure_blink(dut)
    await tb.configure_clkdiv(dut, clkdiv)
    await tb.enter_run_mode(dut, sm_enable=True)

    samples = await tb.sample_uo0(dut, phase * 4)
    expected = [1] * phase + [0] * phase + [1] * phase + [0] * phase
    assert samples == expected, f"got {samples}, expected {expected}"


# ---------------------------------------------------------------------------
# 6) SM restart
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_sm_restart(dut):
    """Restart resets PC/delay so the blink motif restarts from a clean high phase."""
    words = load_hex(str(tb.require_hex("hello_world.hex")))

    await tb.start_clock(dut)
    await tb.reset(dut)
    await tb.load_program(dut, words)
    await tb.configure_blink(dut)
    await tb.enter_run_mode(dut, sm_enable=True)

    # Advance into the low phase.
    samples = await tb.sample_uo0(dut, 3)
    assert samples == [1, 1, 0], samples

    await tb.pulse_restart(dut)

    # Restart pulse itself burns a few clocks; accept a short align window.
    samples = await tb.sample_uo0(dut, 10)
    ok = any(samples[i : i + 4] == [1, 1, 0, 0] for i in range(4))
    assert ok, f"blink motif missing after restart: {samples}"


# ---------------------------------------------------------------------------
# 7) RX path (IN + autopush + pop + hold ack)
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_rx_autopush_pop_hold(dut):
    """Four `in pins,2` beats build one byte; rx_pop latches it on uo[7:0]."""
    words = load_hex(str(tb.require_hex("rx_shift.hex")))
    # in_shiftdir=0 → left shift into ISR (see kraken_pkg::isr_shift_in).
    pairs = [(1, 0), (1, 1), (0, 0), (1, 0)]  # ui[1:0] each SM cycle
    expected = 0
    for b0, b1 in pairs:
        bits = (b1 << 1) | b0
        expected = ((expected << 2) | (bits & 0x3)) & 0xFF

    await tb.start_clock(dut)
    await tb.reset(dut)
    await tb.load_program(dut, words)
    await tb.configure_rx_shift(dut)
    # Stay disabled until the first pin sample is driven (avoid shifting zeros).
    await tb.enter_run_mode(dut, sm_enable=False)

    for b0, b1 in pairs:
        dut.ui_in.value = (b1 << 1) | b0
        dut.uio_in.value = tb.run_uio(sm_enable=True)
        await RisingEdge(dut.clk)
        await ReadOnly()
        await NextTimeStep()

    # Freeze, then replace the program with an idle spin so pop/ack clocks
    # cannot autopush more RX bytes.
    dut.ui_in.value = 0
    dut.uio_in.value = tb.run_uio(sm_enable=False)
    await RisingEdge(dut.clk)
    await ReadOnly()
    await NextTimeStep()

    uo = int(dut.uo_out.value)
    assert not tb.rx_empty(uo), f"RX FIFO empty after 4 IN beats, uo=0x{uo:02x}"

    idle = load_hex(str(tb.require_hex("idle_spin.hex")))
    await tb.load_program(dut, idle)
    await tb.configure_wrap(dut, 0, 0)
    await tb.enter_run_mode(dut, sm_enable=True)

    await tb.pulse_rx_pop(dut)
    await RisingEdge(dut.clk)
    await ReadOnly()
    held = int(dut.uo_out.value) & 0xFF
    await NextTimeStep()
    assert held == expected, f"RX hold 0x{held:02x}, expected 0x{expected:02x}"

    await tb.pulse_rx_ack(dut)
    uo = await tb.sample_uo(dut)
    assert tb.rx_empty(uo), f"expected empty after pop+ack, uo=0x{uo:02x}"


# ---------------------------------------------------------------------------
# 8) IRQ flags on uo[7:4]
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_irq_set_clear_visible(dut):
    """irq set 0 raises uo[4]; reprogramming to irq clear 0 drops it."""
    set_words = load_hex(str(tb.require_hex("irq_set.hex")))
    clr_words = load_hex(str(tb.require_hex("irq_clear.hex")))

    await tb.start_clock(dut)
    await tb.reset(dut)
    await tb.load_program(dut, set_words)
    await tb.configure_wrap(dut, 0, 0)
    await tb.enter_run_mode(dut, sm_enable=True)

    saw_set = False
    for _ in range(8):
        uo = await tb.sample_uo(dut)
        if tb.irq_flags(uo) & 0x1:
            saw_set = True
            break
    assert saw_set, "IRQ0 never set"

    # Re-enter config, load clear program, run again.
    dut.uio_in.value = 0  # leave run mode briefly
    await RisingEdge(dut.clk)
    await tb.load_program(dut, clr_words)
    await tb.configure_wrap(dut, 0, 0)
    await tb.enter_run_mode(dut, sm_enable=True)

    saw_clr = False
    for _ in range(8):
        uo = await tb.sample_uo(dut)
        if (tb.irq_flags(uo) & 0x1) == 0:
            saw_clr = True
            break
    assert saw_clr, "IRQ0 never cleared"
