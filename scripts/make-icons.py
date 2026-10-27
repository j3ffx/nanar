"""Draws the home screen icons (PNG) from the shapes of web/public/icon.svg.

    uv run python scripts/make-icons.py

Phones want PNG icons, which no browser API draws for us: this rasterizes the logo's few shapes
(rounded square, the N, the dot) with the standard library only, supersampled for smooth edges.
"""

import struct
import zlib
from pathlib import Path

PUBLIC = Path(__file__).resolve().parent.parent / "web" / "public"

BACKGROUND = (0x12, 0x0D, 0x1A)
POPCORN = (0xFF, 0xC2, 0x3D)
CHERRY = (0xFF, 0x5C, 0x7A)

# The N of icon.svg, in its 64-unit square: M20 46V18h6l12 17V18h6v28h-6L26 29v17z
N = [
    (20, 46),
    (20, 18),
    (26, 18),
    (38, 35),
    (38, 18),
    (44, 18),
    (44, 46),
    (38, 46),
    (26, 29),
    (26, 46),
]
DOT = (50.0, 46.0, 4.0)


def inside(polygon: list[tuple[int, int]], x: float, y: float) -> bool:
    hit = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def colour_at(x: float, y: float, radius: float) -> tuple[int, int, int] | None:
    """The colour at (x, y) in the 64-unit square, None outside the rounded square."""
    cx, cy = min(max(x, radius), 64 - radius), min(max(y, radius), 64 - radius)
    if (x - cx) ** 2 + (y - cy) ** 2 > radius**2:
        return None
    dx, dy, r = DOT
    if (x - dx) ** 2 + (y - dy) ** 2 <= r**2:
        return CHERRY
    if inside(N, x, y):
        return POPCORN
    return BACKGROUND


def draw(size: int, *, radius: float, samples: int = 4) -> bytes:
    rows = []
    step = 64 / size
    for py in range(size):
        row = bytearray([0])  # filter: none
        for px in range(size):
            totals = [0, 0, 0, 0]
            for sy in range(samples):
                for sx in range(samples):
                    x = (px + (sx + 0.5) / samples) * step
                    y = (py + (sy + 0.5) / samples) * step
                    colour = colour_at(x, y, radius)
                    if colour is not None:
                        totals[0] += colour[0]
                        totals[1] += colour[1]
                        totals[2] += colour[2]
                        totals[3] += 255
            n = samples * samples
            covered = totals[3] // 255
            if covered:
                row += bytes([totals[0] // covered, totals[1] // covered, totals[2] // covered])
            else:
                row += bytes([0, 0, 0])
            row.append(totals[3] // n)
        rows.append(bytes(row))
    return png(size, b"".join(rows))


def png(size: int, raw: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    # Android masks icons itself; iOS rounds them too: the square is drawn full (radius ~0).
    for name, size, radius in [
        ("icon-192.png", 192, 14.0),
        ("icon-512.png", 512, 14.0),
        ("apple-touch-icon.png", 180, 0.01),
    ]:
        (PUBLIC / name).write_bytes(draw(size, radius=radius))
        print(f"{name} ({size}×{size})")


if __name__ == "__main__":
    main()
