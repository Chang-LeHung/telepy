
#include "inject.h"
#include "object.h"
#include "telepysys.h"
#include "tree.h"
#include "tupleobject.h"
#include <Python.h>
#include <assert.h>
#include <sched.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>


#define TELEPYSYS_VERSION "0.1.0"


static PyObject*
Sampler_start(SamplerObject* self, PyObject* Py_UNUSED(ignored)) {

    if (Sample_Enabled(self)) {
        PyErr_Format(PyExc_RuntimeError,
                     "telepysys is already enabled, call disable first");
        return NULL;
    }

    PyObject* threading_module = PyImport_ImportModule("threading");

    PyObject* thread_class =
        PyObject_GetAttrString(threading_module, "Thread");
    if (thread_class == NULL) {
        Py_DECREF(threading_module);
        return NULL;
    }

    PyObject* start_thread_func =
        PyObject_GetAttrString((PyObject*)self, "_sampling_routine");
    if (start_thread_func == NULL) {
        Py_DECREF(thread_class);
        Py_DECREF(threading_module);
        return NULL;
    }

    PyObject* kwargs = Py_BuildValue("{s:O}", "target", start_thread_func);
    if (kwargs == NULL) {
        Py_DECREF(thread_class);
        Py_DECREF(start_thread_func);
        Py_DECREF(threading_module);
        return NULL;
    }
    PyObject* thread_obj = PyObject_Call(thread_class, PyTuple_New(0), kwargs);
    Py_DECREF(kwargs);
    Py_DECREF(start_thread_func);
    Py_DECREF(thread_class);
    Py_DECREF(threading_module);

    if (thread_obj == NULL) {
        return NULL;
    }
    self->sampling_thread = thread_obj;  // onwership transferred do not free

    Sample_Enable(self);

    PyObject* result = PyObject_CallMethod(thread_obj, "start", NULL);
    if (result == NULL) {
        return NULL;
    }
    Py_DECREF(result);

    PyObject* tid = PyObject_GetAttrString(thread_obj, "_ident");
    if (tid == NULL) {
        return NULL;
    }

    self->sampling_tid = PyLong_AsUnsignedLong(tid);
    if (PyErr_Occurred()) {
        Py_DECREF(tid);
        return NULL;
    }
    Py_DECREF(tid);

    Py_RETURN_NONE;
}


static PyObject*
Sampler_stop(SamplerObject* self, PyObject* Py_UNUSED(ignored)) {
    if (!(CHECK_FALG(self, ENABLED))) {
        PyErr_SetString(PyExc_RuntimeError, "Sampler not started");
        return NULL;
    }
    Sample_Disable(self);  // signal the sampling routine to stop first
    // join the thread
    PyObject* result =
        PyObject_CallMethod(self->sampling_thread, "join", NULL);
    if (result == NULL) {
        return NULL;
    }
    Py_DECREF(result);
    Py_RETURN_NONE;
}

static inline int
PyUnicode_Contain(PyObject* filename, const char* str) {
    const char* filename_cstr = PyUnicode_AsUTF8(filename);
    if (!filename_cstr) {
        return 0;
    }
    return strstr(filename_cstr, str) != NULL;
}

static inline int
PyUnicode_start_with(PyObject* filename, const char* str) {
    const char* f = PyUnicode_AsUTF8(filename);
    if (!f) {
        return 0;
    }
    return strncmp(f, str, strlen(str)) == 0;
}

static inline int
is_stdlib_or_third_party(SamplerObject* sampler, PyObject* filename) {
    // Assert that std_path is initialized
    assert(sampler->std_path != NULL);

    // Check if the file is in standard library or third-party packages
    const char* filepath = PyUnicode_AsUTF8(filename);
    if (!filepath) {
        return 0;
    }

    // Check for site-packages pattern (third-party packages)
    if (strstr(filepath, "site-packages/") != NULL) {
        return 1;
    }

    // Check if the file is in standard library using std_path
    if (strstr(filepath, sampler->std_path) != NULL) {
        return 1;
    }

    return 0;
}

static char*
init_std_path(void) {
    // Get sysconfig.get_path("stdlib") and convert to char*
    char* std_path = NULL;
    PyObject* sysconfig_module = PyImport_ImportModule("sysconfig");
    if (sysconfig_module) {
        PyObject* get_path =
            PyObject_GetAttrString(sysconfig_module, "get_path");
        if (get_path && PyCallable_Check(get_path)) {
            PyObject* args = PyTuple_New(1);
            PyObject* stdlib_str = PyUnicode_FromString("stdlib");
            if (args && stdlib_str) {
                PyTuple_SetItem(
                    args,
                    0,
                    stdlib_str);  // This steals reference to stdlib_str
                PyObject* stdlib_path = PyObject_CallObject(get_path, args);
                if (stdlib_path && PyUnicode_Check(stdlib_path)) {
                    const char* stdlib_path_str =
                        PyUnicode_AsUTF8(stdlib_path);
                    if (stdlib_path_str) {
                        size_t len = strlen(stdlib_path_str);
                        std_path = (char*)malloc(len + 1);
                        if (std_path) {
                            strcpy(std_path, stdlib_path_str);
                        }
                    }
                    Py_DECREF(stdlib_path);
                }
                Py_DECREF(args);  // This will also free stdlib_str
            } else {
                Py_XDECREF(args);
                Py_XDECREF(stdlib_str);
            }
            Py_DECREF(get_path);
        }
        Py_DECREF(sysconfig_module);
    }
    return std_path;
}

static inline int
has_content_after_thread_name(const char* buf, Py_ssize_t thread_name_size) {
    // Check if there's meaningful content after the thread name and semicolon
    // buf format: "ThreadName;actual_stack_content"
    // thread_name_size includes the semicolon
    if (buf == NULL || thread_name_size < 0) {
        return 0;
    }

    // Check if there's at least one non-whitespace character after thread name
    const char* content_start = buf + thread_name_size;
    if (*content_start != '\0' && *content_start != ' ' &&
        *content_start != '\t' && *content_start != '\n' &&
        *content_start != '\r') {
        return 1;  // Found meaningful content
    }

    return 0;  // No meaningful content after thread name
}

static inline int
matches_regex_patterns(PyObject* filename, PyObject* regex_patterns) {
    if (regex_patterns == NULL || regex_patterns == Py_None) {
        return 1;  // No patterns means match everything
    }

    if (!PyList_Check(regex_patterns)) {
        return 1;  // Invalid patterns, default to match
    }

    Py_ssize_t pattern_count = PyList_Size(regex_patterns);
    if (pattern_count == 0) {
        return 1;  // Empty list means match everything
    }

    const char* filepath = PyUnicode_AsUTF8(filename);
    if (!filepath) {
        return 0;
    }

    for (Py_ssize_t i = 0; i < pattern_count; i++) {
        PyObject* pattern = PyList_GetItem(regex_patterns, i);
        if (pattern == NULL) {
            continue;
        }

        // Call pattern.search(filepath)
        PyObject* result =
            PyObject_CallMethod(pattern, "search", "s", filepath);
        if (result != NULL) {
            int matched = (result != Py_None);
            Py_DECREF(result);
            if (matched) {
                return 1;  // Found a match
            }
        } else {
            PyErr_Clear();  // Clear any errors from regex matching
        }
    }

    return 0;  // No patterns matched
}


