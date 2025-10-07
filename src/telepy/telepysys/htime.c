/**
 * htime.c - High-precision monotonic time utilities
 * 
 * Provides cross-platform functions for getting:
 * - Monotonic wall clock time (CLOCK_MONOTONIC)
 * - CPU time for the current thread/process
 * 
 * All times are returned in nanoseconds for maximum precision.
 */

#include <stdint.h>
#include <time.h>

#if defined(__APPLE__) || defined(__MACH__)
#include <mach/mach_time.h>
#include <sys/time.h>
#define PLATFORM_MACOS
#elif defined(__linux__)
#include <time.h>
#define PLATFORM_LINUX
#elif defined(_WIN32) || defined(_WIN64)
#include <windows.h>
#define PLATFORM_WINDOWS
#endif

/**
 * Get monotonic wall clock time in nanoseconds.
 * This time is not affected by system clock adjustments and always moves forward.
 * 
 * @return Time in nanoseconds since an unspecified starting point
 */
uint64_t
htime_get_monotonic_ns(void) {
#if defined(PLATFORM_LINUX)
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) == 0) {
        return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
    }
    return 0;

#elif defined(PLATFORM_MACOS)
    static mach_timebase_info_data_t timebase_info;
    static int initialized = 0;

    if (!initialized) {
        mach_timebase_info(&timebase_info);
        initialized = 1;
    }

    uint64_t abs_time = mach_absolute_time();
    // Convert to nanoseconds
    return abs_time * timebase_info.numer / timebase_info.denom;

#elif defined(PLATFORM_WINDOWS)
    static LARGE_INTEGER frequency;
    static int initialized = 0;
    LARGE_INTEGER counter;

    if (!initialized) {
        QueryPerformanceFrequency(&frequency);
        initialized = 1;
    }

    QueryPerformanceCounter(&counter);
    // Convert to nanoseconds
    return (uint64_t)((counter.QuadPart * 1000000000ULL) / frequency.QuadPart);

#else
    // Fallback: use gettimeofday (not strictly monotonic but widely available)
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (uint64_t)tv.tv_sec * 1000000000ULL +
           (uint64_t)tv.tv_usec * 1000ULL;
#endif
}

/**
 * Get monotonic wall clock time in microseconds.
 * 
 * @return Time in microseconds since an unspecified starting point
 */
uint64_t
htime_get_monotonic_us(void) {
    return htime_get_monotonic_ns() / 1000ULL;
}

/**
 * Get monotonic wall clock time in milliseconds.
 * 
 * @return Time in milliseconds since an unspecified starting point
 */
uint64_t
htime_get_monotonic_ms(void) {
    return htime_get_monotonic_ns() / 1000000ULL;
}

/**
 * Get CPU time for the current thread in nanoseconds.
 * This measures actual CPU time consumed, not wall clock time.
 * 
 * @return CPU time in nanoseconds
 */
uint64_t
htime_get_thread_cpu_ns(void) {
#if defined(PLATFORM_LINUX)
    struct timespec ts;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts) == 0) {
        return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
    }
    return 0;

#elif defined(PLATFORM_MACOS)
    struct timespec ts;
// macOS supports CLOCK_THREAD_CPUTIME_ID since 10.12
#ifdef CLOCK_THREAD_CPUTIME_ID
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts) == 0) {
        return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
    }
#endif
    // Fallback to process CPU time
    if (clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts) == 0) {
        return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
    }
    return 0;

#elif defined(PLATFORM_WINDOWS)
    FILETIME creation_time, exit_time, kernel_time, user_time;
    if (GetThreadTimes(GetCurrentThread(),
                       &creation_time,
                       &exit_time,
                       &kernel_time,
                       &user_time)) {
        // FILETIME is in 100-nanosecond intervals
        uint64_t kernel = ((uint64_t)kernel_time.dwHighDateTime << 32) |
                          kernel_time.dwLowDateTime;
        uint64_t user = ((uint64_t)user_time.dwHighDateTime << 32) |
                        user_time.dwLowDateTime;
        return (kernel + user) * 100ULL;  // Convert to nanoseconds
    }
    return 0;

#else
    // Fallback: use clock() (less precise)
    return (uint64_t)clock() * 1000000000ULL / CLOCKS_PER_SEC;
#endif
}

/**
 * Get CPU time for the current process in nanoseconds.
 * This measures total CPU time consumed by all threads in the process.
 * 
 * @return CPU time in nanoseconds
 */
uint64_t
htime_get_process_cpu_ns(void) {
#if defined(PLATFORM_LINUX)
    struct timespec ts;
    if (clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts) == 0) {
        return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
    }
    return 0;

#elif defined(PLATFORM_MACOS)
    struct timespec ts;
    if (clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts) == 0) {
        return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
    }
    return 0;

#elif defined(PLATFORM_WINDOWS)
    FILETIME creation_time, exit_time, kernel_time, user_time;
    if (GetProcessTimes(GetCurrentProcess(),
                        &creation_time,
                        &exit_time,
                        &kernel_time,
                        &user_time)) {
        // FILETIME is in 100-nanosecond intervals
        uint64_t kernel = ((uint64_t)kernel_time.dwHighDateTime << 32) |
                          kernel_time.dwLowDateTime;
        uint64_t user = ((uint64_t)user_time.dwHighDateTime << 32) |
                        user_time.dwLowDateTime;
        return (kernel + user) * 100ULL;  // Convert to nanoseconds
    }
    return 0;

#else
    // Fallback: use clock()
    return (uint64_t)clock() * 1000000000ULL / CLOCKS_PER_SEC;
#endif
}

/**
 * Get CPU time for the current thread in microseconds.
 * 
 * @return CPU time in microseconds
 */
uint64_t
htime_get_thread_cpu_us(void) {
    return htime_get_thread_cpu_ns() / 1000ULL;
}

/**
 * Get CPU time for the current process in microseconds.
 * 
 * @return CPU time in microseconds
 */
uint64_t
htime_get_process_cpu_us(void) {
    return htime_get_process_cpu_ns() / 1000ULL;
}
