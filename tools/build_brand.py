"""Copy the supplied light and dark artwork to HA brand names unchanged.

The canonical @2x icons retain the original PNGs, including their native
dimensions and transparency. Home Assistant scales them for display.
"""

import argparse
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "custom_components/dreame_home/brand"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate without writing")
    args = parser.parse_args()
    for prefix in ("", "dark_"):
        name = f"{prefix}icon@2x.png"
        path = BRAND / name
        if not path.is_file():
            raise SystemExit(f"Missing bundled brand image: {name}")
        source = path.read_bytes()
        if (len(source) < 24 or source[:8] != b"\x89PNG\r\n\x1a\n"
                or source[12:16] != b"IHDR"
                or struct.unpack(">II", source[16:24]) not in ((512, 512), (512, 513))):
            raise SystemExit(f"{name} must retain the original 512-pixel-wide PNG")
        for alias in (f"{prefix}icon.png", f"{prefix}logo.png", f"{prefix}logo@2x.png"):
            target = BRAND / alias
            if args.check:
                if not target.is_file() or target.read_bytes() != source:
                    raise SystemExit(f"{alias} differs from the original artwork")
            else:
                target.write_bytes(source)
    print("Verified bundled light and dark brand assets" if args.check else "Updated bundled light and dark brand assets")


if __name__ == "__main__":
    main()
