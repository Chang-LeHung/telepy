// Only for telepysys.c
#ifndef TelepySys_h
#define TelepySys_h

#include "tree.h"
#include "pytypedefs.h"

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


#define Sample_Enabled(s) ((s)->enabled)
#define Sample_Disable(s) ((s)->enabled = 0)
#define Sample_Enable(s) ((s)->enabled = 1)

typedef struct {
    PyObject_HEAD;
    PyObject* sampling_thread;
    PyObject* sampling_interval;  // in microseconds
    PyObject* debug;              // to switch to verbose mode
    struct StackTree* tree;
    unsigned long sampling_tid;  // thread id of the sampling thread
    unsigned long
        sampling_times;  //  number of times the sampling thread has run

    // profiling data
    Telepy_time acc_sampling_time;  // accumulated sampling time
    Telepy_time life_time;          // sampling thread life time

    int enabled;
} SamplerObject;

#ifdef __cplusplus
}
#endif
#endif