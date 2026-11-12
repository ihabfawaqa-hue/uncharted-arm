# Apple Silicon ARM64 status

This is an experimental launch path for Uncharted 1 (CUSA02320) on Apple Silicon. It combines the
Windows port's game and GPU code with the ARM64 AOT runtime and Vulkan adapter from the local GoW3
Remastered project. It is not a supported macOS release and is not playable yet.

## Implemented

- The upstream GPU library builds as a native ARM64 macOS dylib. The macOS window path uses SDL's
  Cocoa/Metal view, Vulkan ICD discovery no longer masks MoltenVK, and x86-only cycle and spin
  instructions have ARM-safe replacements.
- PS4Recomp translates the CUSA02320 eboot.bin, and the separate Apple Silicon app links as
  Mach-O 64-bit executable arm64.
- The current translation found 20,428 reachable functions and 1,560,405 instructions, emitted
  as 114 ARM64 assembly shards and 213 C shards, with 23 unresolved HLE imports.
- The 2560×1440 output is configured by default in both build and run scripts.
- A direct live launch used the extracted game folder, initialized the Apple M2 Vulkan device,
  read Uncharted data packs, started audio services, and handed the first VideoOut flip to the
  Vulkan presenter. It stopped before a title screen could be verified.
- The build scripts reuse the local GoW3 checkout without editing it. Generated guest code,
  game assets, object files, caches and executables stay under ignored out/.

## Launch failure found

The ARM64 shader recompiler reports that shader 0x43b8ee5e has constant-buffer reads its SRT
flattener cannot resolve. The ARM64 path currently flattens direct user-data pointers with
immediate offsets; this shader includes a nested or dynamic read.

An experimental direct-memory fallback was enabled for the live run. The shader translation and IR
dump completed, then Vulkan compute-pipeline creation returned ErrorUnknown. One instrumented run
logged the GPU assertion and process exit code 23. The failing compute pipeline's shader hash was
not captured, so the timing suggests a relationship to shader 0x43b8ee5e but does not prove it.
The DDA fallback is not a launch fix yet.
A later retry also exited with code 23, but its captured output ended after shader translation
without the assertion or a guest-quit trace, so that retry does not identify its exit cause.

Other observations:

- The selected Uncharted user-data folder had zero save entries. No compatible Uncharted save was
  available in that profile; a GoW3 save cannot be loaded by Uncharted.
- Reads for some effect1/*.bin, lut0/default-color-gray.dds, and bpdata1/particle.json paths returned
  fd=-1. It is unknown whether these are optional sidecars.
- Although 2560×1440 is configured, no rendered frame at that resolution was verified onscreen.
- The ARM64 app uses the GoW3 Vulkan runtime adapter because its memory, GNM and VideoOut bridge is
  connected to the AOT runtime. The upstream libbbgpu.dylib build is not wired into that app.

## Build and run

Requirements: Apple Silicon macOS, Xcode Command Line Tools, Go, CMake, Ninja, Python 3, the local
GoW3 ARM64 repository, its built PS4Recomp translator, and a locally extracted CUSA02320 folder.
The GoW3 Vulkan adapter also needs the Vulkan loader, MoltenVK and the KosmicKrisp ICD used by the
current GoW3 runtime setup.

    export GOW3_ARM64_ROOT="$HOME/Downloads/gow3-arm64-runtime-int"
    export UNCHARTED_GAME_DIR="/path/to/CUSA02320"
    scripts/arm64/build.sh
    scripts/arm64/run.sh

The output defaults to out/u1-arm64/. Override it with UNCHARTED_ARM64_BUILD_DIR; use
UNCHARTED_GOW3GPU_BUILD_DIR if the GoW3 adapter should be built elsewhere. The game output
defaults to 2560×1440; set PS4_OUTPUT_WIDTH and PS4_OUTPUT_HEIGHT to change it. The scripts
default UNCHARTED_GAME_DIR to this machine's extracted CUSA02320 path on /Volumes/1TB; set it
explicitly when building elsewhere.

scripts/arm64/build.sh deliberately keeps eboot.bin, module files, assets, translated shards,
object files, pipeline caches and the executable out of Git. It calls the local GoW3 translator,
copies the GoW3 runtime into the ignored build directory, patches the generated entry point to
start the Vulkan adapter, then builds the ARM64 executable and adapter.

run.sh leaves GOW3_DIRECT_MEMORY_ACCESS=0 by default. Set it to 1 to try the experimental SRT
fallback; that path has not reached a title screen. Set UNCHARTED_TRACE_SRT=1 to emit targeted
shader and compute-pipeline checkpoints while investigating the failure.

## Next engineering work

1. Capture the failed compute pipeline's shader hash and stage, then validate its SPIR-V and Vulkan
   descriptor layout.
2. Implement correct nested/dynamic SRT reads or a verified direct-memory fallback. Make shader
   compilation failures recoverable instead of aborting the GPU library.
3. Check the failed data-pack sidecar reads against the extracted folder.
4. Re-run until a visible title screen, 2560×1440 output and interactive input are verified. Then
   test a compatible Uncharted save.
