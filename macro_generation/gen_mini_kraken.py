#!/usr/bin/env python3
"""Rasterize mini_kraken into IHP TopMetal1 GDS + LEF for Tiny Tapeout.

Pipeline: crop non-white ink → downsample only if needed to fit PDN bay width.
Diagonal thickening is off so 1px eye holes stay open.
"""

from __future__ import annotations

from pathlib import Path

import gdstk
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
# Prefer thicker hand-tuned grid; then thin grid; then high-res squid.
HIGH_RES_PATH = REPO / "imgs" / "squid_1.png"
PNG_THICKER_PATH = HERE / "mini_kraken_thicker.png"
PNG_PATH = HERE / "mini_kraken.png"
OUT_DIR = REPO / "macros"

CELL_NAME = "mini_kraken"

MAX_WIDTH_UM = 30.0
MAX_W_PX = 16  # (16 * 1.7 + 2) = 29.2 µm width budget
MAX_H_PX = 24  # height may span along the PDN column
# Ink fraction in each downsample cell (higher → thinner features / more eye holes).
DOWNSAMPLE_THRESHOLD = 0.35
PIXEL_UM = 1.7
PIXEL_DRAW_UM = 1.75  # keep ≤~1.8 so 1px eye/tentacle holes stay ≥ TM1.b spacing
MARGIN_UM = 1.0

# Off: preserves eye holes (1px gaps). On: better DRC on diagonals, fills eyes.
THICKEN_DIAGONALS = False

ART_LAYER = 126
ART_DATATYPE = 0
BOUNDARY_LAYER = 189
BOUNDARY_DATATYPE = 4


def write_lef(path: Path, cell_name: str, width: float, height: float) -> None:
    path.write_text(
        f"""# LEF generated for {cell_name}
VERSION 5.8 ;
NAMESCASESENSITIVE ON ;
DIVIDERCHAR "/" ;
BUSBITCHARS "[]" ;
UNITS
   DATABASE MICRONS 1000 ;
END UNITS

MACRO {cell_name}
   CLASS BLOCK ;
   FOREIGN {cell_name} 0 0 ;
   SIZE {width:.3f} BY {height:.3f} ;
   SYMMETRY X Y ;
END {cell_name}
"""
    )


def is_metal_pixel(r: int, g: int, b: int, a: int) -> bool:
    """Opaque ink, excluding white paper / background."""
    if a < 128:
        return False
    if r > 240 and g > 240 and b > 240:
        return False
    return True


def crop_to_metal(im: Image.Image) -> Image.Image:
    """Trim transparent and white margins; keep native pixels in the crop."""
    w, h = im.size
    px = im.load()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(h):
        for x in range(w):
            if is_metal_pixel(*px[x, y]):
                xs.append(x)
                ys.append(y)
    if not xs:
        raise SystemExit("no metal pixels found in PNG")
    return im.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1))


def grid_size(crop_w: int, crop_h: int) -> tuple[int, int]:
    """Pick max grid that fits the PDN bay, preserving aspect ratio."""
    tw = min(MAX_W_PX, crop_w)
    th = min(MAX_H_PX, max(1, round(tw * crop_h / crop_w)))
    if tw * PIXEL_UM + 2 * MARGIN_UM >= MAX_WIDTH_UM:
        tw = MAX_W_PX
        th = min(MAX_H_PX, max(1, round(tw * crop_h / crop_w)))
    return tw, th


def downsample_to_grid(im: Image.Image) -> tuple[Image.Image, list[list[bool]]]:
    """Area-average downsample from cropped high-res ink (preserves eye holes)."""
    cw, ch = im.size
    tw, th = grid_size(cw, ch)
    px = im.load()
    mask: list[list[bool]] = []
    for ty in range(th):
        row: list[bool] = []
        ya = ty * ch // th
        yb = (ty + 1) * ch // th
        for tx in range(tw):
            xa = tx * cw // tw
            xb = (tx + 1) * cw // tw
            ink = total = 0
            for y in range(ya, yb):
                for x in range(xa, xb):
                    total += 1
                    if is_metal_pixel(*px[x, y]):
                        ink += 1
            row.append(ink / total >= DOWNSAMPLE_THRESHOLD)
        mask.append(row)

    grid = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    gpx = grid.load()
    for y in range(th):
        for x in range(tw):
            if mask[y][x]:
                gpx[x, y] = (40, 120, 200, 255)
    return grid, mask


def fit_grid(im: Image.Image) -> Image.Image:
    """Keep native pixels when the crop already fits the PDN budget."""
    w, h = im.size
    if w <= MAX_W_PX and h <= MAX_H_PX:
        return im
    tw, th = grid_size(w, h)
    grid, _ = downsample_to_grid(im)
    return grid


