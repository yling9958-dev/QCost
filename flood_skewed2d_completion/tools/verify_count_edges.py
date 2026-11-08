"""Diagnostic native COUNT + ID checks; never a substitute for full correctness."""
import ctypes as C
import csv
import json
import math
import random
import struct
import time
from pathlib import Path

import numpy as np

from initial_audit import COMMON, ROOT, sha, write
from run_stage import RUNTIME


def main():
    started = time.monotonic()
    output = ROOT / '03_validation' / f'count_kernel_edges_{time.time_ns()}'
    output.mkdir()
    library_path = COMMON / 'build/lib/libqmap_runtime.so'
    expected_library = '52283a9c9f9b35a6506dfe859a12d931f6bc4455076c84229c2f0bf98109f973'
    assert sha(library_path) == expected_library
    library = C.CDLL(str(library_path))
    ptr = C.c_void_p
    size = C.c_size_t
    char = C.POINTER(C.c_char)
    ids_ptr = C.POINTER(C.c_uint32)
    bounds = [C.c_double] * 4
    library.qmap_runtime_open.argtypes = [C.c_char_p, C.c_char_p, char, size]
    library.qmap_runtime_open.restype = ptr
    library.qmap_runtime_count.argtypes = [ptr, *bounds, C.POINTER(size), C.POINTER(size), char, size]
    library.qmap_runtime_count.restype = C.c_int
    library.qmap_runtime_query.argtypes = [ptr, *bounds, C.POINTER(ids_ptr), C.POINTER(size), C.POINTER(size), char, size]
    library.qmap_runtime_query.restype = C.c_int
    library.qmap_runtime_free_ids.argtypes = [ids_ptr]
    library.qmap_runtime_free_ids.restype = None
    library.qmap_runtime_close.argtypes = [ptr]
    library.qmap_runtime_close.restype = None

    archives = {name: RUNTIME / f'diagnostic_16384-{name}.idx' for name in ['normal', 'swapped']}
    original_hashes = {name: sha(path) for name, path in archives.items()}
    with archives['normal'].open('rb') as stream:
        n, swapped = struct.unpack('<Q?', stream.read(9))
        points = np.frombuffer(stream.read(), dtype=[('x', '<f4'), ('y', '<f4'), ('id', '<u4')]).copy()
    assert n == len(points) == 16384 + 265 and swapped is False
    assert len(set(int(v) for v in points['id'])) == n
    # Promote coordinates explicitly so nextafter(double) bounds are not cast to float32.
    x, y = points['x'].astype(np.float64), points['y'].astype(np.float64)
    queries = [
        ('all', (-2., -2., 2., 2.)), ('unit_domain', (0., 0., 1., 1.)),
        ('empty_below', (-2., -2., -1., -1.)), ('empty_above', (2., 2., 3., 3.)),
        ('zero', (0., 0., 0., 0.)), ('one', (1., 1., 1., 1.)),
        ('duplicates_exact', (.75, .125, .75, .125)),
        ('duplicates_dense', (.74, .12, .76, .13)),
        ('duplicates_excluded', (math.nextafter(.75, math.inf), .125, .76, .125)),
        ('second_duplicates', (.125, .75, .125, .75)),
        ('sparse', (.90, .90, .91, .91)),
        ('vertical_line', (.5, 0., .5, 1.)), ('horizontal_line', (0., .5, 1., .5)),
    ]
    rng = random.Random(20261024)
    for i in range(1000):
        a, b, c, d = [rng.uniform(-.05, 1.05) for _ in range(4)]
        queries.append((f'random_{i:04d}', (min(a, b), min(c, d), max(a, b), max(c, d))))
    for i in [*range(64), *range(n - 9, n)]:
        a, b = float(x[i]), float(y[i])
        queries.extend([
            (f'point_{i}_exact', (a, b, a, b)),
            (f'point_{i}_nextafter_below', (math.nextafter(a, -math.inf), math.nextafter(b, -math.inf), a, b)),
            (f'point_{i}_nextafter_above', (math.nextafter(a, math.inf), math.nextafter(b, math.inf), a + .001, b + .001)),
        ])
    truths = [np.sort(points['id'][(x >= a) & (x <= c) & (y >= b) & (y <= d)])
              for _, (a, b, c, d) in queries]
    assert len(truths[0]) == n and len(truths[2]) == len(truths[3]) == 0
    assert len(truths[6]) >= 256
    fields = ['orientation', 'lifecycle', 'query_id', 'bounds', 'reference_count', 'native_count', 'id_count', 'exact']
    checked = 0
    with (output / 'correctness.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for orientation, archive in archives.items():
            with archive.open('rb') as source:
                archive_n, archive_swapped = struct.unpack('<Q?', source.read(9))
                archive_points = np.frombuffer(source.read(), dtype=points.dtype)
            assert archive_n == n and archive_swapped == (orientation == 'swapped')
            assert np.array_equal(archive_points, points)
            for lifecycle in ['first_load', 'destroy_then_reload']:
                error = C.create_string_buffer(2048)
                handle = library.qmap_runtime_open(b'flood', str(archive).encode(), error, len(error))
                assert handle, error.value.decode()
                try:
                    for (query_id, rectangle), truth in zip(queries, truths):
                        count, candidates = size(), size()
                        status = library.qmap_runtime_count(handle, *rectangle, C.byref(count), C.byref(candidates), error, len(error))
                        assert status == 0, error.value.decode()
                        returned_ids, id_count, id_candidates = ids_ptr(), size(), size()
                        try:
                            status = library.qmap_runtime_query(handle, *rectangle, C.byref(returned_ids), C.byref(id_count), C.byref(id_candidates), error, len(error))
                            assert status == 0, error.value.decode()
                            ids = np.ctypeslib.as_array(returned_ids, shape=(id_count.value,)) if id_count.value else np.array([], dtype=np.uint32)
                            exact = count.value == id_count.value == len(truth) and np.array_equal(np.sort(ids), truth)
                        finally:
                            library.qmap_runtime_free_ids(returned_ids)
                        writer.writerow(dict(orientation=orientation, lifecycle=lifecycle, query_id=query_id,
                                             bounds=json.dumps(rectangle), reference_count=len(truth),
                                             native_count=count.value, id_count=id_count.value, exact=int(exact)))
                        assert exact, (orientation, lifecycle, query_id, rectangle, len(truth), count.value, id_count.value)
                        checked += 1
                finally:
                    library.qmap_runtime_close(handle)
    assert checked == len(queries) * 4
    assert {name: sha(path) for name, path in archives.items()} == original_hashes
    result = dict(status='PASS', diagnostic_only=True, source_points=16384, additional_fixture_points=265,
                  points=n, rectangles=len(queries), exact_COUNT_and_ID_checks=checked,
                  orientations=2, independent_loads_per_orientation=2,
                  oracle='NumPy brute-force inclusive double-coordinate rectangle comparisons; unique source IDs, no reference answer files.',
                  count_entry='qmap_runtime_count (same unmodified native entry called by PostgreSQL qmap_range_count)',
                  library_sha256=expected_library, archive_sha256=original_hashes,
                  verification_script_sha256=sha(Path(__file__)), elapsed_s=time.monotonic()-started,
                  scope='Diagnostic archives only; no PostgreSQL connection, formal input/query edits, formal latency or reference-table mutation.')
    write(output / 'PASS.json', result)
    print(json.dumps(dict(output=str(output), **result), indent=2))


if __name__ == '__main__':
    main()
