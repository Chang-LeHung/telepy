
#ifndef TelepySys_h
#define TelepySys_h

#ifdef __cplusplus
extern "C" {
#endif

#define KiB *(1024)

#define TELEPYSYS_CHECK(arg, ret)                                             \
    do {                                                                      \
        if (!(arg)) {                                                         \
            return ret;                                                       \
        }                                                                     \
    } while (0)

typedef struct TelePySysState {
    PyObject* threading;
    unsigned long tid;
} TelePySysState;

#ifdef __cplusplus
}
#endif
#endif