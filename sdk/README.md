# Kraken mini — demoboard SDK

MicroPython helpers to program **tt_um_mini_kraken** on a [Tiny Tapeout demoboard](https://tinytapeout.com/guides/get-started-demoboard/). Packing comes from [`scripts/kraken_pin_protocol.py`](../scripts/kraken_pin_protocol.py) (same module cocotb imports — do not fork it).

Works on **FPGA breakout** ([guide](https://tinytapeout.com/guides/fpga-breakout/)) and **ASIC** (`tt.shuttle.tt_um_mini_kraken.enable()`).

| Path | Purpose |
|------|---------|
| `kraken_pin_protocol.py` | Symlink to `scripts/` (copy this file to the board) |
| `kraken_loader.py` | DemoBoard bit-bang API |
| [`examples/`](examples/README.md) | Blink, UART TX, I2C bitstream |

## Quick start

```bash
make -C sdk/examples
mpremote cp scripts/kraken_pin_protocol.py sdk/kraken_loader.py :
mpremote cp sdk/examples/blink/blink.hex sdk/examples/blink/run.py :
mpremote run sdk/examples/blink/run.py
```

Needs [tt-micropython-firmware](https://github.com/TinyTapeout/tt-micropython-firmware). On FPGA, upload the bitstream first:

```bash
tt_fpga.py configure --port /dev/ttyACM0 --upload --name tt_um_mini_kraken --clockrate 1000000
```

## REPL

```python
from ttboard.demoboard import DemoBoard
import kraken_loader as kl

tt = DemoBoard.get()
kl.enable_project(tt)
loader = kl.KrakenLoader(tt)
loader.setup_host_pins()
loader.hardware_reset()
loader.load_program(kl.load_hex("blink.hex"))
loader.configure_blink()
loader.enter_run_mode(sm_enable=True)
tt.clock_project_PWM(1_000_000)
print(loader.sample_uo0(8))  # [1,1,0,0,1,1,0,0]
```

## Pin loader (config `uio[7]=1`)

- **IMEM:** `uio[6]=0`, `uio[4:2]`=addr (0–7), half `uio[1]`, strobe `uio[0]`, data on `ui`
- **Other ops:** `uio[6]=1`, op `uio[5:3]`, strobe `uio[0]`
- **EXEC wrap:** one strobe — `ui[3:0]` bottom, `ui[7:4]` top

Run mode (`uio[7]=0`): `uio[1]`=SM enable, `uio[0]`=TX push. Full map: [docs/info.md](../docs/info.md).

Own programs: `pioasm -o hex myprog.pio myprog.hex` (max **8 words**).

`setup_host_pins()` forces **`ASIC_RP_CONTROL`** so the Pico drives `ui`/`uio`.
