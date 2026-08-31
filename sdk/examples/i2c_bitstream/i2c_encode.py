# SPDX-FileCopyrightText: © 2024 Tiny Tapeout / Matthias Musch
# SPDX-License-Identifier: Apache-2.0
"""Pack (SDA, SCL) line pairs into bytes for i2c_bitstream.pio.

Each byte holds four 2-bit samples (MSB first). Pin 0 = SDA, pin 1 = SCL.
Use with external pull-ups; Kraken drives lines high or low (not true open drain).
"""


def pairs_to_bytes(pairs):
    """Encode a list of (sda, scl) tuples into TX FIFO bytes."""
    out = []
    acc = 0
    n = 0
    for sda, scl in pairs:
        acc = ((acc << 2) | ((sda & 1) << 1) | (scl & 1)) & 0xFF
        n += 1
        if n == 4:
            out.append(acc)
            acc = 0
            n = 0
    if n:
        out.append((acc << (2 * (4 - n))) & 0xFF)
    return out


def _idle():
    return (1, 1)


def start_pairs():
    """I2C START: SDA falls while SCL is high."""
    return [_idle(), (0, 1), (0, 0)]


def stop_pairs():
    """I2C STOP: SDA rises while SCL is high."""
    return [(0, 0), (0, 1), _idle()]


def write_byte_pairs(value):
    """Eight data bits (MSB first) plus ACK clock slot."""
    pairs = []
    for shift in range(7, -1, -1):
        bit = (value >> shift) & 1
        pairs.append((bit, 0))
        pairs.append((bit, 1))
    # ACK: release SDA, one clock pulse (device pulls SDA low if ACK)
    pairs.append((1, 0))
    pairs.append((1, 1))
    pairs.append((1, 0))
    return pairs


def write_transaction(addr7, data_bytes=()):
    """Build (SDA,SCL) pairs for START + addr + optional data + STOP."""
    pairs = []
    pairs.extend(start_pairs())
    pairs.extend(write_byte_pairs((addr7 << 1) & 0xFE))
    for b in data_bytes:
        pairs.extend(write_byte_pairs(b))
    pairs.extend(stop_pairs())
    return pairs


def encode_write(addr7, data_bytes=()):
    """Return FIFO byte list for a master write transaction."""
    return pairs_to_bytes(write_transaction(addr7, data_bytes))
