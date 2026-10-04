"""Render an original geometric home/appliance icon with no external assets."""

import argparse
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "custom_components/dreame_home/brand"

SVG = '''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
<rect width="256" height="256" rx="48" fill="#007c83"/>
<path d="M42 116L128 42L214 116" fill="none" stroke="white" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>
<rect x="68" y="99" width="120" height="125" rx="20" fill="white"/>
<circle cx="128" cy="165" r="38" fill="#007c83"/>
<circle cx="102" cy="117" r="5" fill="#007c83"/>
<circle cx="119" cy="117" r="5" fill="#007c83"/>
</svg>
'''


def rounded_rect(x, y, left, top, width, height, radius):
    dx = max(left + radius - x, 0, x - (left + width - radius))
    dy = max(top + radius - y, 0, y - (top + height - radius))
    return dx * dx + dy * dy <= radius * radius


def line(x, y, ax, ay, bx, by, radius):
    t = max(0, min(1, ((x - ax) * (bx - ax) + (y - ay) * (by - ay))
                   / ((bx - ax) ** 2 + (by - ay) ** 2)))
    return (x - ax - t * (bx - ax)) ** 2 + (y - ay - t * (by - ay)) ** 2 <= radius ** 2


def color(x, y):
    if not rounded_rect(x, y, 0, 0, 256, 256, 48):
        return 0, 0, 0, 0
    teal = (0, 124, 131, 255)
    if (line(x, y, 42, 116, 128, 42, 8) or line(x, y, 128, 42, 214, 116, 8)
            or rounded_rect(x, y, 68, 99, 120, 125, 20)):
        if ((x - 128) ** 2 + (y - 165) ** 2 <= 38 ** 2
                or (x - 102) ** 2 + (y - 117) ** 2 <= 25
                or (x - 119) ** 2 + (y - 117) ** 2 <= 25):
            return teal
        return 255, 255, 255, 255
    return teal


def chunk(kind, content):
    return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", zlib.crc32(kind + content))


def png(size):
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            samples = [color((x + dx) * 256 / size, (y + dy) * 256 / size)
                       for dx, dy in ((.25, .25), (.75, .25), (.25, .75), (.75, .75))]
            alpha = sum(sample[3] for sample in samples)
            if alpha:
                rows.extend(round(sum(sample[channel] * sample[3] for sample in samples) / alpha)
                            for channel in range(3))
                rows.append(round(alpha / 4))
            else:
                rows.extend((0, 0, 0, 0))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = {"icon.svg": SVG.encode(), "icon.png": png(256), "icon@2x.png": png(512)}
    BRAND.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = BRAND / name
        if args.check:
            if not path.is_file() or path.read_bytes() != data:
                raise SystemExit(f"Brand differs: {name}")
        else:
            path.write_bytes(data)
    print("Verified original brand assets" if args.check else "Created original brand assets")


if __name__ == "__main__":
    main()
