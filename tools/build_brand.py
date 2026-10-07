"""Keep bundled brand assets consistent with the supplied app icon.

The canonical icon@2x.png retains the supplied image at its native resolution.
Both serving names use the same PNG; Home Assistant scales it for display.
"""

import argparse
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "custom_components/dreame_home/brand"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = (BRAND / "icon@2x.png").read_bytes()
    if (source[:8] != b"\x89PNG\r\n\x1a\n" or source[12:16] != b"IHDR"
            or struct.unpack(">II", source[16:24]) != (512, 512)):
        raise SystemExit("The canonical brand image must be a square 512-pixel PNG")
    target = BRAND / "icon.png"
    if args.check:
        if not target.is_file() or target.read_bytes() != source:
            raise SystemExit("Bundled icon differs from the supplied brand image")
    else:
        target.write_bytes(source)
    print("Verified bundled brand assets" if args.check else "Updated bundled brand assets")


if __name__ == "__main__":
    main()