// return 0 on success, other on failure and set python error
static int
call_stack(SamplerObject* self,
           PyFrameObject* frame,
           char* buf,
           size_t buf_size) {
    size_t pos = 0;
    Py_INCREF(frame);
    PyObject* list = PyList_New(0);
    if (list == NULL) {
        Py_DECREF(frame);
        return 1;
    }
    while (frame) {
        PyList_Append(list, (PyObject*)frame);
        frame = PyFrame_GetBack(frame);  // return a new reference
    }
    int overflow = 0;
    Py_ssize_t len = PyList_Size(list);
    for (Py_ssize_t i = len - 1; i >= 0; --i) {
        PyFrameObject* frame =
            (PyFrameObject*)PyList_GetItem(list, i);  // Borrowed reference
        PyCodeObject* code = PyFrame_GetCode(frame);  // New reference
        PyObject* filename = code->co_filename;
        PyObject* name = code->co_name;

#if PY_VERSION_HEX >= 0x030B00F0
        name = code->co_qualname;
#endif
        // Apply focus_mode filtering
        if (FOCUS_MODE_ENABLED(self) &&
            is_stdlib_or_third_party(self, filename)) {
            Py_DECREF(code);
            continue;
        }

        // Apply regex pattern filtering
        if (!matches_regex_patterns(name, self->regex_patterns) &&
            !matches_regex_patterns(filename, self->regex_patterns)) {
            Py_DECREF(code);
            continue;
        }

        if (IGNORE_SELF_ENABLED(self) &&
            (PyUnicode_Contain(filename, "/site-packages/telepy") ||
             PyUnicode_Contain(filename, "/bin/telepy"))) {
            Py_DECREF(code);
            continue;
        }
        if (filename == NULL || name == NULL) {
            PyErr_Format(PyExc_RuntimeError,
                         "telepysys: failed to get filename or name");
            Py_DECREF(code);
            goto error;
        }

        int lineno = code->co_firstlineno;
        if (TREE_MODE_ENABLED(self))
            lineno = PyFrame_GetLineNumber(frame);
        size_t ret = 0;
        const char* format = NULL;
        if (i > 0) {
            format = "%s:%s:%d;";
        } else {
            format = "%s:%s:%d";
        }
        if (!(IGNORE_FROZEN_ENABLED(self) &&
              PyUnicode_start_with(filename, "<frozen"))) {
            ret = snprintf(buf + pos,
                           buf_size - pos,
                           format,
                           PyUnicode_AsUTF8(filename),
                           PyUnicode_AsUTF8(name),
                           lineno);
            if (ret >= (int)buf_size - pos) {
                overflow = 1;
                PyErr_Format(
                    PyExc_RuntimeError,
                    "telepysys: buffer overflow, call stack too deep");
                Py_DECREF(code);
                goto error;
            }
            pos += ret;
        }
        Py_DECREF(code);
    }

    Py_DECREF(list);
    return overflow;
error:
    Py_DECREF(list);
    return -1;
}


// return a new reference
static PyObject*
get_thread_name(PyObject* threads, PyObject* thread_id) {
    Py_ssize_t len = PyList_Size(threads);
    for (Py_ssize_t i = 0; i < len; ++i) {
        PyObject* thread = PyList_GetItem(threads, i);
        PyObject* ident = PyObject_GetAttrString(thread, "_ident");
        if (PyErr_Occurred()) {
            return NULL;
        }
        if (PyObject_RichCompareBool(ident, thread_id, Py_EQ)) {
            PyObject* name = PyObject_GetAttrString(thread, "_name");
            Py_DECREF(ident);
            return name;
        }
        Py_DECREF(ident);
    }
    return NULL;
}


// microsecond
static Telepy_time
unix_micro_time() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (Telepy_time)ts.tv_sec * 1000000 + ts.tv_nsec / 1000;
}

static PyObject*
_sampling_routine(SamplerObject* self, PyObject* Py_UNUSED(ignore)) {
    PyObject* threading = PyImport_ImportModule("threading");
    if (threading == NULL) {
        PyErr_SetString(PyExc_ImportError,
                        "threading module can not be imported");
        return NULL;
    }
    const size_t buf_size = BUF_SIZE;
    char* buf = (char*)malloc(buf_size);
    Telepy_time sampling_start = unix_micro_time();
    while (Sample_Enabled(self)) {
        self->sampling_times++;
        Py_BEGIN_ALLOW_THREADS;
        // allow dynamic updates of the sampling interval
        struct timespec req = {
            .tv_sec = 0,
            .tv_nsec = (long)PyLong_AsLong(self->sampling_interval) * 1000};
        int ret = nanosleep(&req, NULL);
        if (ret != 0) {
            perror("telepysys: nanosleep error");
        }
        Py_END_ALLOW_THREADS;
        Telepy_time sampler_start = unix_micro_time();
        PyObject* frames = _PyThread_CurrentFrames();  // New reference
        if (frames == NULL) {
            PyErr_Format(PyExc_RuntimeError,
                         "telepysys: _PyThread_CurrentFrames() failed");
            return NULL;
        }
        PyObject* threads = PyObject_CallMethod(threading,
                                                "enumerate",
                                                NULL);  // New reference
        if (threads == NULL) {
            PyErr_SetString(PyExc_RuntimeError,
                            "telepysys: threading.enumerate() failed");
            Py_DECREF(frames);
            goto error;
        }
        // iterate over frames
        PyObject* key = NULL;
        PyObject* value = NULL;
        Py_ssize_t pos = 0;
        while (PyDict_Next(frames, &pos, &key, &value)) {
            // key is a thread id
            // value is a frame object
            unsigned long tid = PyLong_AsUnsignedLong(key);
            if (PyErr_Occurred()) {
                Py_DECREF(frames);
                Py_DECREF(threads);
                goto error;
            }
            // ignore self
            if (tid == self->sampling_tid) {
                continue;
            }
            PyObject* name = get_thread_name(threads, key);
            if (name == NULL) {
                PyErr_Format(PyExc_RuntimeError,
                             "telepysys: failed to get thread name");
                Py_DECREF(frames);
                Py_DECREF(threads);
                goto error;
            }
            Py_ssize_t size =
                snprintf(buf, buf_size, "%s;", PyUnicode_AsUTF8(name));
            Py_DECREF(name);
            int overflow = call_stack(
                self, (PyFrameObject*)value, buf + size, buf_size - size);
            if (overflow) {
                Py_DECREF(frames);
                Py_DECREF(threads);
                goto error;
            }
            if (has_content_after_thread_name(buf, size)) {
                AddCallStack(self->tree, buf);
            }
        }
        Py_DECREF(frames);
        Py_DECREF(threads);
        Telepy_time sampler_end = unix_micro_time();
        self->acc_sampling_time += sampler_end - sampler_start;
        if (CHECK_FALG(self, VERBOSE)) {
            printf("Telepysys Debug Info: sampling cnt: %ld, interval: %ld, "
                   "overhead time: %llu stack: "
                   "%s\n",
                   self->sampling_times,
                   PyLong_AsLong(self->sampling_interval),
                   sampler_end - sampler_start,
                   buf);
        }
    }
    free(buf);
    Py_DECREF(threading);
    Telepy_time sampling_end = unix_micro_time();
    self->life_time = sampling_end - sampling_start;
    Py_RETURN_NONE;

error:
    free(buf);
    Py_DECREF(threading);
    return NULL;
}

PyDoc_STRVAR(_sampling_routine_doc,
             "The sampling routine that is run in a separate thread.");


static PyObject*
Sampler_clear_tree(SamplerObject* self, PyObject* Py_UNUSED(ignore)) {
    if (self->tree) {
        FreeTree(self->tree);
        self->tree = NewTree();
        if (!self->tree) {
            PyErr_SetString(PyExc_RuntimeError, "Failed to create StackTree");
            return NULL;
        }
    }
    self->acc_sampling_time = 0;
    self->sampling_times = 0;
    Py_RETURN_NONE;
}

