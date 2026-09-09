# Kraken mini SDK examples

MicroPython demos for the [Tiny Tapeout demoboard](https://tinytapeout.com/guides/get-started-demoboard/). Each example has a `.pio` source, prebuilt `.hex`, and `run.py` loader script.

| Example | GPIO | Description |
|---------|------|-------------|
| [blink](blink/) | `uo[0]` | 50% square wave (SET pin toggle) |
| [uart_tx](uart_tx/) | `uo[0]` | 8N1 serial TX (connect to USB-serial RX) |
| [i2c_master](i2c_master/) | `uo[0]`=SDA, `uo[1]`=SCL | PIO I2C **single-byte** write master (20 words) |

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

# I2C (4.7k pull-ups; default address byte 0xA0 for device 0x50)
mpremote cp sdk/examples/i2c_master/i2c_master.hex sdk/examples/i2c_master/run.py :
mpremote run sdk/examples/i2c_master/run.py
```

## I2C master notes

`i2c_master` is a **20-word** write-only SM: each TX FIFO byte produces one full frame

`START → 8 bits → ACK → STOP`.

- Push `(addr7 << 1) & 0xFE` for the address+W byte.
- For a data byte, push another FIFO byte (another START…STOP), or use [`i2c_bitstream`](i2c_bitstream/) to send a multi-byte waveform in one stream.
- Kraken drives high/low; use **external pull-ups** (not true open drain).
- ACK is a clocked slot only (slave ACK is not sampled).

## Limits

- **20 IMEM words** per program (Tiny Tapeout 1×2 budget).
- **2 GPIO pins** on the tile.

See [sdk/README.md](../README.md) for FPGA bitstream setup and pin-loader details.
