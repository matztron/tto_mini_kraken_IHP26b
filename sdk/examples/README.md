# Kraken mini SDK examples

MicroPython demos for the [Tiny Tapeout demoboard](https://tinytapeout.com/guides/get-started-demoboard/). Each example has a `.pio` source, prebuilt `.hex`, and `run.py` loader script.

| Example | GPIO | Description |
|---------|------|-------------|
| [blink](blink/) | `uo[0]` | 50% square wave (SET pin toggle) |
| [uart_tx](uart_tx/) | `uo[0]` | 8N1 serial TX (connect to USB-serial RX) |
| [i2c_bitstream](i2c_bitstream/) | `uo[0]`=SDA, `uo[1]`=SCL | Precomputed I2C waveform via TX FIFO |

All examples use `sdk/kraken_loader.py` (copy to the demoboard root).

## Assemble `.pio` → `.hex`

Requires [pioasm](https://github.com/raspberrypi/pico-sdk/tree/master/tools/pioasm):

```bash
make -C sdk/examples
```

## Run on hardware

```bash
# Shared loader
mpremote cp sdk/kraken_loader.py :

# Blink
mpremote cp sdk/examples/blink/blink.hex sdk/examples/blink/run.py :
mpremote run sdk/examples/blink/run.py

# UART (uo[0] → serial adapter RX, common GND)
mpremote cp sdk/examples/uart_tx/uart_tx.hex sdk/examples/uart_tx/run.py :
mpremote run sdk/examples/uart_tx/run.py

# I2C (4.7k pull-ups on SDA/SCL; default write 0x00 to addr 0x50)
mpremote cp sdk/examples/i2c_bitstream/i2c_bitstream.hex \
          sdk/examples/i2c_bitstream/i2c_encode.py \
          sdk/examples/i2c_bitstream/run.py :
mpremote run sdk/examples/i2c_bitstream/run.py
```

## Limits

- **32 IMEM words** (Pico SM depth) — enough for the official 18-instruction `i2c.pio` master when ported.
- **2 GPIO pins** — both examples use `uo[0]` and `uo[1]`; UART and blink share pin 0 only.
- **Open drain** — Kraken drives high/low; use pull-ups and verify levels for I2C targets.

See [sdk/README.md](../README.md) for FPGA bitstream setup and pin-loader details.
