/*
 * GC Statistics C Extension Module
 * 
 * High-performance implementation of object statistics collection for Python GC.
 * This module provides optimized C functions to replace Python loops in
 * gc_analyzer.py for better performance.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <assert.h>

// Module state structure (currently empty, but following telepysys pattern)
typedef struct {
    // Reserved for future use
    int initialized;
} GCStatsState;

PyDoc_STRVAR(
    gc_stats_doc,
    "High-performance GC statistics collection module.\n\n"
    "This module provides optimized C implementations for garbage collection\n"
    "statistics calculation, replacing performance-critical Python loops.");

// Get module state
static inline GCStatsState*
get_gc_stats_state(PyObject* module) {
    void* state = PyModule_GetState(module);
    assert(state != NULL);
    return (GCStatsState*)state;
}

/*
 * Calculate object statistics from a list of objects.
 * 
 * Args:
 *     objects: List of Python objects to analyze
 *     calculate_memory: Boolean flag to enable memory calculation
 * 
 * Returns:
 *     Dictionary with:
 *     - type_counter: Dict mapping type names to counts
 *     - type_memory: Dict mapping type names to total memory (if calculate_memory)
 *     - total_objects: Total number of objects
 *     - total_memory: Total memory used (if calculate_memory)
 */
static PyObject*
gc_stats_calculate_stats(PyObject* Py_UNUSED(self),
                         PyObject* args,
                         PyObject* kwargs) {
    PyObject* objects = NULL;
    int calculate_memory = 0;
    PyObject* type_counter = NULL;
    PyObject* type_memory = NULL;
    PyObject* sys_module = NULL;
    PyObject* getsizeof = NULL;
    PyObject* result = NULL;
    Py_ssize_t total_objects = 0;
    unsigned long long total_memory = 0;

    static char* kwlist[] = {"objects", "calculate_memory", NULL};

    if (!PyArg_ParseTupleAndKeywords(
            args, kwargs, "O|p", kwlist, &objects, &calculate_memory)) {
        return NULL;
    }

    if (!PyList_Check(objects)) {
        PyErr_SetString(PyExc_TypeError, "objects must be a list");
        return NULL;
    }

    // Create result dictionaries
    type_counter = PyDict_New();
    if (type_counter == NULL) {
        goto error;
    }

    if (calculate_memory) {
        type_memory = PyDict_New();
        if (type_memory == NULL) {
            goto error;
        }
    }

    total_objects = PyList_Size(objects);

    // Get sys.getsizeof for memory calculation
    if (calculate_memory) {
        sys_module = PyImport_ImportModule("sys");
        if (sys_module == NULL) {
            goto error;
        }
        getsizeof = PyObject_GetAttrString(sys_module, "getsizeof");
        if (getsizeof == NULL) {
            goto error;
        }
    }

    // Iterate through objects
    for (Py_ssize_t i = 0; i < total_objects; i++) {
        PyObject* obj = PyList_GetItem(objects, i);
        if (obj == NULL) {
            continue;
        }

        // Get object type name
        PyTypeObject* type = Py_TYPE(obj);
        const char* type_name = type->tp_name;
        PyObject* py_type_name = PyUnicode_FromString(type_name);

        if (py_type_name == NULL) {
            continue;
        }

        // Update count
        PyObject* count = PyDict_GetItem(type_counter, py_type_name);
        if (count == NULL) {
            // First occurrence of this type
            PyObject* one = PyLong_FromLong(1);
            if (one == NULL) {
                Py_DECREF(py_type_name);
                goto error;
            }
            PyDict_SetItem(type_counter, py_type_name, one);
            Py_DECREF(one);
        } else {
            // Increment existing count
            long current_count = PyLong_AsLong(count);
            if (current_count == -1 && PyErr_Occurred()) {
                Py_DECREF(py_type_name);
                goto error;
            }
            PyObject* new_count = PyLong_FromLong(current_count + 1);
            if (new_count == NULL) {
                Py_DECREF(py_type_name);
                goto error;
            }
            PyDict_SetItem(type_counter, py_type_name, new_count);
            Py_DECREF(new_count);
        }

        // Calculate memory if requested
        if (calculate_memory && getsizeof != NULL) {
            PyObject* size_obj =
                PyObject_CallFunctionObjArgs(getsizeof, obj, NULL);
            if (size_obj != NULL) {
                long size = PyLong_AsLong(size_obj);
                if (size != -1 || !PyErr_Occurred()) {
                    total_memory += size;

                    // Update type memory
                    PyObject* mem = PyDict_GetItem(type_memory, py_type_name);
                    if (mem == NULL) {
                        PyObject* size_long = PyLong_FromLong(size);
                        if (size_long == NULL) {
                            Py_DECREF(size_obj);
                            Py_DECREF(py_type_name);
                            goto error;
                        }
                        PyDict_SetItem(type_memory, py_type_name, size_long);
                        Py_DECREF(size_long);
                    } else {
                        long current_mem = PyLong_AsLong(mem);
                        if (current_mem == -1 && PyErr_Occurred()) {
                            Py_DECREF(size_obj);
                            Py_DECREF(py_type_name);
                            goto error;
                        }
                        PyObject* new_mem =
                            PyLong_FromLong(current_mem + size);
                        if (new_mem == NULL) {
                            Py_DECREF(size_obj);
                            Py_DECREF(py_type_name);
                            goto error;
                        }
                        PyDict_SetItem(type_memory, py_type_name, new_mem);
                        Py_DECREF(new_mem);
                    }
                }
                Py_DECREF(size_obj);
            } else {
                // Clear any error from getsizeof
                PyErr_Clear();
            }
        }

        Py_DECREF(py_type_name);
    }

    // Clean up
    Py_XDECREF(getsizeof);
    Py_XDECREF(sys_module);
    getsizeof = NULL;
    sys_module = NULL;

    // Build result dictionary
    result = PyDict_New();
    if (result == NULL) {
        goto error;
    }

    PyDict_SetItemString(result, "type_counter", type_counter);

    PyObject* total_objects_obj = PyLong_FromSsize_t(total_objects);
    if (total_objects_obj == NULL) {
        goto error;
    }
    PyDict_SetItemString(result, "total_objects", total_objects_obj);
    Py_DECREF(total_objects_obj);

    if (calculate_memory) {
        PyDict_SetItemString(result, "type_memory", type_memory);
        PyObject* total_memory_obj = PyLong_FromUnsignedLongLong(total_memory);
        if (total_memory_obj == NULL) {
            goto error;
        }
        PyDict_SetItemString(result, "total_memory", total_memory_obj);
        Py_DECREF(total_memory_obj);
        Py_DECREF(type_memory);
        type_memory = NULL;
    } else {
        Py_INCREF(Py_None);
        PyDict_SetItemString(result, "type_memory", Py_None);
        PyObject* zero = PyLong_FromLong(0);
        if (zero != NULL) {
            PyDict_SetItemString(result, "total_memory", zero);
            Py_DECREF(zero);
        }
    }

    Py_DECREF(type_counter);
    type_counter = NULL;

    return result;

error:
    Py_XDECREF(type_counter);
    Py_XDECREF(type_memory);
    Py_XDECREF(sys_module);
    Py_XDECREF(getsizeof);
    Py_XDECREF(result);
    return NULL;
}

