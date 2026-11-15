#!/usr/bin/env bash
# Cross-compile the full Guacamole userland for the iOS 16.7.16 root.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo"
output=${SWEET_GL_OUT:-$repo/out/full-userdata/next-userland}
mkdir -p "$output"
output=$(realpath "$output")
export SWEET_GL_OUT="$output"
export SWEET_IOS_SDK=${SWEET_IOS_SDK:-$repo/out/deps/sdks/iPhoneOS16.5.sdk}
export SWEET_LDID=${SWEET_LDID:-$repo/out/deps/ldid/ldid}
export SWEET_LLVM_BIN=${SWEET_LLVM_BIN:-/usr/bin}
export SWEET_COMPAT_BIN="$repo/out/linux-tools"
export METAL_WORK=${METAL_WORK:-$repo/out/metal-work}
export LLVM_AS=${LLVM_AS:-$SWEET_LLVM_BIN/llvm-as}
export SDKROOT="$SWEET_IOS_SDK"
export CC_aarch64_apple_ios="$SWEET_COMPAT_BIN/clang"
export AR_aarch64_apple_ios="$SWEET_LLVM_BIN/llvm-ar"
for name in cargo glslangValidator bison flex python3 ninja; do
    command -v "$name" >/dev/null || { echo "Missing build tool: $name" >&2; exit 2; }
done
bash "$repo/tools/build-gl-linux.sh" "$repo"
export PATH="$SWEET_COMPAT_BIN:$PATH"
bash "$repo/tools/build-turnip-ios.sh"
bash "$repo/tools/build-m2v-bridge.sh"

cc=("$SWEET_COMPAT_BIN/clang" -isysroot "$SWEET_IOS_SDK" -O2)
build() {
    local name=$1 entitlements=$2
    shift 2
    "${cc[@]}" -o "$output/$name" "$@"
    "$SWEET_LDID" "-S$entitlements" "$output/$name"
}

cd "$repo/userland"
build wland "" wland/{wland,smem,pmem,glink,link,qmi,rmtfs,pdmapper,tftp,scm,wlfw,radio,ipnet,bridge}.c
build btbridge "" bt/btbridge.c wland/pmem.c -Iwland -Ibt
build sweet-displayd jb/sweet-displayd-ents.plist -fobjc-arc -framework Foundation jb/sweet-displayd.m
build sweet-containers "" -framework CoreFoundation jb/sweet-containers.c
build sweet-sysapps sysapps/entitlements.plist -fobjc-arc -framework Foundation sysapps/sweet-sysapps.m
build HakiosAudio "" -bundle -framework CoreFoundation audio/audio_plugin.c
cp audio/audio_plugin.plist "$output/HakiosAudio.plist"

bundle="$output/SweetMetal2.bundle"
mkdir -p "$bundle"
cd "$repo/userland/metal2"
"$SWEET_COMPAT_BIN/clang++" -isysroot "$SWEET_IOS_SDK" -std=c++17 -fobjc-arc -O2 \
    -Wno-deprecated-declarations -bundle -Wl,-dead_strip -o "$bundle/SweetMetal2" \
    SweetMetal2.mm NativeBridgeMetalFrontend.mm "$METAL_WORK/m2v-bridge/ios/libnative_metal_bridge.a" \
    -framework Foundation -framework Metal -framework QuartzCore -framework IOSurface \
    -framework IOKit -framework CoreFoundation
cp Info.plist "$bundle/Info.plist"
cp "$METAL_WORK/turnip/build-ios/src/freedreno/vulkan/libvulkan_freedreno.dylib" "$bundle/"
for binary in "$bundle/SweetMetal2" "$bundle/libvulkan_freedreno.dylib"; do
    "$SWEET_LLVM_BIN/llvm-strip" -x "$binary"
    "$SWEET_LDID" -S "$binary"
done
(
    cd "$output"
    sha256sum sweet-autorun sweet-bbd redwood-gpu-test osmesa-triangle ./*.dylib \
        wland btbridge sweet-displayd sweet-containers sweet-sysapps HakiosAudio HakiosAudio.plist \
        SweetMetal2.bundle/* > SHA256SUMS
    sha256sum -c SHA256SUMS
)
