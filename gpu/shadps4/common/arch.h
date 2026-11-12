// SPDX-FileCopyrightText: Copyright 2024 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#include <thread>

#if defined(__x86_64__) || defined(_M_X64)
#define ARCH_X86_64 1
#elif defined(__aarch64__) || defined(_M_ARM64)
#define ARCH_ARM64 1
#endif

namespace Common {

/// A low-cost hint for short waits that must not yield the current thread.
inline void SpinWait() noexcept {
#if defined(ARCH_ARM64) && !defined(_MSC_VER)
    asm volatile("yield" ::: "memory");
#elif defined(__i386__) || defined(__x86_64__)
    __builtin_ia32_pause();
#elif defined(_MSC_VER) && defined(ARCH_X86_64)
    _mm_pause();
#else
    std::this_thread::yield();
#endif
}

} // namespace Common