static PyObject*
Sampler_save(SamplerObject* self, PyObject* const* args, Py_ssize_t nargs) {
    if (nargs != 1) {
        PyErr_SetString(PyExc_TypeError, "save() takes exactly one argument");
    }
    PyObject* filename = args[0];
    if (!PyUnicode_Check(filename)) {
        PyErr_SetString(PyExc_TypeError, "filename must be a string");
    }
    Dump(self->tree, PyUnicode_AsUTF8(filename));
    Py_RETURN_NONE;
}


static PyObject*
Sampler_dumps(SamplerObject* self, PyObject* Py_UNUSED(ignore)) {
    char* buf = Dumps(self->tree);
    PyObject* result = PyUnicode_FromString(buf);
    free(buf);
    return result;
}

static PyObject*
Sampler_get_enabled(SamplerObject* self, void* Py_UNUSED(closure)) {
    if (CHECK_FALG(self, ENABLED)) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

static PyObject*
Sampler_join(SamplerObject* self, PyObject* Py_UNUSED(ignore)) {
    PyObject* thread = self->sampling_thread;
    PyObject* res = PyObject_CallMethod(thread, "join", NULL);
    return res;
}


static PyMethodDef Sampler_methods[] = {
    {
        "start",
        (PyCFunction)Sampler_start,
        METH_NOARGS,
        "Start the sampler",
    },
    {
        "stop",
        (PyCFunction)Sampler_stop,
        METH_NOARGS,
        "Stop the sampler",
    },
    {
        "clear",
        (PyCFunction)Sampler_clear_tree,
        METH_NOARGS,
        "Clear the stack tree",
    },
    {
        "_sampling_routine",
        (PyCFunction)_sampling_routine,
        METH_NOARGS,
        _sampling_routine_doc,
    },
    {
        "save",
        _PyCFunction_CAST(Sampler_save),
        METH_FASTCALL,
        "Save the stack tree to a file",
    },
    {
        "dumps",
        (PyCFunction)Sampler_dumps,
        METH_NOARGS,
        "Dumps the stack tree to a string",
    },
    {
        "enabled",
        (PyCFunction)Sampler_get_enabled,
        METH_NOARGS,
        "Get the sampling interval",
    },
    {
        "join_sampling_thread",
        (PyCFunction)Sampler_join,
        METH_NOARGS,
        "Join the sampling thread",
    },
    {NULL, NULL, 0, NULL},
};


static PyObject*
Sampler_get_sampling_interval(SamplerObject* self, void* Py_UNUSED(closure)) {
    return Py_NewRef(self->sampling_interval);
}


static int
Sampler_set_sampling_interval(SamplerObject* self,
                              PyObject* value,
                              void* Py_UNUSED(closure)) {
    if (!PyLong_Check(value)) {
        PyErr_SetString(PyExc_TypeError,
                        "sampling_interval must be an integer");
        return -1;
    }

    long interval = PyLong_AsLong(value);
    if (interval < 0 || PyErr_Occurred()) {
        return -1;
    }

    Py_INCREF(value);
    Py_CLEAR(self->sampling_interval);
    self->sampling_interval = value;

    return 0;
}

static PyObject*
Sampler_get_sample_thread(SamplerObject* self, void* Py_UNUSED(closure)) {
    if (self->sampling_thread == NULL) {
        Py_RETURN_NONE;
    }
    return Py_NewRef(self->sampling_thread);
}


static PyObject*
Sampler_get_life_time(SamplerObject* self, void* Py_UNUSED(closure)) {
    return PyLong_FromLongLong(self->life_time);
}


static PyObject*
Sampler_get_acc_sampling_time(SamplerObject* self, void* Py_UNUSED(closure)) {
    return PyLong_FromLongLong(self->acc_sampling_time);
}

static PyObject*
Sampler_get_debug(SamplerObject* self, void* Py_UNUSED(closure)) {
    if (CHECK_FALG(self, VERBOSE))
        Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}


static int
Sampler_set_debug(SamplerObject* self,
                  PyObject* value,
                  void* Py_UNUSED(closure)) {
    if (!PyBool_Check(value)) {
        PyErr_SetString(PyExc_TypeError, "debug must be a bool");
        return -1;
    }
    if (Py_IsTrue(value)) {
        ENABLE_DEBUG(self);
    } else {
        DISABLE_DEBUG(self);
    }
    return 0;
}


static PyObject*
Sampler_get_sampling_times(SamplerObject* self, void* Py_UNUSED(closure)) {
    return PyLong_FromLong(self->sampling_times);
}


static PyObject*
Sampler_get_ignore_frozen(SamplerObject* self, void* Py_UNUSED(closure)) {
    if (DEBUG_ENABLED(self)) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}


static int
Sampler_set_ignore_frozen(SamplerObject* self,
                          PyObject* value,
                          void* Py_UNUSED(closure)) {
    if (!PyBool_Check(value)) {
        PyErr_Format(PyExc_TypeError, "ignore_frozen must be a bool");
        return -1;
    }
    if (Py_IsTrue(value)) {
        ENABLE_IGNORE_FROZEN(self);
    } else {
        DISABLE_IGNORE_FROZEN(self);
    }
    return 0;
}

static PyObject*
Sampler_get_ignore_self(SamplerObject* self, void* Py_UNUSED(closure)) {
    if (ENABLE_IGNORE_SELF(self)) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}


static int
Sampler_set_ignore_self(SamplerObject* self,
                        PyObject* value,
                        void* Py_UNUSED(closure)) {
    if (!PyBool_Check(value)) {
        PyErr_Format(PyExc_TypeError, "ignore_self must be a bool");
        return -1;
    }
    if (Py_IsTrue(value)) {
        ENABLE_IGNORE_SELF(self);
    } else {
        DISABLE_IGNORE_SELF(self);
    }
    return 0;
}


static PyObject*
Sampler_get_tree_mode(SamplerObject* self, void* Py_UNUSED(closure)) {
    if (ENABLE_TREE_MODE(self)) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}


static int
Sampler_set_tree_mode(SamplerObject* self,
                      PyObject* value,
                      void* Py_UNUSED(closure)) {
    if (!PyBool_Check(value)) {
        PyErr_Format(PyExc_TypeError, "tree_mode must be a bool");
        return -1;
    }
    if (Py_IsTrue(value)) {
        ENABLE_TREE_MODE(self);
    } else {
        DISABLE_TREE_MODE(self);
    }
    return 0;
}


static PyObject*
Sampler_get_focus_mode(SamplerObject* self, void* Py_UNUSED(closure)) {
    if (FOCUS_MODE_ENABLED(self)) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}


static int
Sampler_set_focus_mode(SamplerObject* self,
                       PyObject* value,
                       void* Py_UNUSED(closure)) {
    if (!PyBool_Check(value)) {
        PyErr_Format(PyExc_TypeError, "focus_mode must be a bool");
        return -1;
    }
    if (Py_IsTrue(value)) {
        ENABLE_FOCUS_MODE(self);
    } else {
        DISABLE_FOCUS_MODE(self);
    }
    return 0;
}


static PyObject*
Sampler_get_regex_patterns(SamplerObject* self, void* Py_UNUSED(closure)) {
    if (self->regex_patterns == NULL) {
        Py_RETURN_NONE;
    }
    return Py_NewRef(self->regex_patterns);
}


static int
Sampler_set_regex_patterns(SamplerObject* self,
                           PyObject* value,
                           void* Py_UNUSED(closure)) {
    if (value != Py_None && !PyList_Check(value)) {
        PyErr_SetString(PyExc_TypeError,
                        "regex_patterns must be a list or None");
        return -1;
    }

    Py_XINCREF(value);
    Py_CLEAR(self->regex_patterns);
    self->regex_patterns = value;

    return 0;
}


static PyGetSetDef Sampler_getset[] = {
    {
        "sampling_interval",
        (getter)Sampler_get_sampling_interval,
        (setter)Sampler_set_sampling_interval,
        "sampling interval in nanoseconds",
        NULL,
    },
    {
        "sampling_thread",
        (getter)Sampler_get_sample_thread,
        NULL,
        "sampling thread",
        NULL,
    },
    {
        "sampler_life_time",
        (getter)Sampler_get_life_time,
        NULL,
        "life time of the sampler in nanoseconds",
        NULL,
    },
    {
        "acc_sampling_time",
        (getter)Sampler_get_acc_sampling_time,
        NULL,
        "accumulated sampling time in nanoseconds",
        NULL,
    },
    {
        "debug",
        (getter)Sampler_get_debug,
        (setter)Sampler_set_debug,
        "debug or not",
        NULL,
    },
    {
        "ignore_frozen",
        (getter)Sampler_get_ignore_frozen,
        (setter)Sampler_set_ignore_frozen,
        "ignore frozen frames or not",
        NULL,
    },
    {
        "ignore_self",
        (getter)Sampler_get_ignore_self,
        (setter)Sampler_set_ignore_self,
        "ignore self or not",
        NULL,
    },
    {
        "tree_mode",
        (getter)Sampler_get_tree_mode,
        (setter)Sampler_set_tree_mode,
        "tree mode or not",
        NULL,
    },
    {
        "focus_mode",
        (getter)Sampler_get_focus_mode,
        (setter)Sampler_set_focus_mode,
        "focus mode - ignore stdlib and third-party libraries",
        NULL,
    },
    {
        "regex_patterns",
        (getter)Sampler_get_regex_patterns,
        (setter)Sampler_set_regex_patterns,
        "compiled regex patterns for filtering stack traces",
        NULL,
    },
    {
        "sampling_times",
        (getter)Sampler_get_sampling_times,
        NULL,
        "sampling times of the sampler",
        NULL,
    },
    {NULL, NULL, NULL, NULL, NULL}  // Sentinel
};

// implement tarverse
static int
Sampler_traverse(SamplerObject* self, visitproc visit, void* arg) {
    Py_VISIT(self->sampling_thread);
    Py_VISIT(self->sampling_interval);
    Py_VISIT(self->regex_patterns);
    return 0;
}


static void
Sampler_dealloc(SamplerObject* self) {
    Py_CLEAR(self->sampling_thread);
    Py_CLEAR(self->sampling_interval);
    Py_CLEAR(self->regex_patterns);
    if (self->std_path) {
        free(self->std_path);
        self->std_path = NULL;
    }
    if (self->tree) {
        FreeTree(self->tree);
    }
    Py_TYPE(self)->tp_free((PyObject*)self);
}


static int
Sampler_clear(SamplerObject* self) {
    Py_CLEAR(self->sampling_thread);
    Py_CLEAR(self->sampling_interval);
    Py_CLEAR(self->regex_patterns);
    if (self->std_path) {
        free(self->std_path);
        self->std_path = NULL;
    }
    if (self->tree) {
        FreeTree(self->tree);
        self->tree = NULL;
    }
    self->sampling_times = 0;
    self->acc_sampling_time = 0;
    return 0;
}


static PyObject*
Sampler_new(PyTypeObject* type,
            PyObject* Py_UNUSED(args),
            PyObject* Py_UNUSED(kwds)) {
    SamplerObject* self = NULL;
    self = (SamplerObject*)type->tp_alloc(type, 0);
    if (self != NULL) {
        self->sampling_thread = NULL;
        self->regex_patterns = NULL;
        self->std_path = NULL;
        self->sampling_interval = PyLong_FromLong(10000);  // 10ms
        if (!self->sampling_interval) {
            Py_DECREF(self);
            PyErr_SetString(PyExc_RuntimeError,
                            "Failed to initialize sampling_interval");
            return NULL;
        }
        self->tree = NewTree();
        if (!self->tree) {
            Py_DECREF(self);
            PyErr_SetString(PyExc_RuntimeError, "Failed to create StackTree");
            return NULL;
        }

        // Initialize std_path
        self->std_path = init_std_path();
        if (!self->std_path) {
            Py_DECREF(self);
            PyErr_SetString(PyExc_RuntimeError,
                            "Failed to initialize std_path");
            return NULL;
        }

        return (PyObject*)self;
    }
    return NULL;
}


static PyType_Slot Sampler_slots[] = {
    {Py_tp_dealloc, Sampler_dealloc},
    {Py_tp_clear, Sampler_clear},
    {Py_tp_methods, Sampler_methods},
    {Py_tp_getset, Sampler_getset},
    {Py_tp_new, Sampler_new},
    {Py_tp_traverse, Sampler_traverse},
    {0, NULL},
};

static PyType_Spec sampler_spec = {
    .name = "_telepysys.Sampler",
    .basicsize = sizeof(SamplerObject),
    .flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC | Py_TPFLAGS_BASETYPE,
    .slots = Sampler_slots,
};


static PyObject*
AsyncSampler_get_sampling_tid(SamplerObject* self, void* Py_UNUSED(closure)) {
    return PyLong_FromLong(self->sampling_tid);
}


static int
AsyncSampler_set_sampling_tid(SamplerObject* self,
                              PyObject* value,
                              void* Py_UNUSED(closure)) {
    if (!PyLong_Check(value)) {
        PyErr_SetString(PyExc_TypeError, "sampling_tid must be an integer");
        return -1;
    }

    long tid = PyLong_AsLong(value);
    if (PyErr_Occurred()) {
        return -1;
    }
    self->sampling_tid = tid;
    return 0;
}


static PyObject*
AsyncSampler_get_start_time(AsyncSamplerObject* self,
                            void* Py_UNUSED(closure)) {
    return PyLong_FromLong(self->start);
}


static PyObject*
AsyncSampler_get_end_time(AsyncSamplerObject* self, void* Py_UNUSED(closure)) {
    return PyLong_FromLong(self->end);
}


static PyGetSetDef AsyncSampler_getset[] = {
    {
        "tree_mode",
        (getter)Sampler_get_tree_mode,
        (setter)Sampler_set_tree_mode,
        "tree mode or not",
        NULL,
    },
    {
        "start_time",
        (getter)AsyncSampler_get_start_time,
        NULL,
        "The tid of the thread that is being sampled",
        NULL,
    },
    {
        "end_time",
        (getter)AsyncSampler_get_end_time,
        NULL,
        "The tid of the thread that is being sampled",
        NULL,
    },
    {
        "sampling_tid",
        (getter)AsyncSampler_get_sampling_tid,
        (setter)AsyncSampler_set_sampling_tid,
        "The tid of the thread that is being sampled",
        NULL,
    },
    {
        "sampling_interval",
        (getter)Sampler_get_sampling_interval,  // share it
        (setter)Sampler_set_sampling_interval,  // share it
        "sampling interval in nanoseconds",
        NULL,
    },
    {
        "acc_sampling_time",
        (getter)Sampler_get_acc_sampling_time,  // share it
        NULL,
        "accumulated sampling time in nanoseconds",
        NULL,
    },
    {
        "sampler_life_time",
        (getter)Sampler_get_life_time,
        NULL,
        "life time of the sampler in nanoseconds",
        NULL,
    },
    {
        "debug",
        (getter)Sampler_get_debug,  // share it
        (setter)Sampler_set_debug,  // share it
        "debug or not",
        NULL,
    },
    {
        "ignore_frozen",
        (getter)Sampler_get_ignore_frozen,  // share it
        (setter)Sampler_set_ignore_frozen,  // share it
        "ignore frozen frames or not",
        NULL,
    },
    {
        "ignore_self",
        (getter)Sampler_get_ignore_self,  // share it
        (setter)Sampler_set_ignore_self,  // share it
        "ignore self or not",
        NULL,
    },
    {
        "focus_mode",
        (getter)Sampler_get_focus_mode,  // share it
        (setter)Sampler_set_focus_mode,  // share it
        "focus mode - ignore stdlib and third-party libraries",
        NULL,
    },
    {
        "regex_patterns",
        (getter)Sampler_get_regex_patterns,  // share it
        (setter)Sampler_set_regex_patterns,  // share it
        "compiled regex patterns for filtering stack traces",
        NULL,
    },
    {
        "sampling_times",
        (getter)Sampler_get_sampling_times,  // share it
        NULL,
        "sampling times of the sampler",
        NULL,
    },
    {
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
    }  // Sentinel
};


// we can not call a python function to get the results, such as threading.enumerate()
static PyObject*
get_all_threads(PyObject* threading) {

    PyObject *active = NULL, *limbo = NULL;
    PyObject *active_values = NULL, *limbo_values = NULL;
    PyObject *active_list = NULL, *limbo_list = NULL;
    PyObject* result = NULL;

    // threading._active
    active = PyObject_GetAttrString(threading, "_active");
    if (!active)
        goto error;

    // threading._limbo
    limbo = PyObject_GetAttrString(threading, "_limbo");
    if (!limbo)
        goto error;

    // _active.values()
    active_values = PyObject_CallMethod(active, "values", NULL);
    if (!active_values)
        goto error;

    // _limbo.values()
    limbo_values = PyObject_CallMethod(limbo, "values", NULL);
    if (!limbo_values)
        goto error;

    // list(_active.values())
    active_list = PySequence_List(active_values);
    if (!active_list)
        goto error;

    // list(_limbo.values())
    limbo_list = PySequence_List(limbo_values);
    if (!limbo_list)
        goto error;

    // result = active_list + limbo_list
    result = PySequence_Concat(active_list, limbo_list);
    if (!result)
        goto error;

    // clean up
    Py_DECREF(active);
    Py_DECREF(limbo);
    Py_DECREF(active_values);
    Py_DECREF(limbo_values);
    Py_DECREF(active_list);
    Py_DECREF(limbo_list);

    return result;

error:
    Py_XDECREF(threading);
    Py_XDECREF(active);
    Py_XDECREF(limbo);
    Py_XDECREF(active_values);
    Py_XDECREF(limbo_values);
    Py_XDECREF(active_list);
    Py_XDECREF(limbo_list);
    Py_XDECREF(result);
    return NULL;
}

// we must ensure that do not eval PyFrames in AsyncSampler_async_routine
// SIGPROF signal handler may be called before last call finished
static PyObject*
AsyncSampler_async_routine(AsyncSamplerObject* self,
                           PyObject* const* args,
                           Py_ssize_t nargs) {
    if (SAMPLING_ENABLED((SamplerObject*)self)) {
        Py_RETURN_NONE;
    }
    ENABLE_SAMPLING((SamplerObject*)self);
    if (nargs != 2) {
        PyErr_Format(
            PyExc_TypeError,
            "async_routine() takes 2 positional arguments but %zd were given",
            nargs);
        return NULL;
    }
    SamplerObject* base = (SamplerObject*)self;
    if (base->sampling_tid == 0) {
        PyErr_SetString(PyExc_RuntimeError, "AsyncSampler's tid is not set");
        return NULL;
    }
    PyObject* threading = self->threading;
    if (threading == NULL) {
        PyErr_SetString(PyExc_ImportError, "Failed to import threading");
        return NULL;
    }

    PyObject* main_frame = args[1];

    const size_t buf_size = self->buf_size;
    char* buf = self->buf;

    Telepy_time sampling_start = unix_micro_time();

    PyObject* frames = _PyThread_CurrentFrames();  // New reference
    if (frames == NULL) {
        PyErr_Format(PyExc_RuntimeError,
                     "telepysys: _PyThread_CurrentFrames() failed");
        return NULL;
    }
    if (main_frame) {
        Py_ssize_t size = snprintf(buf, buf_size, "%s;", "MainThread");
        int overflow = call_stack(
            base, (PyFrameObject*)main_frame, buf + size, buf_size - size);
        if (overflow) {
            Py_XDECREF(frames);
            return NULL;
        }
        if (has_content_after_thread_name(buf, size)) {
            AddCallStack(base->tree, buf);
        }
    }
    PyObject* threads = get_all_threads(threading);  // New reference
    if (threads == NULL || PyErr_Occurred()) {
        PyErr_Format(PyExc_RuntimeError,
                     "telepysys: get_all_threads() failed");
        Py_DECREF(frames);
        return NULL;
    }

    // iterate over frames
    PyObject* key = NULL;
    PyObject* value = NULL;
    Py_ssize_t pos = 0;
    while (PyDict_Next(frames, &pos, &key, &value)) {
        // key is a thread id
        // value is a frame object
        unsigned long tid = PyLong_AsUnsignedLong(key);
        if (PyErr_Occurred()) {
            goto error;
        }
        // ignore self
        if (tid == base->sampling_tid) {
            continue;
        }
        PyObject* name = get_thread_name(threads, key);
        if (name == NULL) {
            PyErr_Format(PyExc_RuntimeError,
                         "telepysys: failed to get thread name");
            goto error;
        }
        Py_ssize_t size =
            snprintf(buf, buf_size, "%s;", PyUnicode_AsUTF8(name));
        Py_DECREF(name);
        int overflow = call_stack(
            base, (PyFrameObject*)value, buf + size, buf_size - size);
        if (overflow) {
            goto error;
        }
        if (has_content_after_thread_name(buf, size)) {
            AddCallStack(base->tree, buf);
        }
    }

    Py_DECREF(frames);
    Py_DECREF(threads);

    // ====================== printf IS NOT async safe ======================
    // if (CHECK_FALG(base, VERBOSE)) {
    //     printf("Telepysys Debug Info: sampling cnt: %ld, interval: %ld, "
    //            "overhead time: %llu stack: "
    //            "%s\n",
    //            base->sampling_times,
    //            PyLong_AsLong(base->sampling_interval),
    //            sampler_end - sampler_start,
    //            buf);
    // }
    // =======================================================================

    Telepy_time sampling_end = unix_micro_time();
    base->acc_sampling_time += sampling_end - sampling_start;
    base->sampling_times++;
    DISABLE_SAMPLING(base);
    Py_RETURN_NONE;

error:
    DISABLE_SAMPLING(base);
    Py_XDECREF(frames);
    Py_XDECREF(threads);
    return NULL;
}


static PyObject*
AsyncSampler_start(AsyncSamplerObject* self, PyObject* Py_UNUSED(ignore)) {
    SamplerObject* base = (SamplerObject*)self;
    Sample_Enable(base);
    self->start = unix_micro_time();
    Py_RETURN_NONE;
}

static PyObject*
AsyncSampler_stop(AsyncSamplerObject* self, PyObject* Py_UNUSED(ignore)) {
    SamplerObject* base = (SamplerObject*)self;
    Sample_Disable(base);
    self->end = unix_micro_time();
    base->life_time = self->end - self->start;
    Py_RETURN_NONE;
}


static PyMethodDef AsyncSampler_methods[] = {
    {
        "start",
        (PyCFunction)AsyncSampler_start,
        METH_NOARGS,
        "Start the sampler",
    },
    {
        "stop",
        (PyCFunction)AsyncSampler_stop,
        METH_NOARGS,
        "Stop the sampler",
    },
    {
        "_async_routine",
        _PyCFunction_CAST(AsyncSampler_async_routine),
        METH_FASTCALL,
        "Async sampler routine",
    },
    {
        "save",
        _PyCFunction_CAST(Sampler_save),  // share it
        METH_FASTCALL,
        "Save the stack tree to a file",
    },
    {
        "clear",
        (PyCFunction)Sampler_clear_tree,  // share it
        METH_NOARGS,
        "Clear the stack tree",
    },
    {
        "dumps",
        (PyCFunction)Sampler_dumps,  // share it
        METH_NOARGS,
        "Dumps the stack tree to a string",
    },
    {
        "enabled",
        (PyCFunction)Sampler_get_enabled,  // share it
        METH_NOARGS,
        "Get the sampling interval",
    },
    {NULL, NULL, 0, NULL},
};


static int
AsyncSampler_clear(AsyncSamplerObject* self) {
    Py_CLEAR(self->base.sampling_interval);
    Py_CLEAR(self->base.regex_patterns);
    Py_CLEAR(self->threading);
    if (self->base.std_path) {
        free(self->base.std_path);
        self->base.std_path = NULL;
    }
    if (self->base.tree) {
        FreeTree(self->base.tree);
        self->base.tree = NULL;
    }
    if (self->buf) {
        free(self->buf);
        self->buf = NULL;
    }
    return 0;
}


static void
AsyncSampler_dealloc(AsyncSamplerObject* self) {
    AsyncSampler_clear(self);
    Py_TYPE(self)->tp_free((PyObject*)self);
}

static PyObject*
AsyncSampler_new(PyTypeObject* type,
                 PyObject* Py_UNUSED(args),
                 PyObject* Py_UNUSED(kwds)) {
    AsyncSamplerObject* self = NULL;
    self = (AsyncSamplerObject*)type->tp_alloc(type, 0);
    if (self != NULL) {
        self->base.sampling_tid = 0;
        self->base.regex_patterns = NULL;
        self->base.std_path = NULL;
        self->base.sampling_interval = PyLong_FromLong(10000);  // 10ms
        if (!self->base.sampling_interval) {
            Py_DECREF(self);
            PyErr_SetString(PyExc_RuntimeError,
                            "Failed to initialize sampling_interval");
            return NULL;
        }
        self->base.tree = NewTree();
        if (!self->base.tree) {
            Py_DECREF(self);
            PyErr_SetString(PyExc_RuntimeError, "Failed to create StackTree");
            return NULL;
        }

        // Initialize std_path
        self->base.std_path = init_std_path();
        if (!self->base.std_path) {
            Py_DECREF(self);
            PyErr_SetString(PyExc_RuntimeError,
                            "Failed to initialize std_path");
            return NULL;
        }

        self->buf_size = BUF_SIZE;
        self->buf = malloc(self->buf_size);
        self->threading = PyImport_ImportModule("threading");
        return (PyObject*)self;
    }
    return NULL;
}


static int
AsyncSampler_traverse(AsyncSamplerObject* self, visitproc visit, void* arg) {
    Py_VISIT(self->base.sampling_interval);
    Py_VISIT(self->base.regex_patterns);
    // we do need to visit self->base.sampling_thread
    // we do use it in async profiler
    Py_VISIT(self->threading);
    return 0;
}

static PyType_Slot AsyncSampler_slots[] = {
    {Py_tp_dealloc, AsyncSampler_dealloc},
    {Py_tp_clear, AsyncSampler_clear},
    {Py_tp_methods, AsyncSampler_methods},
    {Py_tp_getset, AsyncSampler_getset},
    {Py_tp_new, AsyncSampler_new},
    {Py_tp_traverse, AsyncSampler_traverse},
    {0, NULL},
};

static PyType_Spec async_sampler_spec = {
    .name = "_telepysys.AsyncSampler",
    .basicsize = sizeof(AsyncSamplerObject),
    .flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC | Py_TPFLAGS_BASETYPE,
    .slots = AsyncSampler_slots,
};


PyDoc_STRVAR(telepysys_doc, "An utility module for telepysys");

PyDoc_STRVAR(
    telepysys_current_frames_doc,
    "Returns a dictionary where keys are thread IDs and values are "
    "stack frames, including all threads in all Python interpreters.");

static PyObject*
telepysys_current_frames(PyObject* Py_UNUSED(module),
                         PyObject* Py_UNUSED(args)) {
    return _PyThread_CurrentFrames();
}

PyDoc_STRVAR(telepysys_unix_microtime_doc,
             "Returns the current time in microseconds since the epoch.");

static PyObject*
telepysys_unix_microtime(PyObject* Py_UNUSED(module),
                         PyObject* Py_UNUSED(args)) {
    return PyLong_FromLongLong((long long)unix_micro_time());
}

static PyObject*
telepysys_register_main(PyObject* Py_UNUSED(module),
                        PyObject* args,
                        PyObject* kwargs) {
    if (PyTuple_Size(args) < 1) {
        PyErr_SetString(PyExc_TypeError,
                        "telepysys.register_main() takes at least one "
                        "argument (the callable)");
        return NULL;
    }
    PyObject* callable = PyTuple_GetItem(args, 0);
    if (!PyCallable_Check(callable)) {
        PyErr_SetString(
            PyExc_TypeError,
            "telepysys.register_main() first argument must be callable");
        return NULL;
    }
    PyObject* new_args = PyTuple_GetSlice(args, 1, PyTuple_Size(args));
    Py_XINCREF(kwargs);
    Py_INCREF(callable);
    int result = register_func_in_main(
        callable, new_args, kwargs);  // pass ownship of new_args and kwArgs
    if (result) {
        PyErr_Format(
            PyExc_RuntimeError,
            "telepysysy: Failed to register a callable in main thread");
        goto error;
    }
    Py_RETURN_NONE;
error:
    Py_XDECREF(kwargs);
    Py_XDECREF(new_args);
    return NULL;
}

PyDoc_STRVAR(telepysys_register_main_doc,
             "Register a callable in the main thread.");

static PyObject*
telepysys_yield(PyObject* Py_UNUSED(module), PyObject* Py_UNUSED(args)) {

    Py_BEGIN_ALLOW_THREADS;
    sched_yield();
    Py_END_ALLOW_THREADS;
    Py_RETURN_NONE;
}

PyDoc_STRVAR(telepysys_yield_doc,
             "Yield the current thread to other threads.");

PyDoc_STRVAR(telepysys_vm_read_doc,
             "Read a variable from the specified thread's frame.\n\n"
             "Args:\n"
             "    tid: Thread ID\n"
             "    name: Variable name to read\n"
             "    level: Frame level (default 0). 0 is top frame, 1 is second "
             "from top, etc.\n\n"
             "Returns:\n"
             "    The value of the variable if found, None otherwise "
             "(including when level is too deep)");

static PyObject*
telepysys_vm_read(PyObject* Py_UNUSED(module),
                  PyObject* const* args,
                  Py_ssize_t nargs) {
    // Check argument count (2 or 3 arguments)
    if (nargs < 2 || nargs > 3) {
        PyErr_Format(PyExc_TypeError,
                     "vm_read() takes 2 or 3 arguments (%zd given)",
                     nargs);
        return NULL;
    }

    // First argument: tid (should be an integer)
    PyObject* tid_obj = args[0];
    if (!PyLong_Check(tid_obj)) {
        PyErr_SetString(PyExc_TypeError,
                        "vm_read() argument 1 must be an integer (thread ID)");
        return NULL;
    }
    unsigned long tid = PyLong_AsUnsignedLong(tid_obj);
    if (tid == (unsigned long)-1 && PyErr_Occurred()) {
        return NULL;
    }

    // Second argument: name (should be a string)
    PyObject* name_obj = args[1];
    if (!PyUnicode_Check(name_obj)) {
        PyErr_SetString(
            PyExc_TypeError,
            "vm_read() argument 2 must be a string (variable name)");
        return NULL;
    }
    const char* name = PyUnicode_AsUTF8(name_obj);
    if (name == NULL) {
        return NULL;
    }

    // Third argument: level (optional, default 0)
    long level = 0;
    if (nargs == 3) {
        PyObject* level_obj = args[2];
        if (!PyLong_Check(level_obj)) {
            PyErr_SetString(
                PyExc_TypeError,
                "vm_read() argument 3 must be an integer (frame level)");
            return NULL;
        }
        level = PyLong_AsLong(level_obj);
        if (level == -1 && PyErr_Occurred()) {
            return NULL;
        }
        if (level < 0) {
            PyErr_SetString(
                PyExc_ValueError,
                "vm_read() argument 3 (level) must be non-negative");
            return NULL;
        }
    }

    // Get all thread frames - _PyThread_CurrentFrames() returns a new reference
    PyObject* frames_dict = _PyThread_CurrentFrames();
    if (frames_dict == NULL) {
        return NULL;
    }

    // Get the frame for this tid - PyDict_GetItem returns a borrowed reference
    PyObject* frame = PyDict_GetItem(frames_dict, tid_obj);

    if (frame == NULL) {
        // Thread not found
        Py_DECREF(frames_dict);
        Py_RETURN_NONE;
    }

    // frame is a borrowed reference, so we need to incref it before releasing
    // frames_dict
    Py_INCREF(frame);
    Py_DECREF(frames_dict);  // Done with frames_dict

    // Navigate to the specified frame level
    // level=0 means top frame (current frame), level=1 means f_back, etc.
    for (long i = 0; i < level; i++) {
        PyObject* back_frame = PyObject_GetAttrString(frame, "f_back");
        Py_DECREF(frame);

        if (back_frame == NULL || back_frame == Py_None) {
            // Level is too deep, reached end of stack
            Py_XDECREF(back_frame);
            PyErr_Clear();  // Clear any attribute error
            Py_RETURN_NONE;
        }

        frame = back_frame;  // Move to the previous frame
    }

    PyObject* result = NULL;

    // Try to get locals - PyObject_GetAttrString returns a new reference
    PyObject* locals = PyObject_GetAttrString(frame, "f_locals");
    if (locals != NULL) {
        // PyDict_GetItemString returns a borrowed reference
        PyObject* value = PyDict_GetItemString(locals, name);
        if (value != NULL) {
            Py_INCREF(value);  // Convert borrowed reference to new reference
            result = value;
            Py_DECREF(locals);
            Py_DECREF(frame);
            return result;
        }
        Py_DECREF(locals);
    } else {
        // Clear the error if f_locals doesn't exist
        PyErr_Clear();
    }

    // Try to get globals - PyObject_GetAttrString returns a new reference
    PyObject* globals = PyObject_GetAttrString(frame, "f_globals");
    if (globals != NULL) {
        // PyDict_GetItemString returns a borrowed reference
        PyObject* value = PyDict_GetItemString(globals, name);
        if (value != NULL) {
            Py_INCREF(value);  // Convert borrowed reference to new reference
            result = value;
            Py_DECREF(globals);
            Py_DECREF(frame);
            return result;
        }
        Py_DECREF(globals);
    } else {
        // Clear the error if f_globals doesn't exist
        PyErr_Clear();
    }

    // Variable not found in either locals or globals
    Py_DECREF(frame);
    Py_RETURN_NONE;
}

PyDoc_STRVAR(telepysys_vm_write_doc,
             "Write a global variable in the specified thread's frame.\n\n"
             "Args:\n"
             "    tid: Thread ID\n"
             "    name: Variable name to write (must be in f_globals)\n"
             "    value: Value to write\n\n"
             "Returns:\n"
             "    True if write succeeded, False otherwise\n\n"
             "Note:\n"
             "    Only global variables can be modified. Local variables\n"
             "    cannot be updated because f_locals is a snapshot dict.");

static PyObject*
telepysys_vm_write(PyObject* Py_UNUSED(module),
                   PyObject* const* args,
                   Py_ssize_t nargs) {
    // Check argument count
    if (nargs != 3) {
        PyErr_Format(PyExc_TypeError,
                     "vm_write() takes exactly 3 arguments (%zd given)",
                     nargs);
        return NULL;
    }

    // First argument: tid (should be an integer)
    PyObject* tid_obj = args[0];
    if (!PyLong_Check(tid_obj)) {
        PyErr_SetString(
            PyExc_TypeError,
            "vm_write() argument 1 must be an integer (thread ID)");
        return NULL;
    }
    unsigned long tid = PyLong_AsUnsignedLong(tid_obj);
    if (tid == (unsigned long)-1 && PyErr_Occurred()) {
        return NULL;
    }

    // Second argument: name (should be a string)
    PyObject* name_obj = args[1];
    if (!PyUnicode_Check(name_obj)) {
        PyErr_SetString(
            PyExc_TypeError,
            "vm_write() argument 2 must be a string (variable name)");
        return NULL;
    }
    const char* name = PyUnicode_AsUTF8(name_obj);
    if (name == NULL) {
        return NULL;
    }

    // Third argument: value (can be any Python object)
    PyObject* value = args[2];

    // Get all thread frames - _PyThread_CurrentFrames() returns a new reference
    PyObject* frames_dict = _PyThread_CurrentFrames();
    if (frames_dict == NULL) {
        return NULL;
    }

    // Get the frame for this tid - PyDict_GetItem returns a borrowed reference
    PyObject* frame = PyDict_GetItem(frames_dict, tid_obj);

    if (frame == NULL) {
        // Thread not found
        Py_DECREF(frames_dict);
        Py_RETURN_FALSE;
    }

    // frame is a borrowed reference, so we need to incref it before releasing
    // frames_dict
    Py_INCREF(frame);
    Py_DECREF(frames_dict);  // Done with frames_dict

    int result = 0;

    // NOTE: We only support updating globals because frame locals (f_locals)
    // is a snapshot dict and modifying it doesn't affect the actual frame's
    // fast locals (C-level local variables). To modify locals, we would need
    // to use PyFrame_LocalsToFast() which is not part of the stable ABI.

    // Get globals - PyObject_GetAttrString returns a new reference
    PyObject* globals = PyObject_GetAttrString(frame, "f_globals");
    if (globals != NULL) {
        // Check if variable exists in globals
        PyObject* existing_value = PyDict_GetItemString(globals, name);
        if (existing_value != NULL) {
            // Variable exists in globals, update it
            // PyDict_SetItemString increfs value, so we don't need to
            result = PyDict_SetItemString(globals, name, value);
            Py_DECREF(globals);
            Py_DECREF(frame);
            if (result == 0) {
                Py_RETURN_TRUE;
            } else {
                return NULL;  // Error occurred
            }
        }
        Py_DECREF(globals);
    } else {
        // Clear the error if f_globals doesn't exist
        PyErr_Clear();
    }

    // Variable not found in globals
    Py_DECREF(frame);
    Py_RETURN_FALSE;
}

PyDoc_STRVAR(
    telepysys_top_namespace_doc,
    "Get the top frame's namespace (locals or globals) for a thread.\n\n"
    "Args:\n"
    "    tid: Thread ID\n"
    "    flag: 0 for locals, 1 for globals, 2 for both\n\n"
    "Returns:\n"
    "    dict: The namespace dictionary when flag is 0 or 1\n"
    "    tuple: A tuple of (locals, globals) when flag is 2\n"
    "    None: If thread not found");

static PyObject*
telepysys_top_namespace(PyObject* Py_UNUSED(module),
                        PyObject* const* args,
                        Py_ssize_t nargs) {
    // Check argument count
    if (nargs != 2) {
        PyErr_Format(PyExc_TypeError,
                     "top_namespace() takes exactly 2 arguments (%zd given)",
                     nargs);
        return NULL;
    }

    // First argument: tid (should be an integer)
    PyObject* tid_obj = args[0];
    if (!PyLong_Check(tid_obj)) {
        PyErr_SetString(
            PyExc_TypeError,
            "top_namespace() argument 1 must be an integer (thread ID)");
        return NULL;
    }

    // Second argument: flag (should be an integer, 0, 1, or 2)
    PyObject* flag_obj = args[1];
    if (!PyLong_Check(flag_obj)) {
        PyErr_SetString(
            PyExc_TypeError,
            "top_namespace() argument 2 must be an integer (0, 1, or 2)");
        return NULL;
    }
    long flag = PyLong_AsLong(flag_obj);
    if (flag != 0 && flag != 1 && flag != 2) {
        PyErr_SetString(PyExc_ValueError,
                        "top_namespace() argument 2 must be 0 (locals), 1 "
                        "(globals), or 2 (both)");
        return NULL;
    }

    // Get all thread frames - _PyThread_CurrentFrames() returns a new reference
    PyObject* frames_dict = _PyThread_CurrentFrames();
    if (frames_dict == NULL) {
        return NULL;
    }

    // Get the frame for this tid - PyDict_GetItem returns a borrowed reference
    PyObject* frame = PyDict_GetItem(frames_dict, tid_obj);

    if (frame == NULL) {
        // Thread not found
        Py_DECREF(frames_dict);
        Py_RETURN_NONE;
    }

    // frame is a borrowed reference, so we need to incref it before releasing
    // frames_dict
    Py_INCREF(frame);
    Py_DECREF(frames_dict);  // Done with frames_dict

    PyObject* result = NULL;

    if (flag == 0) {
        // Return f_locals - PyObject_GetAttrString returns a new reference
        result = PyObject_GetAttrString(frame, "f_locals");
        Py_DECREF(frame);
        if (result == NULL) {
            // Clear the error if attribute doesn't exist
            PyErr_Clear();
            Py_RETURN_NONE;
        }
        return result;  // result is already a new reference
    } else if (flag == 1) {
        // Return f_globals - PyObject_GetAttrString returns a new reference
        result = PyObject_GetAttrString(frame, "f_globals");
        Py_DECREF(frame);
        if (result == NULL) {
            // Clear the error if attribute doesn't exist
            PyErr_Clear();
            Py_RETURN_NONE;
        }
        return result;  // result is already a new reference
    } else {
        // flag == 2: Return both locals and globals as a tuple
        PyObject* locals = PyObject_GetAttrString(frame, "f_locals");
        PyObject* globals = PyObject_GetAttrString(frame, "f_globals");
        Py_DECREF(frame);

        if (locals == NULL || globals == NULL) {
            // Clear the error if attribute doesn't exist
            PyErr_Clear();
            Py_XDECREF(locals);
            Py_XDECREF(globals);
            Py_RETURN_NONE;
        }

        // Create a tuple containing (locals, globals)
        result = PyTuple_Pack(2, locals, globals);
        Py_DECREF(locals);
        Py_DECREF(globals);

        if (result == NULL) {
            return NULL;
        }

        return result;
    }
}

static PyMethodDef telepysys_methods[] = {
    {
        "current_frames",
        (PyCFunction)telepysys_current_frames,
        METH_NOARGS,
        telepysys_current_frames_doc,
    },
    {
        "unix_micro_time",
        (PyCFunction)telepysys_unix_microtime,
        METH_NOARGS,
        telepysys_unix_microtime_doc,
    },
    {
        "register_main",
        _PyCFunction_CAST(telepysys_register_main),
        METH_VARARGS | METH_KEYWORDS,
        telepysys_register_main_doc,
    },
    {
        "sched_yield",
        (PyCFunction)telepysys_yield,
        METH_NOARGS,
        telepysys_yield_doc,
    },
    {
        "vm_read",
        _PyCFunction_CAST(telepysys_vm_read),
        METH_FASTCALL,
        telepysys_vm_read_doc,
    },
    {
        "vm_write",
        _PyCFunction_CAST(telepysys_vm_write),
        METH_FASTCALL,
        telepysys_vm_write_doc,
    },
    {
        "top_namespace",
        _PyCFunction_CAST(telepysys_top_namespace),
        METH_FASTCALL,
        telepysys_top_namespace_doc,
    },
    {
        NULL,
        NULL,
        0,
        NULL,
    },
};

static int
telepysys_exec(PyObject* m) {
    if (PyModule_AddStringConstant(m, "__version__", TELEPYSYS_VERSION)) {
        return -1;
    }
    TelePySysState* state = PyModule_GetState(m);
    PyObject* sampler_type = PyType_FromSpec(&sampler_spec);
    if (sampler_type == NULL) {
        return -1;
    }
    state->sampler_type = (PyTypeObject*)sampler_type;
    if (PyModule_AddObjectRef(m, "Sampler", sampler_type) < 0) {
        Py_DECREF(sampler_type);
        return -1;
    }
    PyObject* async_sampler_type = PyType_FromSpec(&async_sampler_spec);
    if (async_sampler_type == NULL) {
        Py_DECREF(sampler_type);
        return -1;
    }
    state->async_sampler_type = (PyTypeObject*)async_sampler_type;
    if (PyModule_AddObjectRef(m, "AsyncSampler", async_sampler_type) < 0) {
        Py_DECREF(sampler_type);
        Py_DECREF(async_sampler_type);
        return -1;
    }
    PyModule_AddObjectRef(m, "async_sampler", Py_None);  // singleton
    return 0;
}

static int
telepysys_clear(PyObject* module) {
    TelePySysState* state = PyModule_GetState(module);
    Py_CLEAR(state->sampler_type);
    Py_CLEAR(state->async_sampler_type);
    return 0;
}

static int
telepysys_traverse(PyObject* module, visitproc visit, void* arg) {
    TelePySysState* state = PyModule_GetState(module);
    Py_VISIT(state->sampler_type);
    Py_VISIT(state->async_sampler_type);
    return 0;
}


static void
telepysys_free(void* module) {
    // Shutdown the background delete worker thread before cleaning up
    ShutdownDeleteWorker();
    telepysys_clear(module);
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
    .m_clear = telepysys_clear,
    .m_free = telepysys_free,
    .m_methods = telepysys_methods,
    .m_traverse = telepysys_traverse,
};


PyMODINIT_FUNC
PyInit__telepysys(void) {
    return PyModuleDef_Init(&telepysys);
}