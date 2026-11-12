#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GOW3_ROOT="${GOW3_ARM64_ROOT:-$HOME/Downloads/gow3-arm64-runtime-int}"
GAME_DIR="${UNCHARTED_GAME_DIR:-/Volumes/1TB/Uncharted_The_Nathan_Drake_Collection_CUSA02320_extracted/CUSA02320}"
BUILD_DIR="${UNCHARTED_ARM64_BUILD_DIR:-$REPO_ROOT/out/u1-arm64}"
JOBS="${JOBS:-4}"
RECOMP_BIN="${PS4_RECOMP_BIN:-$GOW3_ROOT/third_party/PS4Recomp/out/ps4-recomp}"
GPU_SOURCE="$GOW3_ROOT/third_party/gow3gpu/gpu"
GPU_PROJECT_SOURCE="$GOW3_ROOT/third_party/gow3gpu"
GPU_PROJECT_COPY="${UNCHARTED_GOW3GPU_SOURCE_DIR:-$BUILD_DIR/gow3gpu-source}"
GPU_SOURCE_COPY="$GPU_PROJECT_COPY/gpu"
GPU_BUILD_DIR="${UNCHARTED_GOW3GPU_BUILD_DIR:-$BUILD_DIR/gow3gpu-build-arm64}"

fail() { printf 'uncharted-arm: %s\n' "$*" >&2; exit 1; }

[[ "$(uname -s)" == Darwin ]] || fail "the ARM64 runtime build currently targets macOS"
[[ "$(uname -m)" == arm64 ]] || fail "run this on Apple Silicon (arm64)"
[[ -f "$GAME_DIR/eboot.bin" ]] || fail "no eboot.bin at UNCHARTED_GAME_DIR: $GAME_DIR"
[[ -d "$GAME_DIR/sce_module" && -d "$GAME_DIR/u1data" ]] || fail "GAME_DIR is not the extracted CUSA02320 folder"
[[ -d "$GOW3_ROOT/runtime" && -f "$GOW3_ROOT/tools/generate_build_ninja.py" ]] || fail "set GOW3_ARM64_ROOT to the GoW3 ARM64 runtime checkout"
[[ -d "$GPU_SOURCE" ]] || fail "missing GoW3 GPU source at $GPU_SOURCE"
command -v cmake >/dev/null || fail "cmake is required"
command -v ninja >/dev/null || fail "ninja is required"
command -v python3 >/dev/null || fail "python3 is required"
command -v rsync >/dev/null || fail "rsync is required"

if [[ ! -x "$RECOMP_BIN" ]]; then
  command -v go >/dev/null || fail "Go is required to build PS4Recomp"
  mkdir -p "$(dirname "$RECOMP_BIN")"
  (cd "$GOW3_ROOT/third_party/PS4Recomp" && go build -o "$RECOMP_BIN" .)
fi

mkdir -p "$BUILD_DIR"
printf '\n== Translating Uncharted 1 for ARM64 ==\n'
"$RECOMP_BIN" --compile=false --app-dir "$GAME_DIR" --out "$BUILD_DIR" "$GAME_DIR/eboot.bin"

# The generated guest code remains local. Copy only the GoW3 runtime and its build tools,
# then patch the generated entry point to use the shared Vulkan bridge and an overridable /app0.
rsync -a --delete "$GOW3_ROOT/runtime/" "$BUILD_DIR/runtime/"
rsync -a --delete "$GOW3_ROOT/gpu/" "$BUILD_DIR/gpu/"
rsync -a --delete "$GOW3_ROOT/3rdparty/" "$BUILD_DIR/3rdparty/"
mkdir -p "$BUILD_DIR/third_party/gow3gpu/gpu" "$BUILD_DIR/tools"
cp "$GPU_SOURCE/gow3gpu.h" "$BUILD_DIR/third_party/gow3gpu/gpu/gow3gpu.h"
cp "$GOW3_ROOT/tools/generate_build_ninja.py" "$BUILD_DIR/tools/"
cp "$GOW3_ROOT/tools/peephole_guest_code.py" "$BUILD_DIR/tools/"
cp "$GOW3_ROOT/tools/tso_crossing_sites.txt" "$BUILD_DIR/tools/"

python3 "$REPO_ROOT/scripts/arm64/patch_generated_runtime.py" \
  --root "$BUILD_DIR" --game-dir "$GAME_DIR" --width 2560 --height 1440
python3 "$BUILD_DIR/tools/generate_build_ninja.py" --root "$BUILD_DIR" \
  --output "$BUILD_DIR/build.ninja"

printf '\n== Building the Uncharted ARM64 app ==\n'
ninja -C "$BUILD_DIR" -j "$JOBS" ps4_app

printf '\n== Building the GoW3 Vulkan runtime adapter ==\n'
rsync -a --delete --exclude=.git "$GPU_PROJECT_SOURCE/" "$GPU_PROJECT_COPY/"
python3 "$REPO_ROOT/scripts/arm64/patch_gow3_gpu.py" --root "$GPU_SOURCE_COPY"
if [[ -f "$GPU_BUILD_DIR/CMakeCache.txt" ]]; then
  CACHED_SOURCE="$(sed -n 's/^CMAKE_HOME_DIRECTORY:INTERNAL=//p' "$GPU_BUILD_DIR/CMakeCache.txt")"
  [[ "$CACHED_SOURCE" == "$GPU_SOURCE_COPY" ]] || fail "GPU build directory was configured from $CACHED_SOURCE; choose a fresh UNCHARTED_GOW3GPU_BUILD_DIR"
fi
cmake -S "$GPU_SOURCE_COPY" -B "$GPU_BUILD_DIR" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DGOW3_LTO=OFF
cmake --build "$GPU_BUILD_DIR" --parallel "$JOBS"

printf '\nBuilt: %s/ps4_app\nGPU:   %s/libgow3gpu.dylib\n' "$BUILD_DIR" "$GPU_BUILD_DIR"
printf 'Run with: %s/scripts/arm64/run.sh\n' "$REPO_ROOT"
