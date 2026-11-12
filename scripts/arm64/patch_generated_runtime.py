#!/usr/bin/env python3
"""Patch PS4Recomp output for the GoW3 ARM64 host runtime."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def patch_main(path: Path, game_dir: str) -> None:
    source = path.read_text(encoding="utf-8")
    calls, count = re.subn(
        r'ps4_vfs_init\("[^"]*"\);',
        "ps4_vfs_init(ps4_app_dir());",
        source,
    )
    if count != 2:
        raise SystemExit(f"expected 2 generated VFS initialization sites in {path}, found {count}")

    source = calls
    if '#include "gow3gpu_runtime_loader.h"' not in source:
        include_marker = '#include "ps4_vfs.h"'
        if source.count(include_marker) != 1:
            raise SystemExit(f"could not find the generated VFS include in {path}")
        source = source.replace(
            include_marker,
            include_marker + '\n#include "gow3gpu_runtime_loader.h"',
            1,
        )
    if "#include <stdlib.h>" not in source:
        include_marker = '#include "gow3gpu_runtime_loader.h"'
        source = source.replace(include_marker, include_marker + "\n#include <stdlib.h>", 1)

    tls_call = re.compile(r"(?m)^    recomp_init_tls\(ctx,[^\n]*\);$")
    if "ps4_gow3gpu_start_requested_backend(ctx)" not in source:
        call_block = '''
    if (ps4_gow3gpu_start_requested_backend(ctx) != 0) {
        fprintf(stderr, "[uncharted-arm] Vulkan candidate GPU initialization failed\\n");
        exit(2);
    }'''
        source, backend_count = tls_call.subn(lambda match: match.group(0) + call_block, source, count=1)
        if backend_count != 1:
            raise SystemExit(f"could not insert GPU startup after TLS initialization in {path}")
    elif tls_call.search(source) is None:
        raise SystemExit(f"could not verify TLS initialization before GPU startup in {path}")
    app_dir_function = f'''\nstatic const char *ps4_app_dir(void) {{
    const char *override = getenv("PS4_APP_DIR");
    return (override && *override) ? override : {json.dumps(game_dir)};
}}
'''
    marker = "typedef struct {\n    int argc;"
    if source.count(marker) != 1:
        raise SystemExit(f"could not locate the generated main argument structure in {path}")
    source = source.replace(marker, app_dir_function + "\n" + marker, 1)
    path.write_text(source, encoding="utf-8")


def patch_gpu_loader(path: Path, width: int, height: int) -> None:
    source = path.read_text(encoding="utf-8")
    marker = "int ps4_gow3gpu_start_requested_backend(GuestContext *ctx) {"
    if source.count(marker) != 1:
        raise SystemExit(f"expected one GPU loader entry point in {path}")
    source = source.replace(
        marker,
        f'''static uint32_t output_dimension(const char *name, uint32_t fallback) {{
  const char *value = getenv(name);
  if (!value || !*value) return fallback;
  char *end = NULL;
  unsigned long parsed = strtoul(value, &end, 10);
  if (!end || *end || parsed < 640 || parsed > 7680) return fallback;
  return (uint32_t)parsed;
}}

{marker}''',
        1,
    )
    source, width_count = re.subn(r"\.width\s*=\s*1920,", f'.width = output_dimension("PS4_OUTPUT_WIDTH", {width}),', source, count=1)
    source, height_count = re.subn(r"\.height\s*=\s*1080,", f'.height = output_dimension("PS4_OUTPUT_HEIGHT", {height}),', source, count=1)
    if width_count != 1 or height_count != 1:
        raise SystemExit(f"expected one 1920x1080 candidate config in {path}; found width={width_count}, height={height_count}")
    path.write_text(source, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="PS4Recomp output directory")
    parser.add_argument("--game-dir", required=True, help="Host folder mapped to /app0")
    parser.add_argument("--width", type=int, default=2560)
    parser.add_argument("--height", type=int, default=1440)
    args = parser.parse_args()
    if args.width < 640 or args.height < 480 or args.width > 7680 or args.height > 7680:
        parser.error("output dimensions must be in the range 640..7680 by 480..7680")
    patch_main(args.root / "main.c", args.game_dir)
    patch_gpu_loader(args.root / "runtime/core/gow3gpu_runtime_loader.c", args.width, args.height)


if __name__ == "__main__":
    main()
