#!/usr/bin/env python3
"""Make nested SRT shader reads opt into the existing direct-memory fallback."""

from __future__ import annotations

import argparse
from pathlib import Path


OLD = '''        if (build->info.flat_user_data_unresolved) {
            throw std::runtime_error(fmt::format(
                "unsupported ARM64 nested/dynamic SRT read in {} shader {:#x}",
                build->info.hw_stage, build->info.pgm_hash));
        }'''
NEW = '''        if (build->info.flat_user_data_unresolved &&
            !EmulatorSettings.IsDirectMemoryAccessEnabled()) {
            throw std::runtime_error(fmt::format(
                "unsupported ARM64 nested/dynamic SRT read in {} shader {:#x}; "
                "set GOW3_DIRECT_MEMORY_ACCESS=1 to try the guest-memory fallback",
                build->info.hw_stage, build->info.pgm_hash));
        }'''
FALLBACK = '''    if (flatbuf_off_dw == 0) {
        return ctx.OpFunctionCall(ctx.U32[1], ctx.read_const_dynamic, addr, offset);
    }'''
TRACE_HELPER = '''static bool uncharted_trace_srt_shader(const Shader::Info& info) {
    const char* enabled = std::getenv("UNCHARTED_TRACE_SRT");
    return enabled && *enabled && info.pgm_hash == 0x43b8ee5e;
}

'''
RECOMP_TRACE = '''    const auto trace_srt = [&info](const char* phase) {
        const char* enabled = std::getenv("UNCHARTED_TRACE_SRT");
        if (!enabled || !*enabled || info.pgm_hash != 0x43b8ee5e) {
            return;
        }
        std::fprintf(stderr, "[uncharted-arm] SRT trace: TranslateProgram %s\\n", phase);
        std::fflush(stderr);
    };
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="isolated GoW3 GPU source copy")
    args = parser.parse_args()
    cache = args.root / "shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp"
    emitter = args.root / "shadps4/shader_recompiler/backend/spirv/emit_spirv_context_get_set.cpp"
    recompiler = args.root / "shadps4/shader_recompiler/recompiler.cpp"
    compute_pipeline = args.root / "shadps4/video_core/renderer_vulkan/vk_compute_pipeline.cpp"
    cache_text = cache.read_text(encoding="utf-8")
    emitter_text = emitter.read_text(encoding="utf-8")
    recompiler_text = recompiler.read_text(encoding="utf-8")
    compute_text = compute_pipeline.read_text(encoding="utf-8")
    queue_marker = "bool PipelineCache::QueueShader(Program& program, HwStage stage, SwStage l_stage,"
    if TRACE_HELPER not in cache_text:
        if cache_text.count(queue_marker) != 1:
            raise SystemExit(f"could not find QueueShader declaration in {cache}")
        cache_text = cache_text.replace(queue_marker, TRACE_HELPER + queue_marker, 1)
    if NEW in cache_text:
        pass
    elif cache_text.count(OLD) == 1:
        cache.write_text(cache_text.replace(OLD, NEW, 1), encoding="utf-8")
    else:
        raise SystemExit(f"expected one ARM64 SRT rejection guard in {cache}")
    translated_marker = '''        build->ir.emplace(Shader::TranslateProgram(build->code, *build->pools, build->info,
                                                   build->runtime, profile));
'''
    translated_trace = translated_marker + '''        if (uncharted_trace_srt_shader(build->info)) {
            std::fprintf(stderr,
                         "[uncharted-arm] SRT trace: TranslateProgram unresolved=%d direct-memory=%d\\n",
                         build->info.flat_user_data_unresolved,
                         EmulatorSettings.IsDirectMemoryAccessEnabled());
            std::fflush(stderr);
        }
'''
    if translated_trace not in cache_text:
        if cache_text.count(translated_marker) != 1:
            raise SystemExit(f"could not find TranslateProgram capture point in {cache}")
        cache_text = cache_text.replace(translated_marker, translated_trace, 1)
    captured_marker = '''        build->fetch.Capture(build->info);
        return true;
'''
    captured_trace = '''        build->fetch.Capture(build->info);
        if (uncharted_trace_srt_shader(build->info)) {
            std::fputs("[uncharted-arm] SRT trace: guest-data capture completed\\n", stderr);
            std::fflush(stderr);
        }
        return true;
