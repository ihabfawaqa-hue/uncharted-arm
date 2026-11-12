#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GOW3_ROOT="${GOW3_ARM64_ROOT:-$HOME/Downloads/gow3-arm64-runtime-int}"
GAME_DIR="${UNCHARTED_GAME_DIR:-/Volumes/1TB/Uncharted_The_Nathan_Drake_Collection_CUSA02320_extracted/CUSA02320}"
BUILD_DIR="${UNCHARTED_ARM64_BUILD_DIR:-$REPO_ROOT/out/u1-arm64}"
GPU_BUILD_DIR="${UNCHARTED_GOW3GPU_BUILD_DIR:-$BUILD_DIR/gow3gpu-build-arm64}"

[[ -f "$BUILD_DIR/ps4_app" ]] || { printf 'Build first with scripts/arm64/build.sh\n' >&2; exit 1; }
[[ -f "$GAME_DIR/eboot.bin" ]] || { printf 'Set UNCHARTED_GAME_DIR to the extracted CUSA02320 folder\n' >&2; exit 1; }
[[ -f "$GPU_BUILD_DIR/libgow3gpu.dylib" ]] || { printf 'Missing GoW3 GPU adapter; run scripts/arm64/build.sh\n' >&2; exit 1; }

export PS4_APP_DIR="$GAME_DIR"
export PS4_OUTPUT_WIDTH="${PS4_OUTPUT_WIDTH:-2560}"
export PS4_OUTPUT_HEIGHT="${PS4_OUTPUT_HEIGHT:-1440}"
export PS4_GOW3GPU_BACKEND=gow3gpu-vulkan
export PS4_GOW3GPU_LIBRARY="${PS4_GOW3GPU_LIBRARY:-$GPU_BUILD_DIR/libgow3gpu.dylib}"
export PS4_GOW3GPU_USER_DIR="${PS4_GOW3GPU_USER_DIR:-$HOME/Library/Application Support/UnchartedArm/CUSA02320}"
export PS4_NO_DIALOGS="${PS4_NO_DIALOGS:-1}"
export PS4_LANG="${PS4_LANG:-English}"
export PS4_PRO="${PS4_PRO:-0}"
# The ARM64 build applies a local guard change so unresolved SRT reads may use
# the renderer's existing BDA guest-memory path for this experimental target.
export GOW3_DIRECT_MEMORY_ACCESS="${GOW3_DIRECT_MEMORY_ACCESS:-1}"

# The Vulkan bridge used for this first ARM64 launch is installed by the GoW3 lab setup.
if [[ -z "${VK_DRIVER_FILES:-}" ]]; then
  ICD="$HOME/Library/Application Support/GOW3Lab/runtime/current/kosmickrisp_icd.json"
  [[ -f "$ICD" ]] && export VK_DRIVER_FILES="$ICD"
fi

mkdir -p "$PS4_GOW3GPU_USER_DIR"
cd "$BUILD_DIR"
exec ./ps4_app "$@"
