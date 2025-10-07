
#include "htime.h"
#include "inject.h"
#include "list.h"
#include "object.h"
#include "telepysys.h"
#include "tree.h"
#include "tupleobject.h"
#include <Python.h>
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static inline int
is_stdlib_or_third_party(SamplerObject* sampler, PyObject* filename);

static inline int
PyUnicode_Contain(PyObject* filename, const char* str);

static inline int
matches_regex_patterns(PyObject* filename, PyObject* regex_patterns);

static inline int
PyUnicode_start_with(PyObject* filename, const char* str);

#ifdef __APPLE__
#include <os/lock.h>
#define SPINLOCK_T os_unfair_lock
#define SPINLOCK_INIT OS_UNFAIR_LOCK_INIT
#define SPINLOCK_LOCK(lock) os_unfair_lock_lock(lock)
#define SPINLOCK_UNLOCK(lock) os_unfair_lock_unlock(lock)
#else
// Linux uses pthread_spinlock_t
#define SPINLOCK_T pthread_spinlock_t
#define SPINLOCK_INIT {0}
#define SPINLOCK_LOCK(lock) pthread_spin_lock(lock)
#define SPINLOCK_UNLOCK(lock) pthread_spin_unlock(lock)
#define SPINLOCK_INIT_FUNC(lock)                                              \
    pthread_spin_init(lock, PTHREAD_PROCESS_PRIVATE)
#endif


#define TELEPYSYS_VERSION "0.1.0"
#define MAX_THREAD_NUM 2048

static __thread int ts_idx = -1;
static SPINLOCK_T ts_lock = SPINLOCK_INIT;

struct ThreadState {
    pthread_t thread_id;
    struct list_head list;
};

static struct ThreadState thread_states[MAX_THREAD_NUM];

static int
allocate_thread_state() {
#if !defined(__APPLE__) && defined(SPINLOCK_INIT_FUNC)
    static int ts_lock_initialized = 0;
    if (!ts_lock_initialized) {
        SPINLOCK_INIT_FUNC(&ts_lock);
        ts_lock_initialized = 1;
    }
#endif
    SPINLOCK_LOCK(&ts_lock);
    for (int i = 0; i < MAX_THREAD_NUM; i++) {
        if (thread_states[i].thread_id == 0) {
            thread_states[i].thread_id = pthread_self();
            SPINLOCK_UNLOCK(&ts_lock);
            return i;
        }
    }
    SPINLOCK_UNLOCK(&ts_lock);
    return -1;  // No available slot
}

// Represents a C function call node in the call tree
struct NativeCallNode {
    PyCFunctionObject* cfunc;
    PyFrameObject* py_frame;
    uint64_t call_time_ns;
    struct list_head list;
};

#define FREE_CALL_NODE(node)                                                  \
    do {                                                                      \
        Py_XDECREF((node)->py_frame);                                         \
        Py_XDECREF((node)->cfunc);                                            \
        free(node);                                                           \
    } while (0)


static int
trace_cfunction_call_callback(SamplerObject* Py_UNUSED(self),
                              PyFrameObject* frame,
                              PyObject* arg) {
    if (ts_idx == -1) {
        ts_idx = allocate_thread_state();
        if (ts_idx == -1) {
            PyErr_SetString(PyExc_RuntimeError, "telepysys: too many threads");
            return -1;
        }
    }
    // create new node and insert it
    struct NativeCallNode* node =
        (struct NativeCallNode*)malloc(sizeof(struct NativeCallNode));
    if (node == NULL) {
        PyErr_SetString(PyExc_RuntimeError,
                        "telepysys: failed to allocate memory for C function "
                        "call node");
        return -1;
    }
    node->cfunc = (PyCFunctionObject*)arg;
    node->py_frame = frame;
    node->call_time_ns = htime_get_thread_cpu_ns();
    Py_INCREF(frame);
    Py_INCREF((PyObject*)node->cfunc);
    list_add(&node->list, &thread_states[ts_idx].list);
    thread_states[ts_idx].thread_id = pthread_self();
    return 0;
}


