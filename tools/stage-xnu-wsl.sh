#!/usr/bin/env bash
# Stage the SWEET kernel sources and apply the same patches used by macOS CI.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
sdk=${SWEET_IOS_SDK:-$repo/out/deps/sdks/iPhoneOS16.5.sdk}
output=${1:-$repo/out/xnu-wsl-check}
reference=${XNU_REFERENCE:-https://github.com/apple-oss-distributions/xnu.git}
commit=1b191cb58250d0705d8a51287127505aa4bc0789
if [[ ! -r "$sdk/usr/include/TargetConditionals.h" ]]; then
    echo "Set SWEET_IOS_SDK to the unpacked iOS SDK used by build-gl-linux.sh" >&2
    exit 2
fi
if [[ -e "$output" ]]; then
    echo "Choose a new output directory: $output already exists" >&2
    exit 2
fi
mkdir -p "$(dirname "$output")"
git clone --no-checkout --depth 1 --branch xnu-8796.141.3 "$reference" "$output"
git -C "$output" checkout --detach "$commit"

# The HFS source staging helper only uses xcrun to find TargetConditionals.h.
# We supply the equivalent header from the same SDK used for WSL userland.
wrapper=$(mktemp -d)
trap 'rm -f "$wrapper/xcrun"; rmdir "$wrapper"' EXIT
cat > "$wrapper/xcrun" <<'EOF'
#!/bin/sh
if [ "$*" = "--sdk macosx --show-sdk-path" ]; then
    printf '%s\n' "$SWEET_IOS_SDK"
else
    echo "Unexpected xcrun invocation: $*" >&2
    exit 1
fi
EOF
chmod +x "$wrapper/xcrun"
export SWEET_IOS_SDK="$(realpath "$sdk")" MACHINE_CONFIG=SWEET MACOS_VERSION=13.5
export PATH="$wrapper:$PATH"
cd "$output"
for script in "$repo"/xnu/patches/*.sh; do
    bash "$script"
done
for patch in "$repo"/xnu/patches/*.patch "$repo"/xnu/local/*.patch; do
    git apply "$patch"
done
printf 'Patched XNU source staged at %s\n' "$PWD"