def load_source() -> tuple[Image.Image, Path]:
    """Prefer thicker hand-tuned PNG, then thin grid, else squid_1.png."""
    for path in (PNG_THICKER_PATH, PNG_PATH):
        if path.is_file():
            im = Image.open(path).convert("RGBA")
            if im.size[0] <= MAX_W_PX and im.size[1] <= MAX_H_PX:
                return im, path
    if HIGH_RES_PATH.is_file():
        return Image.open(HIGH_RES_PATH).convert("RGBA"), HIGH_RES_PATH
    if PNG_THICKER_PATH.is_file():
        return Image.open(PNG_THICKER_PATH).convert("RGBA"), PNG_THICKER_PATH
    if not PNG_PATH.is_file():
        raise SystemExit(
            f"missing PNG: {PNG_THICKER_PATH} / {PNG_PATH} (and no {HIGH_RES_PATH})"
        )
    return Image.open(PNG_PATH).convert("RGBA"), PNG_PATH


def opaque_mask(im: Image.Image) -> list[list[bool]]:
    w, h = im.size
    pixels = im.load()
    return [[is_metal_pixel(*pixels[x, y]) for x in range(w)] for y in range(h)]


def thicken_diagonals(mask: list[list[bool]]) -> list[list[bool]]:
    h = len(mask)
    w = len(mask[0])
    out = [row[:] for row in mask]
    for y in range(h):
        for x in range(w):
            if mask[y][x]:
                continue
            nw = y > 0 and x > 0 and mask[y - 1][x - 1]
            se = y + 1 < h and x + 1 < w and mask[y + 1][x + 1]
            ne = y > 0 and x + 1 < w and mask[y - 1][x + 1]
            sw = y + 1 < h and x > 0 and mask[y + 1][x - 1]
            if (nw and se) or (ne and sw):
                out[y][x] = True
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    raw, src = load_source()
    # Hand-tuned grids (thin or thicker) are used as-is; high-res gets cropped/downsampled.
    if src in (PNG_PATH, PNG_THICKER_PATH) and raw.size[0] <= MAX_W_PX and raw.size[1] <= MAX_H_PX:
        im = raw
        mask = opaque_mask(im)
        cropped = im
    else:
        cropped = crop_to_metal(raw)
        if cropped.size[0] > MAX_W_PX or cropped.size[1] > MAX_H_PX:
            im, mask = downsample_to_grid(cropped)
        else:
            im = cropped
            mask = opaque_mask(im)
    w, h = im.size

    # Save a processed preview grid (does not overwrite the thicker source).
    grid_path = HERE / "mini_kraken.png"
    im.save(grid_path)
    if THICKEN_DIAGONALS:
        mask = thicken_diagonals(mask)

    lib = gdstk.Library()
    cell = lib.new_cell(CELL_NAME)

    art_w = w * PIXEL_UM
    art_h = h * PIXEL_UM
    width_um = art_w + 2 * MARGIN_UM
    height_um = art_h + 2 * MARGIN_UM
    if width_um >= MAX_WIDTH_UM:
        raise SystemExit(
            f"macro width {width_um:.1f} µm exceeds {MAX_WIDTH_UM} µm "
            f"(grid {w}×{h} @ {PIXEL_UM} µm)"
        )

    cell.add(
        gdstk.rectangle(
            (0, 0),
            (width_um, height_um),
            layer=BOUNDARY_LAYER,
            datatype=BOUNDARY_DATATYPE,
        )
    )

    rects: list[gdstk.Polygon] = []
    metal = 0
    inset = (PIXEL_DRAW_UM - PIXEL_UM) / 2.0
    for y in range(h):
        for x in range(w):
            if not mask[y][x]:
                continue
            x0 = MARGIN_UM + x * PIXEL_UM - inset
            y0 = MARGIN_UM + (h - 1 - y) * PIXEL_UM - inset
            rects.append(
                gdstk.rectangle(
                    (x0, y0),
                    (x0 + PIXEL_DRAW_UM, y0 + PIXEL_DRAW_UM),
                )
            )
            metal += 1

    if not rects:
        raise SystemExit("no opaque pixels found after processing")

    merged = gdstk.boolean(
        rects,
        [],
        "or",
        layer=ART_LAYER,
        datatype=ART_DATATYPE,
    )
    for poly in merged:
        cell.add(poly)

    gds_path = OUT_DIR / f"{CELL_NAME}.gds"
    lef_path = OUT_DIR / f"{CELL_NAME}.lef"
    svg_path = OUT_DIR / f"{CELL_NAME}.svg"

    lib.write_gds(str(gds_path))
    write_lef(lef_path, CELL_NAME, width_um, height_um)
    cell.write_svg(str(svg_path))

    print(f"source: {src} ({raw.size[0]}×{raw.size[1]})")
    print(f"crop:   {cropped.size[0]}×{cropped.size[1]} → grid {w}×{h}")
    print(f"grid:   {grid_path}")
    print(
        f"metal:  {metal} pixels @ {PIXEL_UM} µm "
        f"(draw {PIXEL_DRAW_UM} µm, merged) → {width_um:.1f} x {height_um:.1f} µm"
    )
    print(f"polys:  {len(merged)}")
    print(f"wrote:  {gds_path}")
    print(f"        {lef_path}")
    print(f"        {svg_path}")


if __name__ == "__main__":
    main()
