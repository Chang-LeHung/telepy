
#include <Python.h>
#include "telepysys.h"
#include "frameobject.h"


#define TELEPYSYS_VERSION "0.1.0"


PyDoc_STRVAR(telepysys_doc, "An utility module for telepysys");

PyDoc_STRVAR(
    telepysys_current_frames_doc,
    "Returns a dictionary where keys are thread IDs and values are "
    "stack frames, including all threads in all Python interpreters.");

static PyObject*
telepysys_current_frames(void) {
    return _PyThread_CurrentFrames();
}


static PyMethodDef telepysys_methods[] = {
    {"current_frames",
     (PyCFunction)telepysys_current_frames,
     METH_NOARGS,
     telepysys_current_frames_doc},
};

static int
telepysys_exec(PyObject* m) {
    if (PyModule_AddStringConstant(m, "__version__", TELEPYSYS_VERSION)) {
        return -1;
    }
    if (PyModule_AddFunctions(m, telepysys_methods)) {
        return -1;
    }
    PyObject* threading = PyImport_ImportModule("threading");
    TELEPYSYS_CHECK(threading, -1);
    TelePySysState* state = (TelePySysState*)PyModule_GetState(m);
    state->threading = threading;
    return 0;
}


static PyModuleDef_Slot telepysys_slots[] = {
    {Py_mod_exec, telepysys_exec},
    {0, NULL},
};


static struct PyModuleDef telepysys = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_telepysys",
    .m_doc = telepysys_doc,
    .m_size = sizeof(TelePySysState),
    .m_slots = telepysys_slots,
};


PyMODINIT_FUNC
PyInit__telepysys(void) {
    return PyModuleDef_Init(&telepysys);
}