#ifndef TELEXSYS_COMPAT_H
#define TELEXSYS_COMPAT_H

#include <Python.h>

// For Python 3.10, we need to include frameobject.h to get PyFrame_GetBack
#if PY_VERSION_HEX < 0x030B0000
#include <frameobject.h>
#endif

/*
 * Compatibility layer for different Python versions
 * This file provides backwards compatibility for APIs that were added
 * in newer Python versions.
 */

// Python 3.8+ compatibility
#if PY_VERSION_HEX < 0x03080000
#error "Python 3.8 or newer is required"
#endif

// Python 3.8 and 3.9 compatibility
#if PY_VERSION_HEX < 0x030A0000  // Python < 3.10

/*
 * PyFrame_GetBack() was added in Python 3.9
 * Returns the previous frame in the call stack
 */
#if PY_VERSION_HEX < 0x03090000  // Python 3.8
static inline PyFrameObject*
PyFrame_GetBack(PyFrameObject* frame) {
    PyFrameObject* back = frame->f_back;
    Py_XINCREF(back);
    return back;
}

/*
 * PyFrame_GetCode() was added in Python 3.9
 * Returns the code object for a frame
 */
static inline PyCodeObject*
PyFrame_GetCode(PyFrameObject* frame) {
    PyCodeObject* code = frame->f_code;
    Py_INCREF(code);
    return code;
}
#endif  // Python < 3.9

/*
 * Py_NewRef() was added in Python 3.10
 * Creates a new strong reference to an object
 */
static inline PyObject*
Py_NewRef(PyObject* obj) {
    Py_INCREF(obj);
    return obj;
}

/*
 * Py_IsTrue() was added in Python 3.10
 * Returns 1 if object is True, 0 if False
 */
static inline int
Py_IsTrue(PyObject* obj) {
    return PyObject_IsTrue(obj) == 1;
}

/*
 * PyModule_AddObjectRef() was added in Python 3.10
 * Similar to PyModule_AddObject but steals a reference
 */
static inline int
PyModule_AddObjectRef(PyObject* module, const char* name, PyObject* value) {
    int res;
    Py_XINCREF(value);
    res = PyModule_AddObject(module, name, value);
    if (res < 0) {
        Py_XDECREF(value);
    }
    return res;
}

#endif  // Python < 3.10

// Python 3.10 compatibility
#if PY_VERSION_HEX < 0x030B0000  // Python < 3.11

/*
 * PyFrame_GetBack() is available in Python 3.9+ via frameobject.h
 * but we need to ensure frameobject.h is included (done above)
 */

/*
 * _PyCFunction_CAST() was added in Python 3.11
 * It safely casts function pointers to PyCFunction
 */
#ifndef _PyCFunction_CAST
#define _PyCFunction_CAST(func) ((PyCFunction)(void (*)(void))(func))
#endif

#endif  // Python < 3.11

// Python 3.11+ compatibility
#if PY_VERSION_HEX >= 0x030B0000
// Python 3.11 and later have these functions built-in
// No additional compatibility code needed
#endif

// Python 3.12+ compatibility
#if PY_VERSION_HEX >= 0x030C0000
// Python 3.12 specific compatibility if needed
#endif

// Python 3.13+ compatibility
#if PY_VERSION_HEX >= 0x030D0000
// Python 3.13 specific compatibility if needed
#endif

/*
 * Platform-specific compatibility
 * Windows vs Unix differences
 */

// Platform detection
#if defined(_WIN32) || defined(_WIN64) || defined(__CYGWIN__)
#define TELEX_PLATFORM_WINDOWS 1
#define TELEX_PLATFORM_UNIX 0
#else
#define TELEX_PLATFORM_WINDOWS 0
#define TELEX_PLATFORM_UNIX 1
#endif

#if TELEX_PLATFORM_WINDOWS

// Windows-specific includes
#include <process.h>
#include <windows.h>

// Include time.h before defining timespec to avoid conflicts
#include <time.h>

/*
 * sched_yield() equivalent for Windows
 * On Windows, use SwitchToThread() which yields execution to another thread
 */
static inline int
sched_yield(void) {
    SwitchToThread();
    return 0;
}

/*
 * clock_gettime() implementation for Windows
 * Windows doesn't have clock_gettime, so we implement it using QueryPerformanceCounter
 */

// Note: Modern Windows 10+ SDKs define struct timespec in time.h
// We don't need to define it ourselves for recent SDK versions.
// Only define timespec for very old Windows SDKs that don't have it.
// The guards below prevent redefinition errors.

// Define CLOCK_MONOTONIC for Windows
#ifndef CLOCK_MONOTONIC
#define CLOCK_MONOTONIC 1
#endif

static inline int
clock_gettime(int clk_id, struct timespec* tp) {
    (void)clk_id;  // Unused on Windows

    static LARGE_INTEGER frequency = {0};
    LARGE_INTEGER counter;

    // Initialize frequency on first call
    if (frequency.QuadPart == 0) {
        QueryPerformanceFrequency(&frequency);
    }

    QueryPerformanceCounter(&counter);

    // Convert to seconds and nanoseconds
    tp->tv_sec = (time_t)(counter.QuadPart / frequency.QuadPart);
    tp->tv_nsec =
        (long)(((counter.QuadPart % frequency.QuadPart) * 1000000000LL) /
               frequency.QuadPart);

    return 0;
}

/*
 * nanosleep() implementation for Windows
 * Windows doesn't have nanosleep, so we implement it using Sleep
 */
static inline int
nanosleep(const struct timespec* req, struct timespec* rem) {
    (void)rem;  // Windows Sleep doesn't support remaining time

    // Convert to milliseconds
    DWORD milliseconds = (DWORD)(req->tv_sec * 1000 + req->tv_nsec / 1000000);

    // Sleep for at least 1ms if any time was requested
    if (milliseconds == 0 && (req->tv_sec > 0 || req->tv_nsec > 0)) {
        milliseconds = 1;
    }

    Sleep(milliseconds);
    return 0;
}
#else  // Unix platforms

// Unix-specific includes
#include <pthread.h>
#include <sched.h>
#include <unistd.h>

#endif  // TELEX_PLATFORM_WINDOWS

#endif  // TELEXSYS_COMPAT_H
