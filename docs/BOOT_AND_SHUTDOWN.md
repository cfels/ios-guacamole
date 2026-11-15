# Power-button boot and shutdown

Target is the full iOS 90 Hz direct shim image selected by the user on
2026-11-15. Root is the existing userdata HFSX installation. Logical canvas
is 1125x2436 at 3x, physical display 1440x3120.

## Shutdown implementation

Patch 0267 overrides SweetPlatformExpert::haltRestart for whole-system halt.
At platform startup it queries PSCI_VERSION and, for PSCI 1.0 or later,
PSCI_FEATURES(SYSTEM_OFF). Unsupported firmware reports a failure. After
XNU's existing process termination and VFS unmount path, the handler flushes
the UFS LUN with SYNCHRONIZE CACHE under the driver's I/O mutex and stops
further driver I/O, including the periodic persistent log writer. A failed
flush prevents the power-off call. A successful flush is followed by
PSCI SYSTEM_OFF through SMC. Unexpected return is logged as a failure.

Other platform operations retain the inherited handler. The existing
shim PM8150 PON restart-reason path remains available. Individual CPU halt
and system suspend remain unimplemented.

The existing SweetHID power/volume events are delivered on press and release.
Use Settings > General > Shut Down to test the native shutdown path first.
Then test holding side button with a volume button to request the iPhone X
shutdown interface. Menu presentation and physical shutdown require phone
verification. A short power press must continue to lock/wake the screen.

## Validation

Patch application checked against the pinned, fully patched XNU source.
Modified C and C++ translation units passed Linux clang syntax checking
using the successful CI build's generated headers. The 17 C++ header/macro
warnings match the unchanged baseline; no new warnings were introduced. The full macOS kernel build subsequently passed:
https://github.com/cfels/ios-guacamole/actions/runs/43754879607
Source: aab3a08b62905ccd30d034c68db1744877a90d66.
Hardware shutdown, menu behavior and cold boot remain NOT TESTED.

The startup line reports the actual firmware version, for example:
SWEET POWER: PSCI version=0x10001 SYSTEM_OFF feature=0

The version above is illustrative, not a phone measurement. Feature=0
means the firmware advertises SYSTEM_OFF support.

Expected shutdown progress:
SWEET POWER: final UFS flush before SYSTEM_OFF

Any SYSTEM_OFF returned line is a failure. The final cache flush stops the
persistent log writer, so capture unexpected-return output from the screen.
Verify the device remains off with the USB cable disconnected and again
while connected to a charger. Power it on again and check filesystem
integrity from recovery after a write/shutdown/cold-boot cycle.

## Persistent installation and recovery

Permanent installation is pending an explicit target-slot confirmation.
Read current slot and boot partition sizes in TWRP, back up both boot
partitions, hash the backups, and temporarily boot the new image first.
The earlier boot_a backup alone does not establish the current slot.
Do not change the GPT or the active slot implicitly.

After a successful temporary test, select and confirm the exact boot
partition, verify the image fits, then install there. Reboot from completely
powered off with USB disconnected to verify power-button boot.

Rollback restores the exact saved image to the same confirmed boot
partition through fastboot. Keep the stock/TWRP image and the known-good
90 Hz boot image on the host. A full userdata rebuild is unnecessary for
this kernel-only change.

Read-only preflight on 2026-11-15: active slot A; boot_a and boot_b are
100663296 bytes each. Fresh backups and hashes are in
out/power-build/device/preflight.json. No boot partition or slot was changed.


## Delivered test images

Windows directory: C:/Users/Mox/Desktop/platform-tools/ios16-corey-power.
90 Hz: boot-corey-full-ios-90hz.img.
60 Hz: boot-corey-full-ios-60hz.img.
Both are 21590016 bytes and fit the backed-up boot_a partition.
SHA256SUMS and power-build-manifest.json record the exact inputs and outputs.
INSTALL.txt contains temporary boot and the proposed boot_a installation
and rollback commands. Permanent installation is not yet authorized.

WSL packaging:
```
python3 tools/build-full-boot.py out/power-build/ci-43754879607/kernel.development.sweet out/power-build/device/boot_a.img out/power-build/release
cp shim/out/Image out/power-build/release/shim.Image
python3 tools/verify-power-boot.py out/power-build/ci-43754879607/kernel.development.sweet out/power-build/device/boot_a.img out/power-build/release
```
Use a new output directory when rebuilding. The verifier compares every
embedded kernel segment and the shim, DTB, boot arguments, framebuffer
geometry and Android header checksum. A deliberately corrupted shim was
rejected. All non-random ADT properties match the previous full iOS build;
the missing optional haptics firmware remains an existing limitation.
