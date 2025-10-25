
#include "inject.h"
#include "object.h"
#include <stdlib.h>

static int
register_main(PyMainThreadFunc func, const Trampoline* trampoline) {
    return Py_AddPendingCall(func, (void*)trampoline);
}


/// @brief run trampoline
/// @param trampoline
/// @return 0 if success, -1 if error
static int
run_trampoline(void* trampoline) {
    Trampoline* arg = (Trampoline*)trampoline;
    PyObject* callable = arg->callable;
    PyObject* result = PyObject_Call(callable, arg->args, arg->kwargs);
    if (result == NULL || PyErr_Occurred()) {
        goto error;
    }
    Py_XDECREF(result);
    Py_XDECREF(callable);
    Py_XDECREF(arg->args);
    Py_XDECREF(arg->kwargs);
    free(trampoline);
    return 0;
error:
    Py_XDECREF(result);
    Py_XDECREF(callable);
    Py_XDECREF(arg->args);
    Py_XDECREF(arg->kwargs);
    free(trampoline);
    return -1;
}


int
register_func_in_main(PyObject* callable, PyObject* args, PyObject* kwargs) {
    Trampoline* trampoline = malloc(sizeof(Trampoline));
    trampoline->callable = callable;
    trampoline->args = args;
    trampoline->kwargs = kwargs;
    return register_main(run_trampoline, trampoline);
}