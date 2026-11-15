# Guacamole builds from WSL

Use a checkout on WSL's Linux filesystem. The Windows fastboot folder can
hold finished images.

On Ubuntu, the build tools are Git, Python 3 with venv, Clang and LLVM with
ld64.lld, GNU Bison and Flex, glslangValidator, Ninja, mtools, cpio,
gcc-aarch64-linux-gnu and binutils-aarch64-linux-gnu. Use an LLVM distribution
that includes llvm-as, llvm-ar, llvm-nm, llvm-strip and llvm-install-name-tool.
Metal also needs Rust 1.98.0 via rustup and its aarch64-apple-ios target.

Point SWEET_IOS_SDK at your unpacked iPhoneOS16.5.sdk and SWEET_LDID at the
Linux ldid executable. SWEET_LLVM_BIN defaults to /usr/bin. Then run:

```sh
bash tools/stage-xnu-wsl.sh
bash tools/build-full-userland-wsl.sh
BOARD=guacamole bash shim/build.sh
```

The first command stages the pinned Apple XNU, HFS, libpthread and BearSSL
sources and applies the kernel patches. It prepares source for inspection and
local compile checks. The second builds and signs the iOS ARM64 graphics
libraries and device services into out/full-userdata/next-userland. The shim
goes to shim/out/Image and starts iOS for every Alert Slider position.

GitHub Actions supplies the linked SWEET kernel and generated headers.
Run **xnu** on main with the default 13.5 / DEVELOPMENT / SWEET settings.
The workflow uses macOS 15 with Xcode 16.4. Download its xnu-kernel artifact
and check SHA256SUMS on WSL. xnu-buildtree provides generated files for
individual kernel compile checks. The full linked kernel still uses the
macOS toolchain.

To prepare the matching boot images once the kernel is available:

```sh
python3 tools/build-full-boot.py --check-kernel /path/to/kernel.development.sweet
python3 tools/build-full-boot.py /path/to/kernel.development.sweet /path/to/stock_boot.img out/full-boot
```

The packer needs the extracted iPhone X ADT under research/ipsw-x and the
six Adreno firmware files under research/gpu/fw. The full userland installer
takes a mounted copy of the clean iOS 16.7.16 HFSX root and the WSL userland
output. With --radio-firmware it enables Wi-Fi and Bluetooth. With
--ssh-bootstrap it enables SSH using a configured Procursus tree.
Use a Linux VM with hfsplus support if WSL cannot mount HFSX. Use mtools and
tools/pull-radio-firmware.py to collect the modem, rmtfs and Bluetooth inputs
locally with the device in TWRP. Those files belong to the individual phone.
Keep them out of Git and CI.

After a phone test, return to TWRP and pull the log from userdata:

```sh
mkdir -p out/device-logs
PART=userdata ADB=/mnt/c/Users/Mox/Desktop/platform-tools/adb.exe \
  tools/sweet-log-pull.sh out/device-logs/corey-first-boot.txt
```

Check the panel mode and measured refresh, the RedwoodGPU startup, and the
SweetMetal2 loader messages. The measured panel rate is separate from the
rate at which CoreAnimation or a game renders frames.
