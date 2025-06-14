
#pragma once

#include <Python.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef int (*PyMainThreadFunc)(void*);

typedef struct Trampoline {
    PyObject* callable;
    PyObject* args;
    PyObject* kwargs;
} Trampoline;

int
register_func_in_main(PyObject* func, PyObject* args, PyObject* kwargs);

#ifdef __cplusplus
}
#endif