static int
cfunc_call_stack(SamplerObject* self,
                 struct list_head* h,
                 char* buf,
                 size_t buf_size) {

#define BUFFER_OVERFLOW_CHECK(ret, buf_size, pos, context, goto_label)        \
    do {                                                                      \
        if ((ret) < 0 || (ret) >= (int)((buf_size) - (pos))) {                \
            PyErr_Format(PyExc_RuntimeError,                                  \
                         "telepysys: buffer overflow when writing %s, "       \
                         "buffer size: %zu, position: %zd, required: %d",     \
                         (context),                                           \
                         (buf_size),                                          \
                         (pos),                                               \
                         (ret));                                              \
            goto goto_label;                                                  \
        }                                                                     \
    } while (0)

    struct NativeCallNode* node;
    node = list_entry(h, struct NativeCallNode, list);
    PyObject* list = PyList_New(0);
    PyFrameObject* f = node->py_frame;
    Py_INCREF(f);
    while (f != NULL) {
        PyList_Append(list, (PyObject*)f);
        f = PyFrame_GetBack(f);  // return a new reference
    }
    Py_ssize_t pos = 0;
    char* format = NULL;
    for (Py_ssize_t i = PyList_Size(list) - 1; i >= 0; --i) {
        PyFrameObject* frame = (PyFrameObject*)PyList_GetItem(list, i);
        PyCodeObject* code = PyFrame_GetCode(frame);  // New reference
        PyObject* filename = code->co_filename;
        PyObject* name = code->co_name;
#if PY_VERSION_HEX >= 0x030B00F0
        name = code->co_qualname;
#endif
        if (name == NULL || filename == NULL) {
            PyErr_Format(PyExc_RuntimeError,
                         "telepysys: failed to get filename or name");
            Py_DECREF(code);
            goto error;
        }
        int lineno = code->co_firstlineno;
        Py_DECREF(code);
        if (FOCUS_MODE_ENABLED(self) &&
            is_stdlib_or_third_party(self, filename)) {
            continue;
        }
        if (IGNORE_SELF_ENABLED(self) &&
            (PyUnicode_Contain(filename, "/site-packages/telepy") ||
             PyUnicode_Contain(filename, "/bin/telepy"))) {
            continue;
        }
        if (!matches_regex_patterns(name, self->regex_patterns) &&
            !matches_regex_patterns(filename, self->regex_patterns)) {
            continue;
        }
        if (IGNORE_FROZEN_ENABLED(self) &&
            PyUnicode_start_with(filename, "<frozen")) {
            continue;
        }
        if (TREE_MODE_ENABLED(self))
            lineno = PyFrame_GetLineNumber(frame);
        if (i > 0) {
            format = "%s:%s:%d;";
        } else {
            format = "%s:%s:%d";
        }
        int ret = snprintf(buf + pos,
                           buf_size - pos,
                           format,
                           PyUnicode_AsUTF8(filename),
                           PyUnicode_AsUTF8(name),
                           lineno);
        BUFFER_OVERFLOW_CHECK(ret, buf_size, pos, "stack trace", error);
        pos += ret;

        if (frame == node->py_frame) {
            // found the frame where the C function is called
            const char* cfunc_format = NULL;
            if (i > 0) {
                cfunc_format = ";%s:%s:%d;";
            } else {
                cfunc_format = ";%s:%s:%d";
            }
            // Get module name from PyCFunctionObject
            const char* module_name = NULL;
            if (node->cfunc->m_module != NULL) {
                if (PyUnicode_Check(node->cfunc->m_module)) {
                    module_name = PyUnicode_AsUTF8(node->cfunc->m_module);
                } else if (PyModule_Check(node->cfunc->m_module)) {
                    module_name = PyModule_GetName(node->cfunc->m_module);
                }
            }
            if (module_name == NULL) {
                module_name = "<cfunc>";
            }
            const char* func_name = node->cfunc->m_ml->ml_name;
            ret = snprintf(buf + pos,
                           buf_size - pos,
                           cfunc_format,
                           module_name,
                           func_name,
                           0);
            BUFFER_OVERFLOW_CHECK(ret, buf_size, pos, "cfunc trace", error);
            pos += ret;
            struct NativeCallNode* t =
                list_entry(&node->list.prev, struct NativeCallNode, list);
            FREE_CALL_NODE(node);
            list_del(&node->list);
            node = t;
        }
    }
    Py_DECREF(list);
    return 0;
error:
    Py_DECREF(list);
    return -1;
}

