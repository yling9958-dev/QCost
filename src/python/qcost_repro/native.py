"""Context-managed Python bindings for the project's existing C API."""

import ctypes as ct
from pathlib import Path

import numpy as np


class RuntimeIndex:
    def __init__(self, library, index, method='qmap_uniform_qmf'):
        self.library = ct.CDLL(str(Path(library).resolve()))
        pointer = ct.POINTER(ct.c_uint32)
        base = [ct.c_void_p, ct.c_double, ct.c_double, ct.c_double, ct.c_double]
        tail = [ct.POINTER(ct.c_size_t), ct.POINTER(ct.c_size_t), ct.c_char_p, ct.c_size_t]
        self.library.qmap_runtime_open.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_char_p, ct.c_size_t]
        self.library.qmap_runtime_open.restype = ct.c_void_p
        self.library.qmap_runtime_count.argtypes = base + tail
        self.library.qmap_runtime_count.restype = ct.c_int
        self.library.qmap_runtime_query.argtypes = base + [ct.POINTER(pointer)] + tail
        self.library.qmap_runtime_query.restype = ct.c_int
        self.library.qmap_runtime_free_ids.argtypes = [pointer]
        self.library.qmap_runtime_free_ids.restype = None
        self.library.qmap_runtime_close.argtypes = [ct.c_void_p]
        self.library.qmap_runtime_close.restype = None
        self.error = ct.create_string_buffer(1024)
        self.handle = self.library.qmap_runtime_open(method.encode(), str(Path(index)).encode(),
                                                    self.error, len(self.error))
        if not self.handle:
            raise RuntimeError(self.error.value.decode())

    def count(self, rectangle):
        if not self.handle:
            raise RuntimeError('Index is closed')
        count, candidates = ct.c_size_t(), ct.c_size_t()
        code = self.library.qmap_runtime_count(self.handle, *map(float, rectangle),
            ct.byref(count), ct.byref(candidates), self.error, len(self.error))
        if code:
            raise RuntimeError(self.error.value.decode())
        return count.value, candidates.value

    def query(self, rectangle):
        if not self.handle:
            raise RuntimeError('Index is closed')
        ids = ct.POINTER(ct.c_uint32)()
        count, candidates = ct.c_size_t(), ct.c_size_t()
        code = self.library.qmap_runtime_query(self.handle, *map(float, rectangle), ct.byref(ids),
            ct.byref(count), ct.byref(candidates), self.error, len(self.error))
        try:
            if code:
                raise RuntimeError(self.error.value.decode())
            result = np.ctypeslib.as_array(ids, shape=(count.value,)).copy() if count.value else np.empty(0, dtype=np.uint32)
            return result, candidates.value
        finally:
            if ids:
                self.library.qmap_runtime_free_ids(ids)

    def close(self):
        if self.handle:
            self.library.qmap_runtime_close(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
