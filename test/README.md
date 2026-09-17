# RTL testbench

[cocotb](https://docs.cocotb.org/en/stable/) suite for Kraken mini. Pin packing comes from [`scripts/kraken_pin_protocol.py`](../scripts/kraken_pin_protocol.py) (shared with the SDK).

```sh
make assemble   # needs pioasm → generated/*.hex
make -B         # full suite
# after hardening: copy netlist → gate_level_netlist.v
make -B GATES=yes
```

| Test | What it locks |
|------|----------------|
| `test_blink_square_wave` | SET blink / pin loader smoke |
| `test_imem_all_eight_words` | Each IMEM[0..7] writable+executable (GL-safe) |
| `test_imem_execute_wrap_at_top` | Wrap/PC at words 6–7 |
| `test_uart_tx_byte` | 8N1 frame on `uo[0]` (SDK `uart_tx.pio`) |
| `test_tx_fifo_full` | Depth-2 TX FIFO + `uo[2]` |
| `test_clkdiv_stretches_blink` | Integer clock divider |
| `test_sm_restart` | `uio[2]` restart |
| `test_rx_autopush_pop_hold` | IN → RX FIFO → pop/hold/ack |
| `test_irq_set_clear_visible` | IRQ flags on `uo[7:4]` |

Shared packing: [`scripts/kraken_pin_protocol.py`](../scripts/kraken_pin_protocol.py). Waveforms: `gtkwave tb.fst tb.gtkw`.