static int
trace_cfunction_return_callback(SamplerObject* self,
                                PyFrameObject* Py_UNUSED(frame),
                                PyObject* Py_UNUSED(arg)) {
    assert(ts_idx != -1);
    uint64_t return_time_ns = htime_get_thread_cpu_ns();
    struct NativeCallNode* node =
        list_entry(&thread_states[ts_idx].list, struct NativeCallNode, list);
    uint64_t duration_us = (return_time_ns - node->call_time_ns) / 1000ULL;
    char* buf = self->buf;
    size_t buf_size = self->buf_size;
    int ret =
        cfunc_call_stack(self, thread_states[ts_idx].list.prev, buf, buf_size);
    if (ret != 0) {
        goto cleanup;
    }
    // TODO: find the best discount factor
    AddCallStackWithCount(
        self->tree,
        buf,
        duration_us / PyLong_AsLong(self->sampling_interval) *
            0.8);  // discount 20% time for C function call overhead

cleanup:
    list_del(&node->list);
    free(node);
    return ret;
}

// =============================================================================
// C Function Trace Callbacks
// =============================================================================

#if PY_VERSION_HEX >= 0x030C0000
// Python 3.12+ uses the new monitoring API for better performance
// Skeleton trace function for Python 3.12+
// Note: For now this is just a placeholder for the monitoring API implementation
// The actual monitoring API has a different interface that will be implemented later
static int
trace_c_function(PyObject* obj,
                 PyFrameObject* frame,
                 int what,
                 PyObject* arg) {
    // TODO: Implement C function tracing logic for Python 3.12+
    // This will use the new sys.monitoring API for better performance
    // Reference: PEP 669 - Low Impact Monitoring for CPython

    // increase branch prediction accuracy
    if (what != PyTrace_C_CALL && what != PyTrace_C_RETURN) {
        return 0;
    }

    SamplerObject* self = (SamplerObject*)obj;
    int ret = 0;

    switch (what) {
    case PyTrace_C_CALL:
        ret = trace_cfunction_call_callback(self, frame, arg);
        break;
    case PyTrace_C_RETURN:
        ret = trace_cfunction_return_callback(self, frame, arg);
        break;
    default:
        return 0;
    }

    return ret;
}

#else
// Python < 3.12 uses PyEval_SetProfile
// Skeleton trace function for Python < 3.12
static int
trace_c_function(PyObject* obj,
                 PyFrameObject* frame,
                 int what,
                 PyObject* arg) {
    // increase branch prediction accuracy
    if (what != PyTrace_C_CALL && what != PyTrace_C_RETURN) {
        return 0;
    }

    SamplerObject* self = (SamplerObject*)obj;
    int ret = 0;

    switch (what) {
    case PyTrace_C_CALL:
        ret = trace_cfunction_call_callback(self, frame, arg);
        break;
    case PyTrace_C_RETURN:
        ret = trace_cfunction_return_callback(self, frame, arg);
        break;
    default:
        return 0;
    }

    return ret;
}
#endif

// =============================================================================
// End of C Function Trace Callbacks
// =============================================================================


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

static inline Telepy_time
sampler_now_us(SamplerObject* self) {
    if (TIME_MODE_IS_CPU(self)) {
        return (Telepy_time)htime_get_thread_cpu_us();
    }
    return unix_micro_time();
}

