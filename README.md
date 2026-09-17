![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# mini-Kraken

![project mascot](imgs/squid_1.png)

> AI was heavily used while creating this

RP2040-style **PIO** tile for [Tiny Tapeout](https://tinytapeout.com): one state machine, **8-word** instruction memory, pin-loaded config, 2 GPIO (`uo[1:0]`). Occupies a **1×2** tile (with silicon art).

| | |
|---|---|
| Top | `tt_um_mini_kraken` |
| Datasheet | [docs/info.md](docs/info.md) |
| Demoboard SDK | [sdk/](sdk/README.md) |
| RTL sim | [test/](test/README.md) |

```sh
# cocotb square-wave smoke test
make -C test -B

# demoboard examples (MicroPython)
make -C sdk/examples
```

Pin protocol, wrap/clkdiv programming, and run-mode pins are documented in the datasheet. Examples: blink, UART TX, I2C bitstream (`sdk/examples/`).
