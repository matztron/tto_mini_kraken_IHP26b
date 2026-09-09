# SPDX-FileCopyrightText: © 2024 Tiny Tapeout / Matthias Musch
# SPDX-License-Identifier: Apache-2.0

PIOASM ?= pioasm
EXAMPLES := blink uart_tx i2c_bitstream

.PHONY: all clean $(EXAMPLES)

all: $(EXAMPLES)

$(EXAMPLES):
	$(PIOASM) -o hex $@/$@.pio $@/$@.hex

clean:
	rm -f $(foreach d,$(EXAMPLES),$(d)/$(d).hex)