static PyObject*
_sampling_routine(SamplerObject* self, PyObject* Py_UNUSED(ignore)) {
    PyObject* threading = PyImport_ImportModule("threading");
    if (threading == NULL) {
        PyErr_SetString(PyExc_ImportError,
                        "threading module can not be imported");
        return NULL;
    }
    const size_t buf_size = self->buf_size;
    char* buf = self->buf;
    Telepy_time sampling_start = sampler_now_us(self);
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
        Telepy_time sampler_start = sampler_now_us(self);
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
        Telepy_time sampler_end = sampler_now_us(self);
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
    Py_DECREF(threading);
    Telepy_time sampling_end = sampler_now_us(self);
    self->life_time = sampling_end - sampling_start;
    Py_RETURN_NONE;

error:
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

static PyObject*
Sampler_start_trace_cfunction(SamplerObject* self,
                              PyObject* Py_UNUSED(ignored)) {
    // Check if trace_cfunction flag is enabled
    if (!TRACE_CFUNCTION_ENABLED(self)) {
        PyErr_SetString(PyExc_RuntimeError,
                        "trace_cfunction is not enabled. Set "
                        "trace_cfunction=True when creating the sampler.");
        return NULL;
    }

    // Check if sampler is already started
    if (!Sample_Enabled(self)) {
        PyErr_SetString(
            PyExc_RuntimeError,
            "Sampler must be started before enabling C function tracing.");
        return NULL;
    }

#if PY_VERSION_HEX >= 0x030C0000
    // Use PyEval_SetProfile for Python 3.12+ (monitoring API to be implemented later)
    PyEval_SetProfile(trace_c_function, (PyObject*)self);
#else
    // Use PyEval_SetProfile for Python < 3.12
    PyEval_SetProfile(trace_c_function, (PyObject*)self);
#endif

    Py_RETURN_NONE;
}

static PyObject*
Sampler_stop_trace_cfunction(SamplerObject* self,
                             PyObject* Py_UNUSED(ignored)) {
    // Check if trace_cfunction flag is enabled
    if (!TRACE_CFUNCTION_ENABLED(self)) {
        PyErr_SetString(PyExc_RuntimeError,
                        "trace_cfunction is not enabled. Set "
                        "trace_cfunction=True when creating the sampler.");
        return NULL;
    }

    // Disable profiling by setting NULL (same for all Python versions)
    PyEval_SetProfile(NULL, NULL);

    Py_RETURN_NONE;
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
    {
        "start_trace_cfunction",
        (PyCFunction)Sampler_start_trace_cfunction,
        METH_NOARGS,
        "Start tracing C functions",
    },
    {
        "stop_trace_cfunction",
        (PyCFunction)Sampler_stop_trace_cfunction,
        METH_NOARGS,
        "Stop tracing C functions",
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
Sampler_get_trace_cfunction(SamplerObject* self, void* Py_UNUSED(closure)) {
    if (TRACE_CFUNCTION_ENABLED(self)) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}


static int
Sampler_set_trace_cfunction(SamplerObject* self,
                            PyObject* value,
                            void* Py_UNUSED(closure)) {
    if (!PyBool_Check(value)) {
        PyErr_Format(PyExc_TypeError, "trace_cfunction must be a bool");
        return -1;
    }
    if (Py_IsTrue(value)) {
        ENABLE_TRACE_CFUNCTION(self);
    } else {
        DISABLE_TRACE_CFUNCTION(self);
    }
    return 0;
}


static PyObject*
Sampler_get_time_mode(SamplerObject* self, void* Py_UNUSED(closure)) {
    if (TIME_MODE_IS_CPU(self)) {
        return PyUnicode_FromString("cpu");
    }
    if (TIME_MODE_IS_WALL(self)) {
        return PyUnicode_FromString("wall");
    }
    Py_RETURN_NONE;
}


static int
Sampler_set_time_mode(SamplerObject* self,
                      PyObject* value,
                      void* Py_UNUSED(closure)) {
    if (value == NULL) {
        PyErr_SetString(PyExc_TypeError, "cannot delete time_mode");
        return -1;
    }
    if (value == Py_None) {
        SET_TIME_MODE_NONE(self);
        return 0;
    }
    if (!PyUnicode_Check(value)) {
        PyErr_SetString(PyExc_TypeError, "time_mode must be a string or None");
        return -1;
    }
    PyObject* lower = PyObject_CallMethod(value, "lower", NULL);
    if (!lower) {
        return -1;
    }
    const char* mode = PyUnicode_AsUTF8(lower);
    if (!mode) {
        Py_DECREF(lower);
        return -1;
    }
    if (strcmp(mode, "cpu") == 0) {
        SET_TIME_MODE_CPU(self);
        Py_DECREF(lower);
        return 0;
    }
    if (strcmp(mode, "wall") == 0) {
        SET_TIME_MODE_WALL(self);
        Py_DECREF(lower);
        return 0;
    }
    Py_DECREF(lower);
    PyErr_SetString(PyExc_ValueError,
                    "time_mode must be either 'cpu', 'wall', or None");
    return -1;
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
        "trace_cfunction",
        (getter)Sampler_get_trace_cfunction,
        (setter)Sampler_set_trace_cfunction,
        "trace C functions via profiling hooks",
        NULL,
    },
    {
        "time_mode",
        (getter)Sampler_get_time_mode,
        (setter)Sampler_set_time_mode,
        "sampling timer source ('cpu' for CPU time, 'wall' for monotonic)",
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
        self->buf = malloc(BUF_SIZE);
        if (!self->buf) {
            Py_DECREF(self);
            PyErr_SetString(PyExc_RuntimeError, "Failed to allocate buffer");
            return NULL;
        }
        self->buf_size = BUF_SIZE;

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
        "trace_cfunction",
        (getter)Sampler_get_trace_cfunction,  // share it
        (setter)Sampler_set_trace_cfunction,  // share it
        "trace C functions via profiling hooks",
        NULL,
    },
    {
        "time_mode",
        (getter)Sampler_get_time_mode,  // share it
        (setter)Sampler_set_time_mode,  // share it
        "sampling timer source ('cpu' for CPU time, 'wall' for monotonic)",
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
        PyErr_Format(PyExc_TypeError,
                     "async_routine() takes 2 positional arguments but "
                     "%zd were given",
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

    const size_t buf_size = self->base.buf_size;
    char* buf = self->base.buf;

    Telepy_time sampling_start = sampler_now_us(base);

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

    Telepy_time sampling_end = sampler_now_us(base);
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
    self->start = sampler_now_us(base);
    Py_RETURN_NONE;
}

static PyObject*
AsyncSampler_stop(AsyncSamplerObject* self, PyObject* Py_UNUSED(ignore)) {
    SamplerObject* base = (SamplerObject*)self;
    Sample_Disable(base);
    self->end = sampler_now_us(base);
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
    {
        "start_trace_cfunction",
        (PyCFunction)Sampler_start_trace_cfunction,  // share it
        METH_NOARGS,
        "Start tracing C functions",
    },
    {
        "stop_trace_cfunction",
        (PyCFunction)Sampler_stop_trace_cfunction,  // share it
        METH_NOARGS,
        "Stop tracing C functions",
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
    if (self->base.buf) {
        free(self->base.buf);
        self->base.buf = NULL;
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

        self->base.buf_size = BUF_SIZE;
        self->base.buf = malloc(self->base.buf_size);
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
    int result =
        register_func_in_main(callable,
                              new_args,
                              kwargs);  // pass ownship of new_args and kwArgs
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
        NULL,
        NULL,
        0,
        NULL,
    },
};

static int
telepysys_exec(PyObject* m) {
    memset(thread_states, 0, sizeof(thread_states));
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
    for (int i = 0; i < MAX_THREAD_NUM; i++) {
        if (thread_states[i].thread_id == 0)
            break;
        struct NativeCallNode* pos;
        struct NativeCallNode* n;
        list_for_each_entry_safe(pos, n, &thread_states[i].list, list) {
            FREE_CALL_NODE(pos);
            list_del(&pos->list);
        }
        thread_states[i].thread_id = 0;
    }
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
