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
using the successful CI build's generated headers. C++ inherited macro
warnings require comparison against the unchanged baseline. This check
does not substitute for the macOS full kernel build or hardware testing.

Expected startup line:
SWEET POWER: PSCI version=0x10001 SYSTEM_OFF feature=0

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
