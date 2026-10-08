"""Validate the bundled light and dark brand PNGs without altering artwork."""

import argparse
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "custom_components/dreame_home/brand"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate without writing (also the default)")
    parser.parse_args()
    for name, size in (("icon.png", 256), ("icon@2x.png", 512),
                       ("dark_icon.png", 256), ("dark_icon@2x.png", 512)):
        path = BRAND / name
        if not path.is_file():
            raise SystemExit(f"Missing bundled brand image: {name}")
        source = path.read_bytes()
        if (len(source) < 24 or source[:8] != b"\x89PNG\r\n\x1a\n"
                or source[12:16] != b"IHDR"
                or struct.unpack(">II", source[16:24]) != (size, size)):
            raise SystemExit(f"{name} must be a square {size}-pixel PNG")
    print("Verified bundled light and dark brand assets")


if __name__ == "__main__":
    main()
