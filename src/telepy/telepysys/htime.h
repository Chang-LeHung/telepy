/**
 * htime.h - High-precision monotonic time utilities
 * 
 * Header file for cross-platform high-precision time functions.
 */

#pragma once


#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Get monotonic wall clock time in nanoseconds.
 * This time is not affected by system clock adjustments and always moves forward.
 * 
 * @return Time in nanoseconds since an unspecified starting point
 */
uint64_t
htime_get_monotonic_ns(void);

/**
 * Get monotonic wall clock time in microseconds.
 * 
 * @return Time in microseconds since an unspecified starting point
 */
uint64_t
htime_get_monotonic_us(void);

/**
 * Get monotonic wall clock time in milliseconds.
 * 
 * @return Time in milliseconds since an unspecified starting point
 */
uint64_t
htime_get_monotonic_ms(void);

/**
 * Get CPU time for the current thread in nanoseconds.
 * This measures actual CPU time consumed, not wall clock time.
 * 
 * @return CPU time in nanoseconds
 */
uint64_t
htime_get_thread_cpu_ns(void);

/**
 * Get CPU time for the current process in nanoseconds.
 * This measures total CPU time consumed by all threads in the process.
 * 
 * @return CPU time in nanoseconds
 */
uint64_t
htime_get_process_cpu_ns(void);

/**
 * Get CPU time for the current thread in microseconds.
 * 
 * @return CPU time in microseconds
 */
uint64_t
htime_get_thread_cpu_us(void);

/**
 * Get CPU time for the current process in microseconds.
 * 
 * @return CPU time in microseconds
 */
uint64_t
htime_get_process_cpu_us(void);

#ifdef __cplusplus
}
#endif