PyDoc_STRVAR(
    calculate_stats_doc,
    "calculate_stats(objects, calculate_memory=False)\n"
    "--\n\n"
    "Calculate object statistics efficiently.\n\n"
    "Args:\n"
    "    objects: List of objects to analyze\n"
    "    calculate_memory: Whether to calculate memory usage\n\n"
    "Returns:\n"
    "    Dict with type_counter, type_memory, total_objects, total_memory");

// Module method definitions
static PyMethodDef gc_stats_methods[] = {
    {"calculate_stats",
     (PyCFunction)(void (*)(void))gc_stats_calculate_stats,
     METH_VARARGS | METH_KEYWORDS,
     calculate_stats_doc},
    {NULL, NULL, 0, NULL}};

// Module initialization function (called by Py_mod_exec slot)
static int
gc_stats_exec(PyObject* module) {
    GCStatsState* state = get_gc_stats_state(module);
    if (state == NULL) {
        return -1;
    }

    // Initialize module state
    state->initialized = 1;

    // Add module version
    if (PyModule_AddStringConstant(module, "__version__", "0.1.0") < 0) {
        return -1;
    }

    return 0;
}

// Module cleanup
static int
gc_stats_clear(PyObject* module) {
    GCStatsState* state = get_gc_stats_state(module);
    if (state) {
        state->initialized = 0;
    }
    return 0;
}

// Module traverse (for garbage collection)
static int
gc_stats_traverse(PyObject* Py_UNUSED(module),
                  visitproc Py_UNUSED(visit),
                  void* Py_UNUSED(arg)) {
    // No Python objects in state currently
    return 0;
}

// Module free
static void
gc_stats_free(void* module) {
    gc_stats_clear((PyObject*)module);
}

// Module slots
static PyModuleDef_Slot gc_stats_slots[] = {
    {Py_mod_exec, gc_stats_exec},
    {0, NULL},
};

// Module definition
static struct PyModuleDef gc_stats_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_gc_stats",
    .m_doc = gc_stats_doc,
    .m_size = sizeof(GCStatsState),
    .m_slots = gc_stats_slots,
    .m_clear = gc_stats_clear,
    .m_free = gc_stats_free,
    .m_methods = gc_stats_methods,
    .m_traverse = gc_stats_traverse,
};

// Module initialization function
PyMODINIT_FUNC
PyInit__gc_stats(void) {
    return PyModuleDef_Init(&gc_stats_module);
}
