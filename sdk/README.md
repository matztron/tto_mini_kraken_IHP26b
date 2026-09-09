# Kraken mini — demoboard SDK

MicroPython helpers to **program the Kraken PIO tile** on a [Tiny Tapeout demoboard](https://tinytapeout.com/guides/get-started-demoboard/) (RP2040/RP2350). Same pin-loader protocol as `test/test.py` and `src/kraken_tt_loader.sv`.

Works on:

- **FPGA breakout** — test before silicon ([FPGA guide](https://tinytapeout.com/guides/fpga-breakout/))
- **ASIC shuttle** — `tt.shuttle.tt_um_mini_kraken.enable()` after chips arrive

## Layout

| Path | Purpose |
|------|---------|
| `kraken_loader.py` | Pin-loader protocol (IMEM, config, run mode, TX FIFO) |
| [`examples/`](examples/README.md) | **Blink**, **UART TX**, and **I2C** demo programs |
| `load_hello_world.py` | Legacy wrapper (prefer `examples/blink/run.py`) |

## Examples

See **[examples/README.md](examples/README.md)** for per-demo wiring and `mpremote` commands.

```bash
make -C sdk/examples          # assemble .pio → .hex
mpremote cp sdk/kraken_loader.py :
mpremote cp sdk/examples/blink/blink.hex sdk/examples/blink/run.py :
mpremote run sdk/examples/blink/run.py
```

## Prerequisites

1. Demoboard running [tt-micropython-firmware](https://github.com/TinyTapeout/tt-micropython-firmware) (flash UF2 from releases).
2. **FPGA:** bitstream uploaded to `/bitstreams/tt_um_mini_kraken.bin`  
   ```bash
   tt_fpga.py configure --port /dev/ttyACM0 --upload --name tt_um_mini_kraken --clockrate 1000000
   ```
3. **ASIC:** project on your shuttle ROM (no bitstream step).

## REPL usage

```python
from ttboard.demoboard import DemoBoard
import kraken_loader as kl

tt = DemoBoard.get()
kl.enable_project(tt)

loader = kl.KrakenLoader(tt)
loader.setup_host_pins()
loader.hardware_reset()

words = kl.load_hex("blink.hex")
loader.load_program(words)
loader.configure_blink()
loader.enter_run_mode(sm_enable=True)

tt.clock_project_PWM(1_000_000)
print(loader.sample_uo0(8))   # expect [1,1,0,0,1,1,0,0]
```

## Loading your own `.pio` program

1. Assemble on the PC: `pioasm -o hex myprog.pio myprog.hex` (max **16 words**).
2. Copy `myprog.hex` to the demoboard.
3. Load and configure wrap / clkdiv / pin counts — see `KrakenLoader` helpers or `examples/`.

## Pin loader recap

Config mode (`uio[7]=1`):

- **IMEM:** `uio[6]=0`, `uio[5:2]`=addr[3:0], `ui[4]`=addr[4], half `uio[1]`, strobe `uio[0]`, data on `ui[7:0]`
- **Other ops:** `uio[6]=1`, op `uio[5:3]`, strobe `uio[0]`; EXEC wrap uses `uio[2]` for bottom/top select

Run mode (`uio[7]=0`):

- `uio[1]` = SM enable · `uio[0]` = TX push · `uo[0:1]` = PIO GPIO out

See `docs/info.md` for the full pin map.

## FPGA note

When an FPGA carrier is detected, the demoboard may start in `ASIC_MANUAL_INPUTS` mode. `KrakenLoader.setup_host_pins()` switches to **`ASIC_RP_CONTROL`** so the Pico drives `ui`/`uio` instead of the DIP switches.