'''
    if captured_trace not in cache_text:
        if cache_text.count(captured_marker) != 1:
            raise SystemExit(f"could not find guest-data capture completion point in {cache}")
        cache_text = cache_text.replace(captured_marker, captured_trace, 1)
    poll_marker = "    if (!capture_job.Poll()) {\n"
    poll_trace = '''    const auto capture_result = capture_job.Poll();
    if (uncharted_trace_srt_shader(build->info)) {
        std::fprintf(stderr,
                     "[uncharted-arm] SRT trace: capture result=%d error=%s\\n",
                     capture_result.has_value(), capture_job.Error().c_str());
        std::fflush(stderr);
    }
    if (!capture_result) {
'''
    if poll_trace not in cache_text:
        if cache_text.count(poll_marker) != 1:
            raise SystemExit(f"could not find shader capture result point in {cache}")
        cache_text = cache_text.replace(poll_marker, poll_trace, 1)
    spirv_marker = '''        auto spv = Shader::Backend::SPIRV::EmitSPIRV(profile, build->runtime, *build->ir,
                                                    build->binding);
'''
    spirv_trace = '''        if (uncharted_trace_srt_shader(build->info)) {
            std::fputs("[uncharted-arm] SRT trace: SPIR-V emission started\\n", stderr);
            std::fflush(stderr);
        }
''' + spirv_marker + '''        if (uncharted_trace_srt_shader(build->info)) {
            std::fprintf(stderr, "[uncharted-arm] SRT trace: SPIR-V emission completed bytes=%zu\\n",
                         spv.size() * sizeof(u32));
            std::fflush(stderr);
        }
'''
    if spirv_trace not in cache_text:
        if cache_text.count(spirv_marker) != 1:
            raise SystemExit(f"could not find SPIR-V emission point in {cache}")
        cache_text = cache_text.replace(spirv_marker, spirv_trace, 1)
    compile_marker = '''        build->module = CompileSPV(patch && EmulatorSettings.IsPatchShaders() ? *patch : spv,
                                    instance.GetDevice());
'''
    compile_trace = '''        if (uncharted_trace_srt_shader(build->info)) {
            std::fputs("[uncharted-arm] SRT trace: Vulkan shader compilation started\\n", stderr);
            std::fflush(stderr);
        }
''' + compile_marker + '''        if (uncharted_trace_srt_shader(build->info)) {
            std::fputs("[uncharted-arm] SRT trace: Vulkan shader compilation completed\\n", stderr);
            std::fflush(stderr);
        }
'''
    if compile_trace not in cache_text:
        if cache_text.count(compile_marker) != 1:
            raise SystemExit(f"could not find Vulkan shader compilation point in {cache}")
        cache_text = cache_text.replace(compile_marker, compile_trace, 1)
    cache.write_text(cache_text, encoding="utf-8")
    if "#include <cstdio>" not in recompiler_text:
        include_marker = '#include "common/logging/classes.h"'
        if recompiler_text.count(include_marker) != 1:
            raise SystemExit(f"could not find standard include point in {recompiler}")
        recompiler_text = recompiler_text.replace(
            include_marker, "#include <cstdio>\n#include <cstdlib>\n\n" + include_marker, 1
        )
    function_marker = '''IR::Program TranslateProgram(const std::span<const u32>& code, Pools& pools, Info& info,
                             RuntimeInfo& runtime_info, const Profile& profile) {
'''
    if RECOMP_TRACE not in recompiler_text:
        if recompiler_text.count(function_marker) != 1:
            raise SystemExit(f"could not find TranslateProgram declaration in {recompiler}")
        recompiler_text = recompiler_text.replace(function_marker, function_marker + RECOMP_TRACE, 1)
    collect_marker = "    Shader::Optimization::CollectShaderInfoPass(program, profile);\n"
    collect_trace = collect_marker + '    trace_srt("after shader-info collection");\n'
    if collect_trace not in recompiler_text:
        if recompiler_text.count(collect_marker) != 1:
            raise SystemExit(f"could not find shader-info collection point in {recompiler}")
        recompiler_text = recompiler_text.replace(collect_marker, collect_trace, 1)
    dump_marker = "    Shader::IR::DumpProgram(program, info);\n"
    dump_trace = dump_marker + '    trace_srt("after final IR dump");\n'
    if dump_trace not in recompiler_text:
        if recompiler_text.count(dump_marker) != 1:
            raise SystemExit(f"could not find final IR dump point in {recompiler}")
        recompiler_text = recompiler_text.replace(dump_marker, dump_trace, 1)
    recompiler.write_text(recompiler_text, encoding="utf-8")
    if "#include <cstdio>" not in compute_text:
        include_marker = "#include <boost/container/small_vector.hpp>"
        if compute_text.count(include_marker) != 1:
            raise SystemExit(f"could not find standard include point in {compute_pipeline}")
        compute_text = compute_text.replace(
            include_marker,
            "#include <cstdio>\n#include <cstdlib>\n\n" + include_marker,
            1,
        )
    pipeline_assert = '''    ASSERT_MSG(pipeline_result == vk::Result::eSuccess, "Failed to create compute pipeline: {}",
               vk::to_string(pipeline_result));
'''
    pipeline_diagnostic = '''    if (pipeline_result != vk::Result::eSuccess) {
        const char* trace = std::getenv("UNCHARTED_TRACE_SRT");
        if (trace && *trace) {
            std::fprintf(stderr,
                         "[uncharted-arm] compute pipeline failure: shader=0x%llx result=%d "
                         "unresolved-srt=%d dma=%d buffers=%zu images=%zu samplers=%zu\\n",
                         static_cast<unsigned long long>(info->pgm_hash),
                         static_cast<int>(pipeline_result), info->flat_user_data_unresolved,
                         info->uses_dma, info->buffers.size(), info->images.size(),
                         info->samplers.size());
            std::fflush(stderr);
        }
    }
''' + pipeline_assert
    if pipeline_diagnostic not in compute_text:
        if compute_text.count(pipeline_assert) != 1:
            raise SystemExit(f"could not find compute pipeline assertion in {compute_pipeline}")
        compute_text = compute_text.replace(pipeline_assert, pipeline_diagnostic, 1)
    compute_pipeline.write_text(compute_text, encoding="utf-8")
    if FALLBACK not in emitter_text:
        raise SystemExit(f"the direct guest-memory fallback is missing from {emitter}")


if __name__ == "__main__":
    main()
