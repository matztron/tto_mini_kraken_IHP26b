# Kraken mini SDK examples

MicroPython demos for the [Tiny Tapeout demoboard](https://tinytapeout.com/guides/get-started-demoboard/). Each example has a `.pio` source, prebuilt `.hex`, and `run.py` loader script.

| Example | GPIO | Description |
|---------|------|-------------|
| [blink](blink/) | `uo[0]` | 50% square wave (SET pin toggle) |
| [uart_tx](uart_tx/) | `uo[0]` | 8N1 serial TX (connect to USB-serial RX) |
| [i2c_master](i2c_master/) | `uo[0]`=SDA, `uo[1]`=SCL | PIO I2C write master (addr + data bytes) |

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

# I2C master (4.7k pull-ups; default write 0x00 to addr 0x50)
mpremote cp sdk/examples/i2c_master/i2c_master.hex sdk/examples/i2c_master/run.py :
mpremote run sdk/examples/i2c_master/run.py
```

## I2C master notes

The [i2c_master](i2c_master/) program (~28 IMEM words) drives START, 8 data bits, ACK, and STOP in PIO. The host pushes **raw I2C bytes** on the TX FIFO — e.g. `(addr7 << 1) & 0xFE`, then data bytes. The current SM handles **one or two payload bytes** after the first pull (addr, optional data).

- Not the unmodified Raspberry Pi `i2c.pio` (that targets 16-bit FIFO records and different pin mapping).
- Kraken drives lines high/low; use **external pull-ups** (not true open drain).
- Scope or logic analyzer on `uo[0]`/`uo[1]` to verify timing.

## Limits

- **32 IMEM words** per program (RP2040 SM depth).
- **2 GPIO pins** on the tile.

See [sdk/README.md](../README.md) for FPGA bitstream setup and pin-loader details.
