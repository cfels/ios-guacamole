#!/usr/bin/env python3
"""Verify shutdown boot images against their kernel, device tree and boot arguments."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import adt
import mkguacboot
import mkpayload


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path)
    parser.add_argument("stock_boot", type=Path)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    kernel = args.kernel.read_bytes()
    shim = (args.directory / "shim.Image").read_bytes()
    require(b"SWEET POWER: final UFS flush before power-off" in kernel,
            "Kernel lacks the shutdown flush path")
    require(b"SWEET POWER: PMIC power-off" in kernel,
            "Kernel lacks the PMIC power-off implementation")
    source = args.kernel.with_name("SOURCE_COMMIT").read_text().strip()
    require(len(source) == 40 and all(c in "0123456789abcdef" for c in source),
            "Missing full kernel source commit")
    original = mkguacboot.parse_v2(args.stock_boot.read_bytes())
    relocated = bytearray(kernel)
    macho = mkpayload.parse_macho(relocated)
    mkpayload.apply_chained_fixups(relocated, macho)
    tree_bytes = (args.directory / "guacamole.adt").read_bytes()
    tree, _ = adt.parse(tree_bytes)
    nodes = []

    def visit(node):
        nodes.append(node)
        for child in node.children:
            visit(child)

    visit(tree)
    display = next(n for n in nodes if n.name == "disp0")
    require(struct.unpack("<I", display.prop("canvas-width"))[0] == 1125,
            "Wrong logical width")
    require(struct.unpack("<I", display.prop("canvas-height"))[0] == 2436,
            "Wrong logical height")
    fbcon = next(n for n in nodes if n.name == "sweet-fbcon")
    for key, expected in (("width", 1440), ("height", 3120), ("stride", 5760)):
        require(struct.unpack("<I", fbcon.prop(key))[0] == expected,
                f"Wrong physical framebuffer {key}")
    manifest = {
        "shim_sha256": digest(shim),
        "kernel_source_commit": source,
        "kernel_sha256": digest(kernel),
        "stock_boot_sha256": digest(args.stock_boot.read_bytes()),
        "adt_sha256": digest(tree_bytes),
        "root_partition": "userdata",
        "logical_canvas": [1125, 2436],
        "physical_panel": [1440, 3120],
        "hardware_validation": "NOT TESTED",
        "images": {},
    }
    for hz in (90, 60):
        name = f"boot-corey-full-ios-{hz}hz"
        image = (args.directory / f"{name}.img").read_bytes()
        header = mkguacboot.parse_v2(image)
        require(header["dtb"] == original["dtb"], "Stock DTB changed")
        kernel_size, _, ramdisk_size = struct.unpack_from("<III", image, 8)
        page = header["page"]
        require(image[page:page + kernel_size] == shim, "Embedded shim mismatch")
        for key in ("kaddr", "raddr", "saddr", "tags", "page", "osver", "dtb_addr"):
            require(header[key] == original[key], f"Boot header changed: {key}")
        offset = page + ((kernel_size + page - 1) // page) * page
        payload = image[offset:offset + ramdisk_size]
        require(payload == (args.directory / f"{name}.payload").read_bytes(),
                "Embedded payload mismatch")
        require(payload[:8] == b"SWEETXNU", "Payload magic mismatch")
        boot_args = payload[0x48:0x2a8].split(b"\0")[0].decode()
        require(boot_args == (args.directory / f"{name}.boot-args.txt").read_text().strip(),
                "Boot argument mismatch")
        tokens = boot_args.split()
        require("ufsroot=userdata" in tokens and "rd=ufsroot0" in tokens,
                "Unexpected root partition")
        require("sweetfb_scale=2" not in tokens and "sweetfb_native=1" not in tokens,
                "Unexpected display geometry override")
        require(f"sweetfb90={int(hz == 90)}" in tokens, "Refresh mode mismatch")
        adt_offset, adt_size = struct.unpack_from("<QQ", payload, 0x20)
        require(payload[adt_offset:adt_offset + adt_size] == tree_bytes, "Embedded ADT mismatch")
        count = struct.unpack_from("<I", payload, 12)[0]
        segments = [s for s in macho["segs"] if s["vmsize"]]
        require(count == len(segments), "Kernel segment count mismatch")
        for i, segment in enumerate(segments):
            address, size, offset, length = struct.unpack_from("<QQQQ", payload, 0x2a8 + 32 * i)
            require((address, size, length) ==
                    (segment["vmaddr"], segment["vmsize"], segment["filesize"]),
                    "Kernel segment metadata mismatch")
            start = segment["fileoff"]
            require(payload[offset:offset + length] == relocated[start:start + length],
                    "Embedded kernel segment mismatch")
        checksum = hashlib.sha1()
        for blob in (image[page:page + kernel_size], payload, b"", b"", header["dtb"]):
            checksum.update(blob)
            checksum.update(struct.pack("<I", len(blob)))
        require(image[576:596] == checksum.digest(), "Android header checksum mismatch")
        manifest["images"][f"{name}.img"] = {
            "sha256": digest(image), "bytes": len(image), "boot_args": boot_args,
        }
        print(f"{name}: verified")
        print(f"boot-args: {boot_args}")
    (args.directory / "power-build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (args.directory / "SHA256SUMS").write_text("".join(
        f"{info['sha256']}  {name}\n" for name, info in manifest["images"].items()))


if __name__ == "__main__":
    main()
