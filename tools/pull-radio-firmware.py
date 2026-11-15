#!/usr/bin/env python3
"""Read the stock OnePlus radio inputs from TWRP into a local build directory."""

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess


BLOCK = "/dev/block/bootdevice/by-name/"
RMTFS = ("modemst1", "modemst2", "fsg", "fsc")
BT_NAMES = ("crbtfw21.tlv", "crnv21.bin")


def adb_text(adb, *args):
    return subprocess.check_output([adb, *args], text=True).strip()


def read_partition(adb, name, target):
    device = BLOCK + name
    size = int(adb_text(adb, "shell", "blockdev", "--getsize64", device))
    if not 0 < size <= 512 * 1024**2:
        raise ValueError(f"{name}: unexpected partition size {size}")
    temporary = target.with_suffix(".part")
    with temporary.open("xb") as output:
        subprocess.run([adb, "exec-out", "cat", device], stdout=output, check=True)
    if temporary.stat().st_size != size:
        raise ValueError(f"{name}: short read")
    native = adb_text(adb, "shell", "sha256sum", device).split()[0]
    with temporary.open("rb") as output:
        captured = hashlib.file_digest(output, "sha256").hexdigest()
    if native != captured:
        raise ValueError(f"{name}: source and copy hashes differ")
    temporary.rename(target)
    print(f"Verified {name} ({size} bytes)")


def extract_fat(image, prefixes, pattern, output):
    env = dict(os.environ, MTOOLS_SKIP_CHECK="1")
    for prefix in prefixes:
        listing = subprocess.run(["mdir", "-b", "-i", str(image), f"::/{prefix}*"],
                                 capture_output=True, text=True, env=env)
        if listing.returncode != 0:
            continue
        for entry in listing.stdout.splitlines():
            source = entry.strip()
            name = source.rsplit("/", 1)[-1].lower()
            if pattern.fullmatch(name) and not (output / name).exists():
                subprocess.run(["mcopy", "-i", str(image), source, str(output / name)],
                               env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--slot", choices=("a", "b"))
    parser.add_argument("output", type=Path, help="New, private output directory in WSL")
    args = parser.parse_args()
    devices = adb_text(args.adb, "devices").splitlines()[1:]
    recovery = [line for line in devices if line.split()[1:] == ["recovery"]]
    if len(recovery) != 1 or len([line for line in devices if line.strip()]) != 1:
        parser.error("Connect exactly one device in TWRP recovery")
    slot = args.slot or adb_text(args.adb, "shell", "getprop", "ro.boot.slot_suffix").removeprefix("_")
    if slot not in ("a", "b"):
        parser.error("Specify the stock firmware slot with --slot a or --slot b")

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name in ("raw", "modem", "rmtfs", "bt"):
        (out / name).mkdir(mode=0o700)
    modem = out / "raw/modem.img"
    bluetooth = out / "raw/bluetooth.img"
    read_partition(args.adb, f"modem_{slot}", modem)
    read_partition(args.adb, f"bluetooth_{slot}", bluetooth)
    for name in RMTFS:
        read_partition(args.adb, name, out / "rmtfs" / f"{name}.img")
    extract_fat(modem, ("image/", ""), re.compile(
        r"modem\.(mdt|b\d+)|modem[ru]w?\.jsn|wlanmdsp\.mbn|bdwlan\.[a-z0-9]+|regdb\.bin"), out / "modem")
    extract_fat(bluetooth, ("image/", ""), re.compile(r"crbtfw21\.tlv|crnv21\.bin"), out / "bt")
    required = [*(out / "bt" / name for name in BT_NAMES),
                *(out / "modem" / name for name in
                  ("modem.mdt", "modem.b00", "modemr.jsn", "modemuw.jsn", "wlanmdsp.mbn", "bdwlan.b0e"))]
    missing = [str(p.relative_to(out)) for p in required if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise SystemExit("Missing radio input files: " + ", ".join(missing))
    print(f"Radio inputs ready in {out}")


if __name__ == "__main__":
    main()
