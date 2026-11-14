#!/usr/bin/env bash
# Build the pinned CI source's OpenGL userland on Linux with LLVM + an iOS SDK.
# Dependencies are local; no installation into the host or phone.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SOURCE=${1:-$ROOT/out/ci-source}
export SWEET_IOS_SDK=${SWEET_IOS_SDK:-$ROOT/out/deps/sdks/iPhoneOS16.5.sdk}
export SWEET_LDID=${SWEET_LDID:-$ROOT/out/deps/ldid/ldid}
export SWEET_LLVM_BIN=${SWEET_LLVM_BIN:-/usr/bin}
export SWEET_COMPAT_BIN="$ROOT/out/linux-tools"
mkdir -p "$SWEET_COMPAT_BIN"
test -f "$SWEET_IOS_SDK/SDKSettings.plist"
test -x "$SWEET_LDID"
cat > "$SWEET_COMPAT_BIN/clang" <<'EOF'
#!/bin/sh
for arg do
 case "$arg" in -c|-S|-E|-M|-MM) exec "$SWEET_LLVM_BIN/clang" -target arm64-apple-ios16.0 "$@";; esac
done
exec "$SWEET_LLVM_BIN/clang" -target arm64-apple-ios16.0 -fuse-ld=lld "$@"
EOF
cat > "$SWEET_COMPAT_BIN/clang++" <<'EOF'
#!/bin/sh
for arg do
 case "$arg" in -c|-S|-E|-M|-MM) exec "$SWEET_LLVM_BIN/clang++" -target arm64-apple-ios16.0 "$@";; esac
done
exec "$SWEET_LLVM_BIN/clang++" -target arm64-apple-ios16.0 -fuse-ld=lld "$@"
EOF
cat > "$SWEET_COMPAT_BIN/xcrun" <<'EOF'
#!/bin/sh
if [ "${1:-}" = --sdk ]; then shift 2; fi
case "${1:-}" in
--show-sdk-path) echo "$SWEET_IOS_SDK";;
-f|--find)
 case "$2" in
 clang|clang++) echo "$SWEET_COMPAT_BIN/$2";;
 ar|ranlib|strip) echo "$SWEET_LLVM_BIN/llvm-$2";;
 *) echo "Unsupported xcrun tool: $2" >&2; exit 1;;
 esac;;
clang|clang++) tool=$1; shift; exec "$SWEET_COMPAT_BIN/$tool" "$@";;
*) echo "Unsupported xcrun invocation: $*" >&2; exit 1;;
esac
EOF
cat > "$SWEET_COMPAT_BIN/codesign" <<'EOF'
#!/bin/bash
set -eu
ent=
while [ $# -gt 1 ]; do
 case "$1" in
 -f) shift;;
 -s) test "$2" = -; shift 2;;
 --entitlements) ent=$2; shift 2;;
 *) echo "Unsupported codesign option $1" >&2; exit 1;;
 esac
done
exec "$SWEET_LDID" "-S$ent" "$1"
EOF
chmod +x "$SWEET_COMPAT_BIN/clang" "$SWEET_COMPAT_BIN/clang++" "$SWEET_COMPAT_BIN/xcrun" "$SWEET_COMPAT_BIN/codesign"
ln -sf "$SWEET_LLVM_BIN/llvm-nm" "$SWEET_COMPAT_BIN/nm"
ln -sf "$SWEET_LLVM_BIN/llvm-install-name-tool" "$SWEET_COMPAT_BIN/install_name_tool"
export PATH="$SWEET_COMPAT_BIN:$PATH"
cd "$SOURCE"
bash userland/mesa/mk-mesa.sh
# Only GPU-related helpers for the initial migration.
SDK=$SWEET_IOS_SDK
OUT="$ROOT/out/gl-userland"
mkdir -p "$OUT"
CC=(clang -isysroot "$SDK" -O2 -Wall -Wextra)
build() {
 local dst=$1; shift
 "${CC[@]}" -o "$OUT/$dst" "$@"
 codesign -f -s - "$OUT/$dst"
}
build sweet-autorun userland/autorun/sweet-autorun.c
build redwood-gpu-test userland/gputest/redwood-gpu-test.c -framework IOKit -framework CoreFoundation
build sweet-bbd userland/bbd/sweet-bbd.c
build libsweet-bbd.dylib userland/bbd/bbd-insert.c -dynamiclib -install_name /usr/lib/libsweet-bbd.dylib -framework IOSurface -framework IOKit -framework CoreFoundation
MESA=userland/mesa/build
cp "$MESA/out/libOSMesa.8.dylib" "$OUT/"
build osmesa-triangle userland/gputest/osmesa-triangle.c -I"$MESA/mesa-25.0.7/include" "$OUT/libOSMesa.8.dylib" -Wl,-rpath,@executable_path
python3 userland/gpu/mkeagl.py userland/gpu/eagl_slots.txt "$MESA/out/gl.xml" "$MESA/out/exported-gl.txt" userland/gpu/eagl.c > "$OUT/eagl_gen.h"
build libsweet-gl.dylib userland/gpu/eagl.c userland/gpu/gl_osmesa.c -dynamiclib -install_name /usr/lib/libsweet-gl.dylib -I"$OUT" -Iuserland/gpu -I"$MESA/mesa-25.0.7/include" "$OUT/libOSMesa.8.dylib" -Wl,-rpath,/usr/lib -Wno-unused-but-set-variable -framework OpenGLES -framework IOKit -framework IOSurface -framework CoreFoundation -lobjc
(cd "$OUT" && sha256sum sweet-autorun sweet-bbd redwood-gpu-test osmesa-triangle *.dylib > SHA256SUMS)
