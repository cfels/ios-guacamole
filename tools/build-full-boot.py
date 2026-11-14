#!/usr/bin/env python3
"""Package the full Guacamole kernel with the iOS-only shim and 90 Hz defaults."""

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path, help="Built kernel.development.sweet")
    parser.add_argument("stock_boot", type=Path, help="Boot image from the same phone for its DTB")
    parser.add_argument("output", type=Path, help="New output directory")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    kernel = args.kernel.resolve()
    stock_boot = args.stock_boot.resolve()
    output = args.output.resolve()

    # CI has older builds with some of these features. Check the actual Mach-O,
    # so an old artifact cannot accidentally be shipped as the full build.
    binary = kernel.read_bytes()
    if not binary.startswith(bytes.fromhex("cffaedfe0c000001")):
        parser.error(f"{kernel} must be an ARM64 Mach-O")
    required = {
        "90 Hz panel mode": b"panel switched to 90 Hz",
        "NativeAdreno Metal bridge": b"SweetMetal2",
        "Bluetooth bridge": b"com.sweet.bt.host",
        "display refresh measurement": b"sweetfb_refresh",
    }
    missing = [name for name, marker in required.items() if marker not in binary]
    if missing:
        parser.error(f"{kernel} lacks {', '.join(missing)}")
    stock_boot.stat()
    for name in ("a640_gmu.bin", "a630_sqe.fw", "a640_zap.mdt",
                 "a640_zap.b00", "a640_zap.b01", "a640_zap.b02"):
        if not (repo / "research/gpu/fw" / name).is_file():
            parser.error(f"Missing research/gpu/fw/{name}")
    if not (repo / "research/ipsw-x/d22ap.adt").is_file():
        parser.error("Missing research/ipsw-x/d22ap.adt")

    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, BOARD="guacamole", DUAL_BOOT="0")
    subprocess.run(["bash", str(repo / "shim/build.sh")], env=env, check=True)
    shim = repo / "shim/out/Image"
    adt = output / "guacamole.adt"
    subprocess.run([sys.executable, str(repo / "tools/mkadt.py"), str(adt),
                    "--highmem", "--guacamole"], check=True)

    common = (
        "debug=0xc serial=3 cpus=8 keepsyms=1 -noprogress sweettouch=1 "
        "sweetkeys=1 sweetusb=0 wdt=-1 rd=ufsroot0 ufsroot=userdata "
        "unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin "
        "ufsrw=1 rootrw=1 launchd_unsecure_cache=1 sweetfb_noconsole=1 "
        "sweetlogdump=0 ufslogsecs=1 sweetaudio=0 "
        "sweetmailbox=1 sweetboxpart=rawdump sweetboxroot=1"
    )
    common += f" sweettime={int(time.time())}"
    variants = {
        "boot-corey-full-ios-90hz": "sweetfb90=1 sweetgpu=11 sweetmtl=2 sweetpmem=1 sweetbattery=2",
        "boot-corey-full-ios-60hz": "sweetfb90=0 sweetgpu=11 sweetmtl=2 sweetpmem=1 sweetbattery=2",
    }
    for name, options in variants.items():
        cmdline = f"{common} {options}"
        payload = output / f"{name}.payload"
        image = output / f"{name}.img"
        subprocess.run([sys.executable, str(repo / "tools/mkpayload.py"), str(kernel), str(adt),
                        str(payload), "--cmdline", cmdline], check=True)
        subprocess.run([sys.executable, str(repo / "tools/mkguacboot.py"), str(stock_boot), str(shim),
                        str(image), "--ramdisk", str(payload)], check=True)
        (output / f"{name}.boot-args.txt").write_text(cmdline + "\n")
    (output / "kernel.sha256").write_text(hashlib.sha256(binary).hexdigest() + "\n")


if __name__ == "__main__":
    main()
