// Only for telepysys.c
#ifndef TelepySys_h
#define TelepySys_h

#include "tree.h"
#include <Python.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define KiB *(1024)

#define BUF_SIZE 16 KiB

typedef unsigned long long Telepy_time;

#define TELEPYSYS_CHECK(arg, ret)                                             \
    do {                                                                      \
        if (!(arg)) {                                                         \
            return ret;                                                       \
        }                                                                     \
    } while (0)

typedef struct TelePySysState {
    PyTypeObject* sampler_type;
    PyTypeObject* async_sampler_type;
} TelePySysState;

#define BIT_SET(x, n) (x |= (1 << n))
#define BIT_CLEAR(x, n) (x &= ~(1 << n))
#define BIT_CHECK(x, n) (x & (1 << n))

#define VERBOSE 0
#define ENABLED 1
#define IGNORE_FROZEN 2
#define SAMPLING 3
#define IGNORE_SELF 4
#define TREE_MODE 5
#define FOCUS_MODE 6
#define TRACE_CFUNCTION 7

#define Sample_Enabled(s) (BIT_CHECK((s)->flags, ENABLED))
#define Sample_Disable(s) (BIT_CLEAR((s)->flags, ENABLED))
#define Sample_Enable(s) (BIT_SET((s)->flags, ENABLED))

#define ENABLE_DEBUG(s) (BIT_SET((s)->flags, VERBOSE))
#define DISABLE_DEBUG(s) (BIT_CLEAR((s)->flags, VERBOSE))
#define DEBUG_ENABLED(s) (BIT_CHECK((s)->flags, VERBOSE))

#define ENABLE_IGNORE_FROZEN(s) (BIT_SET((s)->flags, IGNORE_FROZEN))
#define DISABLE_IGNORE_FROZEN(s) (BIT_CLEAR((s)->flags, IGNORE_FROZEN))
#define IGNORE_FROZEN_ENABLED(s) (BIT_CHECK((s)->flags, IGNORE_FROZEN))

#define ENABLE_SAMPLING(s) (BIT_SET((s)->flags, SAMPLING))
#define DISABLE_SAMPLING(s) (BIT_CLEAR((s)->flags, SAMPLING))
#define SAMPLING_ENABLED(s) (BIT_CHECK((s)->flags, SAMPLING))

#define ENABLE_IGNORE_SELF(s) (BIT_SET((s)->flags, IGNORE_SELF))
#define DISABLE_IGNORE_SELF(s) (BIT_CLEAR((s)->flags, IGNORE_SELF))
#define IGNORE_SELF_ENABLED(s) (BIT_CHECK((s)->flags, IGNORE_SELF))

#define ENABLE_TREE_MODE(s) (BIT_SET((s)->flags, TREE_MODE))
#define DISABLE_TREE_MODE(s) (BIT_CLEAR((s)->flags, TREE_MODE))
#define TREE_MODE_ENABLED(s) (BIT_CHECK((s)->flags, TREE_MODE))

#define ENABLE_FOCUS_MODE(s) (BIT_SET((s)->flags, FOCUS_MODE))
#define DISABLE_FOCUS_MODE(s) (BIT_CLEAR((s)->flags, FOCUS_MODE))
#define FOCUS_MODE_ENABLED(s) (BIT_CHECK((s)->flags, FOCUS_MODE))

#define ENABLE_TRACE_CFUNCTION(s) (BIT_SET((s)->flags, TRACE_CFUNCTION))
#define DISABLE_TRACE_CFUNCTION(s) (BIT_CLEAR((s)->flags, TRACE_CFUNCTION))
#define TRACE_CFUNCTION_ENABLED(s) (BIT_CHECK((s)->flags, TRACE_CFUNCTION))

#define CHECK_FALG(s, flag) (BIT_CHECK((s)->flags, flag))

typedef struct SamplerObject {
    PyObject_HEAD;
    PyObject* sampling_thread;
    PyObject* sampling_interval;  // in microseconds

    struct StackTree* tree;
    unsigned long sampling_tid;  // thread id of the sampling thread
    //  number of times the sampling thread has run
    unsigned long sampling_times;

    // profiling data
    Telepy_time acc_sampling_time;  // accumulated sampling time
    Telepy_time life_time;          // sampling thread life time

    // filtering options
    PyObject* regex_patterns;  // list of compiled regex patterns
    char* std_path;            // path to Python executable from sys.executable

    uint32_t flags;
} SamplerObject;

typedef struct AsyncSamplerObject {
    SamplerObject base;
    // ------------------------------------------------------
    // do not make any changes to the above field
    Telepy_time start;    // start time in microseconds
    Telepy_time end;      // end time in microseconds
    PyObject* threading;  // we can not import it in singal function
    // log buffer, we can not allocate memory in singal function, malloc is not async safe.
    char* buf;
    Py_ssize_t buf_size;
} AsyncSamplerObject;

#ifdef __cplusplus
}
#endif
#endif