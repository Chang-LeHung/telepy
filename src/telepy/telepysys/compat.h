#ifndef TELEPYSYS_COMPAT_H
#define TELEPYSYS_COMPAT_H

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

// Python 3.9+ compatibility
#if PY_VERSION_HEX < 0x03090000
#error "Python 3.9 or newer is required"
#endif

// Python 3.9 compatibility
#if PY_VERSION_HEX < 0x030A0000  // Python < 3.10

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

#endif  // TELEPYSYS_COMPAT_H
