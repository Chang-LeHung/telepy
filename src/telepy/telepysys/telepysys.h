// Only for telepysys.c
#ifndef TelepySys_h
#define TelepySys_h

#include "pytypedefs.h"
#include "tree.h"
#include <Python.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define KiB *(1024)

typedef unsigned long long Telepy_time;

#define TELEPYSYS_CHECK(arg, ret)                                             \
    do {                                                                      \
        if (!(arg)) {                                                         \
            return ret;                                                       \
        }                                                                     \
    } while (0)

typedef struct TelePySysState {
    PyTypeObject* sampler_type;
} TelePySysState;

#define BIT_SET(x, n) (x |= (1 << n))
#define BIT_CLEAR(x, n) (x &= ~(1 << n))
#define BIT_CHECK(x, n) (x & (1 << n))

#define VERBOSE 0
#define ENABLED 1
#define IGNORE_FROZEN 2

#define Sample_Enabled(s) (BIT_CHECK((s)->flags, ENABLED))
#define Sample_Disable(s) (BIT_CLEAR((s)->flags, ENABLED))
#define Sample_Enable(s) (BIT_SET((s)->flags, ENABLED))

#define ENABLE_DEBUG(s) (BIT_SET((s)->flags, VERBOSE))
#define DISABLE_DEBUG(s) (BIT_CLEAR((s)->flags, VERBOSE))
#define DEBUG_ENABLED(s) (BIT_CHECK((s)->flags, VERBOSE))

#define ENABLE_IGNORE_FROZEN(s) (BIT_SET((s)->flags, IGNORE_FROZEN))
#define DISABLE_IGNORE_FROZEN(s) (BIT_CLEAR((s)->flags, IGNORE_FROZEN))
#define IGNORE_FROZEN_ENABLED(s) (BIT_CHECK((s)->flags, IGNORE_FROZEN))

#define CHECK_FALG(s, flag) (BIT_CHECK((s)->flags, flag))

typedef struct SamplerObject {
    PyObject_HEAD;
    PyObject* sampling_thread;
    PyObject* sampling_interval;  // in microseconds

    struct StackTree* tree;
    unsigned long sampling_tid;  // thread id of the sampling thread
    unsigned long
        sampling_times;  //  number of times the sampling thread has run

    // profiling data
    Telepy_time acc_sampling_time;  // accumulated sampling time
    Telepy_time life_time;          // sampling thread life time

    uint32_t flags;
} SamplerObject;

#ifdef __cplusplus
}
#endif
#endif