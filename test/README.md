# RTL testbench

[cocotb](https://docs.cocotb.org/en/stable/) loads a 2-word `hello_world.pio` program through the pin loader (8-word IMEM, addr `uio[4:2]`) and checks `uo[0]` for a 50% square wave.

```sh
make assemble   # needs pioasm
make -B         # RTL sim
# after hardening: copy netlist → gate_level_netlist.v
make -B GATES=yes
```

Waveforms: `gtkwave tb.fst tb.gtkw` or `surfer tb.fst`.

Protocol details: [docs/info.md](../docs/info.md). Demoboard: [sdk/](../sdk/README.md).
