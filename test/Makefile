# Makefile
# See https://docs.cocotb.org/en/stable/quickstart.html for more info

# defaults
SIM ?= icarus
FST ?= -fst # Use more efficient FST format
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(PWD)/../src

# Match info.yaml source_files (package first for SystemVerilog).
PROJECT_SOURCES = \
  kraken_pkg.sv \
  kraken_alu.sv \
  kraken_decode.sv \
  kraken_fifo.sv \
  kraken_imem.sv \
  kraken_pc.sv \
  kraken_pins.sv \
  kraken_regfile.sv \
  kraken_sm.sv \
  kraken_tt_cfg.sv \
  kraken_tt_loader.sv \
  tt_um_kraken_mini.sv \
  project.v

# Locate Raspberry Pi pioasm (override: make PIOASM=/path/to/pioasm).
ifeq ($(origin PIOASM),undefined)
  ifneq ($(wildcard /Applications/pico-sdk-tools/pioasm/pioasm),)
    PIOASM := /Applications/pico-sdk-tools/pioasm/pioasm
  else
    PIOASM := pioasm
  endif
endif

# Keep cocotb's sim as the default goal (do not put other targets first).
.DEFAULT_GOAL := sim

ifneq ($(GATES),yes)

# RTL simulation:
SIM_BUILD				= sim_build/rtl
VERILOG_SOURCES += $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))
# SystemVerilog (packages, logic, etc.)
COMPILE_ARGS    += -g2012

else

# Gate level simulation:
SIM_BUILD				= sim_build/gl
COMPILE_ARGS    += -DGL_TEST
COMPILE_ARGS    += -DFUNCTIONAL
COMPILE_ARGS    += -DSIM
VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_io/verilog/sg13g2_io.v
VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog/sg13g2_stdcell.v

# this gets copied in by the GDS action workflow
VERILOG_SOURCES += $(PWD)/art_stub.v
VERILOG_SOURCES += $(PWD)/gate_level_netlist.v

endif

# Allow sharing configuration between design and testbench via `include`:
COMPILE_ARGS 		+= -I$(SRC_DIR)

# Include the testbench sources:
VERILOG_SOURCES += $(PWD)/tb.v
TOPLEVEL = tb

# List test modules to run, separated by commas and without the .py suffix:
COCOTB_TEST_MODULES = test_kraken

# Shared pin-protocol module (scripts/) must be importable by cocotb + helpers.
export PYTHONPATH := $(PWD)/../scripts:$(PWD):$(PYTHONPATH)

# Prefer the venv cocotb-config when present (CI/local).
ifneq ($(wildcard $(PWD)/../.venv/bin/cocotb-config),)
  COCOTB_CONFIG := $(PWD)/../.venv/bin/cocotb-config
else
  COCOTB_CONFIG := cocotb-config
endif

# include cocotb's make rules to take care of the simulator setup
include $(shell $(COCOTB_CONFIG) --makefiles)/Makefile.sim

.PHONY: assemble check-hex

SDK_UART_PIO = $(PWD)/../sdk/examples/uart_tx/uart_tx.pio

HEX_ALL = \
  generated/hello_world.hex \
  generated/idle_spin.hex \
  generated/rx_shift.hex \
  generated/irq_set.hex \
  generated/irq_clear.hex \
  generated/uart_tx.hex

# True if PIOASM resolves to an executable (absolute path or on PATH).
PIOASM_OK := $(shell \
  if [ -x "$(PIOASM)" ] || command -v "$(PIOASM)" >/dev/null 2>&1; then echo yes; fi)

check-hex:
	@missing=0; \
	for f in $(HEX_ALL); do \
		if [ ! -f "$$f" ]; then echo "error: missing $$f"; missing=1; fi; \
	done; \
	if [ "$$missing" -ne 0 ]; then \
		echo "error: committed/generated hex files required when pioasm is unavailable"; \
		exit 1; \
	fi

assemble:
ifeq ($(PIOASM_OK),yes)
	mkdir -p generated
	$(PIOASM) -o hex hello_world.pio generated/hello_world.hex
	$(PIOASM) -o hex pio/idle_spin.pio generated/idle_spin.hex
	$(PIOASM) -o hex pio/rx_shift.pio generated/rx_shift.hex
	$(PIOASM) -o hex pio/irq_set.pio generated/irq_set.hex
	$(PIOASM) -o hex pio/irq_clear.pio generated/irq_clear.hex
	$(PIOASM) -o hex $(SDK_UART_PIO) generated/uart_tx.hex
else
	@echo "warning: pioasm not found (PIOASM=$(PIOASM)); using existing hex in generated/"
	@$(MAKE) --no-print-directory check-hex
	@# Refresh mtimes so dependent `sim` rules do not keep rebuilding.
	@touch $(HEX_ALL)
endif

# Rebuild hex when sources change (no-op assemble if pioasm missing but hex present).
$(HEX_ALL): hello_world.pio pio/idle_spin.pio pio/rx_shift.pio pio/irq_set.pio pio/irq_clear.pio $(SDK_UART_PIO)
	$(MAKE) assemble

# Hook assemble so local/CI runs have the pio programs available.
sim: $(HEX_ALL)
