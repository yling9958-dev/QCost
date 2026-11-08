"""Single source of truth for the frozen full-scale paper protocol."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "QMF_PostGIS_100M_Repro_20260910"
RUNTIME_ROOT = Path("/var/tmp/qmf-paper-protocol-20260911")
RESULT_ROOT = ROOT / "results/four_dataset_paper_protocol_20260911"
SEED = 20260910
GIB = 1024 ** 3

DATASET_SPECS = (
    ("geolife_2d_4p2G", "GeoLife", 181000000,
     "98619de96d873e54587ee8cdec9b20162e077b33305b420075494992abbe5c1a"),
    ("gowalla_2d_4p2G", "Gowalla", 183000000,
     "febe5e80f15883d3d558bf00f95d73baf49dc3a67eef6374396084a224057e88"),
    ("nyc_taxi_2d_4p2G", "NYC Taxi", 181000000,
     "9fd8ebf1bef0b5529c111ee9515081b9759be08dc4eedbbe89a1b86d0ab9694c"),
    ("skewed_2d", "Skewed 2D", 204986702,
     "fd3556dda7495d3ca022ac3d9262658c72247649fb7d83790cdabcd92264e190"),
)
DATASETS = tuple(item[0] for item in DATASET_SPECS)
DATASET_NAMES = tuple(item[1] for item in DATASET_SPECS)
DATASET_RESULT_SLUGS = ("geolife", "gowalla", "nyc_taxi", "skewed_2d")
RAW_SHA256 = tuple(item[3] for item in DATASET_SPECS)
POINT_COUNTS = tuple(item[2] for item in DATASET_SPECS)
GEOLIFE_NORMALIZED_SHA256 = "ac4d4843820c5bee637b7e2bb8dc84b039477387fa79e5edb61ba1fb5a8be589"

METHODS = (
    ("QMF", "qmap_uniform_qmf"),
    ("PostGIS-GiST", "postgis_gist"),
    ("LISA", "lisa"),
    ("Flood", "flood"),
    ("Tsunami", "tsunami"),
    ("LMSFC", "lmsfc"),
    ("BMTree", "bmtree"),
    ("Boost-Rstar", "rtree"),
)
REPORT_METHOD_LABELS = (
    "QMF-Index", "PostGIS GiST", "LISA", "Flood", "Tsunami", "LMSFC",
    "BMTree", "Boost R*-tree",
)
PERSISTENT_METHODS = frozenset({
    "qmap_uniform_qmf", "postgis_gist", "tsunami", "lmsfc", "bmtree"
})
METRICS = ("Build_s", "IndexSize_MiB", "Mean_ms", "P95_ms", "P99_ms", "QPS", "PeakMemory_MiB")

QUERY_COUNTS = {
    "train": 1000,
    "validation": 1000,
    "correctness": 1000,
    "warmup": 300,
    "performance": 3000,
    "total": 6300,
}
PERFORMANCE_SELECTIVITY_GROUPS = ("S1", "S2", "S3")
PERFORMANCE_QUERIES_PER_GROUP = QUERY_COUNTS["performance"] // len(PERFORMANCE_SELECTIVITY_GROUPS)
PERFORMANCE_REPETITIONS = 5
BUILD_REPETITIONS = 1
TIMEOUTS_S = {"build": 43200, "correctness": 43200, "timing": 43200}
MEMORY_HIGH = 22 * GIB
MEMORY_MAX = 24 * GIB
MEMORY_SWAP_MAX = 0
HOST_EMERGENCY_RESERVE = 7 * GIB // 2

STATUSES = frozenset({
    "PASS", "HOST_SAFETY_STOP", "CGROUP_MEMORY_MAX", "OOM_KILLED",
    "SWAP_INVALID", "BUILD_FAILED", "CORRECTNESS_FAILED", "WARMUP_FAILED",
    "TIMING_FAILED", "FINALIZATION_FAILED", "REPORTING_FAILED", "TIMEOUT",
})
RETRY_ELIGIBLE_STATUSES = STATUSES - {"PASS"}
GEOLIFE_REPAIR_ORDER = ("qmap_uniform_qmf", "flood", "rtree")

CAMPAIGN_UNIT = "qmf-paper-benchmark-20260911"
REPAIR_UNIT = "qmf-paper-repair-geolife_2d_4p2G"
EXPERIMENT_SLICE = "qmf-paper.slice"
POSTGRES_UNIT = "qmf-paper-postgres"
POSTGRES_PORT = 55445

PROTOCOL = {
    **QUERY_COUNTS,
    "performance_repetitions": PERFORMANCE_REPETITIONS,
    "build_repetitions": BUILD_REPETITIONS,
    "seed": SEED,
    "reference_precomputation": False,
    "reference_query_denominator": QUERY_COUNTS["correctness"],
    "MemoryHigh": MEMORY_HIGH,
    "MemoryMax": MEMORY_MAX,
    "MemorySwapMax": MEMORY_SWAP_MAX,
    "host_reserve": HOST_EMERGENCY_RESERVE,
    "qmf_memory_engineering_production_change": True,
    "qmf_algorithm_changed": False,
    "stage_a": "historical 37/37 attestation plus current packaged R4 and production/config SHA",
    "performance_reference_counts": "not precomputed; observed counts remain in raw timings",
    "correctness_semantics": "exact SQL truth/candidate counts and bidirectional EXCEPT IDs; count kernel checked too",
    "correctness_infrastructure": "enable_hashagg=off only in correctness session to bound SetOp memory",
    "timing_policy": "single persistent connection/worker; prepared statements; all five repetitions; no Linux cache flush",
    "peak_memory_definition": "same original process estimator: maximum build worker RSS or query client RSS plus backend peak; shared cgroup peak is diagnostic",
    "timeouts_s": TIMEOUTS_S,
}
