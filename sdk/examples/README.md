# Kraken mini SDK examples

Demoboard demos (`.pio` + `.hex` + `run.py`). Copy `sdk/kraken_loader.py` to the board root first.

| Example | GPIO | Notes |
|---------|------|--------|
| [blink](blink/) | `uo[0]` | SET-pin square wave (2 words) |
| [uart_tx](uart_tx/) | `uo[0]` | 8N1 TX (4 words) |
| [i2c_bitstream](i2c_bitstream/) | SDA=`uo[0]`, SCL=`uo[1]` | Host-encoded waveform (1 word; needs pull-ups) |

```bash
make -C sdk/examples          # needs pioasm

mpremote cp sdk/kraken_loader.py :
mpremote cp sdk/examples/blink/blink.hex sdk/examples/blink/run.py :
mpremote run sdk/examples/blink/run.py
```

**Limit:** 8 IMEM words, 2 GPIO. Full pin map: [docs/info.md](../../docs/info.md). Setup: [sdk/README.md](../README.md).
