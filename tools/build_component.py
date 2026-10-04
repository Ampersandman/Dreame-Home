"""Deterministically vendor the API and build a credential-free component ZIP."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "dreamehome"
COMPONENT = ROOT / "custom_components" / "dreame_home"
TARGET = COMPONENT / "api"


def expected_files():
    files = {}
    for path in SOURCE.rglob("*"):
        if path.is_file() and (path.suffix == ".py" or path.suffix == ".json" or path.name == "py.typed"):
            files[path.relative_to(SOURCE).as_posix()] = path.read_bytes().replace(b"\r\n", b"\n")
    files["LICENSE"] = (ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n")
    files["THIRD_PARTY_NOTICES.md"] = (ROOT / "THIRD_PARTY_NOTICES.md").read_bytes().replace(b"\r\n", b"\n")
    files["licenses/ioBroker.dreame.txt"] = (ROOT / "licenses/ioBroker.dreame.txt").read_bytes().replace(b"\r\n", b"\n")
    manifest = {"format_version": 1, "source": "src/dreamehome", "files": {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    files["vendor_manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    return files


def vendor(*, check=False):
    # This helper never recursively removes files. Every write resolves beneath
    # the named component, including paths copied from the source package.
    if TARGET.resolve().parent != COMPONENT.resolve():
        raise ValueError("Unexpected vendoring target")
    expected = expected_files()
    different = []
    for name, data in expected.items():
        target = TARGET / name
        target.resolve().relative_to(TARGET.resolve())
        if target.exists() and target.read_bytes() == data:
            continue
        different.append(name)
        if not check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    extras = [path.relative_to(TARGET).as_posix() for path in TARGET.rglob("*")
              if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
              and path.relative_to(TARGET).as_posix() not in expected]
    if extras:
        raise ValueError(f"Unexpected vendored files require review: {extras}")
    if check and different:
        print("Vendored backend differs: " + ", ".join(different))
        return False
    print(f"{'Verified' if check else 'Vendored'} {len(expected)} backend files")
    return True


def archive():
    output = ROOT / "dist" / "dreame_home.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(COMPONENT.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if path.is_symlink():
                raise ValueError("Component archive must not include symlinks")
            relative = path.relative_to(COMPONENT).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 10, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
    print(f"Built {output}; SHA256 {hashlib.sha256(output.read_bytes()).hexdigest()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--archive", action="store_true")
    args = parser.parse_args()
    if not vendor(check=args.check):
        return 1
    if args.archive:
        archive()
    return 0


if __name__ == "__main__":
    sys.exit(main())
