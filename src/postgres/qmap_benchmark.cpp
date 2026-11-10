extern "C" {
#include "postgres.h"
#include "fmgr.h"
#include "funcapi.h"
#include "utils/builtins.h"
#include "utils/guc.h"
#include "utils/memutils.h"
}

#include <array>
#include <cfloat>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <memory>
#include <string>
#include <unordered_map>

#include "qmapli/runtime_c_api.h"

extern "C" {
PG_MODULE_MAGIC;
PG_FUNCTION_INFO_V1(qmap_range_query);
PG_FUNCTION_INFO_V1(qmap_range_count);
PG_FUNCTION_INFO_V1(qmap_preload_index);
PG_FUNCTION_INFO_V1(qmap_fairness_counters);
PG_FUNCTION_INFO_V1(qmap_reset_index_cache);
PG_FUNCTION_INFO_V1(qmap_profile_query);
void _PG_init(void);
}

namespace {

char* index_root = nullptr;
bool normalize_coordinates = false;
double source_xmin = 0.0;
double source_xmax = 1.0;
double source_ymin = 0.0;
double source_ymax = 1.0;

struct HandleDeleter {
    void operator()(qmap_runtime_handle* handle) const { qmap_runtime_close(handle); }
};

using Handle = std::unique_ptr<qmap_runtime_handle, HandleDeleter>;
std::unordered_map<std::string, Handle> handles;

struct FairnessCounters {
    std::uint64_t load_count = 0;
    std::uint64_t query_count = 0;
    std::uint64_t query_rebuild_count = 0;
    std::uint64_t query_reload_count = 0;
    std::uint64_t query_training_count = 0;
    std::uint64_t query_external_process_count = 0;
    std::uint64_t query_python_count = 0;
    std::uint64_t query_quantum_count = 0;
};

std::unordered_map<std::string, FairnessCounters> fairness_counters;
std::uint64_t cache_generation = 1;

constexpr std::array<const char*, 2> kMethods{"qmap_uniform_qmf", "qmap_qw"};

bool supported(const std::string& method) {
    for (const auto* candidate : kMethods) if (method == candidate) return true;
    return false;
}

std::filesystem::path configured_root() {
    if (index_root && index_root[0] != '\0') return index_root;
    const auto* environment = std::getenv("QMAP_INDEX_ROOT");
    if (environment && environment[0] != '\0') return environment;
    throw std::runtime_error(
        "qmap_benchmark.index_root is unset; set it to the directory containing static .idx files");
}

qmap_runtime_handle* get_handle(const std::string& method) {
    if (!supported(method)) throw std::invalid_argument("unsupported qmap benchmark method: " + method);
    const auto found = handles.find(method);
    if (found != handles.end()) return found->second.get();
    const auto path = configured_root() / (method + ".idx");
    std::array<char, 1024> error{};
    auto* raw = qmap_runtime_open(method.c_str(), path.c_str(), error.data(), error.size());
    if (!raw) throw std::runtime_error(error.data());
    ++fairness_counters[method].load_count;
    return handles.emplace(method, Handle(raw)).first->second.get();
}

struct QueryRows {
    std::uint32_t* ids = nullptr;
    std::size_t count = 0;
    MemoryContextCallback cleanup{};
};

void release_rows(void* argument) {
    auto* rows = static_cast<QueryRows*>(argument);
    qmap_runtime_free_ids(rows->ids);
    rows->ids = nullptr;
}

struct CachedCall {
    char method[64];
    std::size_t length;
    std::uint64_t generation;
    qmap_runtime_handle* handle;
    FairnessCounters* counters;
};

CachedCall* count_binding(FunctionCallInfo fcinfo) {
    const auto* value = PG_GETARG_TEXT_PP(0);
    const auto length = static_cast<std::size_t>(VARSIZE_ANY_EXHDR(value));
    const auto* data = VARDATA_ANY(value);
    auto* binding = static_cast<CachedCall*>(fcinfo->flinfo->fn_extra);
    if (!binding) {
        binding = static_cast<CachedCall*>(MemoryContextAllocZero(fcinfo->flinfo->fn_mcxt,sizeof(CachedCall)));
        fcinfo->flinfo->fn_extra = binding;
    }
    if (length >= sizeof(binding->method)) throw std::invalid_argument("unsupported method name length");
    if (binding->generation != cache_generation || binding->length != length
        || std::memcmp(binding->method,data,length) != 0) {
        const std::string method(data,length);
        auto* handle = get_handle(method);
        std::memcpy(binding->method,data,length);
        binding->method[length] = '\0';
        binding->length = length;
        binding->handle = handle;
        binding->counters = &fairness_counters.at(method);
        binding->generation = cache_generation;
    }
    return binding;
}

struct Coordinates {
    double xmin;
    double ymin;
    double xmax;
    double ymax;
};

Coordinates transform(double xmin, double ymin, double xmax, double ymax) {
    if (!normalize_coordinates) return {xmin, ymin, xmax, ymax};
    if (!(source_xmax > source_xmin && source_ymax > source_ymin)) {
        throw std::runtime_error("invalid qmap_benchmark coordinate normalization bounds");
    }
    const auto xscale = source_xmax - source_xmin;
    const auto yscale = source_ymax - source_ymin;
    return {
        (xmin - source_xmin) / xscale,
        (ymin - source_ymin) / yscale,
        (xmax - source_xmin) / xscale,
        (ymax - source_ymin) / yscale,
    };
}

}  // namespace

extern "C" void _PG_init(void) {
    DefineCustomStringVariable(
        "qmap_benchmark.index_root",
        "Directory containing the source-audited static index files.",
        nullptr,
        &index_root,
        "",
        PGC_USERSET,
        0,
        nullptr,
        nullptr,
        nullptr);
    DefineCustomBoolVariable(
        "qmap_benchmark.normalize_coordinates",
        "Apply the frozen shared affine transform before learned-index queries.",
        nullptr, &normalize_coordinates, false, PGC_USERSET, 0,
        nullptr, nullptr, nullptr);
    DefineCustomRealVariable(
        "qmap_benchmark.source_xmin", "Source-coordinate lower x bound.", nullptr,
        &source_xmin, 0.0, -DBL_MAX, DBL_MAX, PGC_USERSET, 0, nullptr, nullptr, nullptr);
    DefineCustomRealVariable(
        "qmap_benchmark.source_xmax", "Source-coordinate upper x bound.", nullptr,
        &source_xmax, 1.0, -DBL_MAX, DBL_MAX, PGC_USERSET, 0, nullptr, nullptr, nullptr);
    DefineCustomRealVariable(
        "qmap_benchmark.source_ymin", "Source-coordinate lower y bound.", nullptr,
        &source_ymin, 0.0, -DBL_MAX, DBL_MAX, PGC_USERSET, 0, nullptr, nullptr, nullptr);
    DefineCustomRealVariable(
        "qmap_benchmark.source_ymax", "Source-coordinate upper y bound.", nullptr,
        &source_ymax, 1.0, -DBL_MAX, DBL_MAX, PGC_USERSET, 0, nullptr, nullptr, nullptr);
}

extern "C" Datum qmap_range_query(PG_FUNCTION_ARGS) {
    FuncCallContext* function_context;
    if (SRF_IS_FIRSTCALL()) {
        const std::string method(text_to_cstring(PG_GETARG_TEXT_PP(0)));
        const auto coordinates = transform(
            PG_GETARG_FLOAT8(1), PG_GETARG_FLOAT8(2),
            PG_GETARG_FLOAT8(3), PG_GETARG_FLOAT8(4));
        std::array<char, 1024> error{};
        std::uint32_t* ids = nullptr;
        std::size_t count = 0;
        std::size_t candidates = 0;
        try {
            const auto status = qmap_runtime_query(
                get_handle(method), coordinates.xmin, coordinates.ymin,
                coordinates.xmax, coordinates.ymax,
                &ids, &count, &candidates, error.data(), error.size());
            if (status != 0) throw std::runtime_error(error.data());
            ++fairness_counters[method].query_count;
        } catch (const std::exception& exception) {
            ereport(ERROR, (errcode(ERRCODE_EXTERNAL_ROUTINE_EXCEPTION), errmsg("%s", exception.what())));
        }

        function_context = SRF_FIRSTCALL_INIT();
        MemoryContext old_context = MemoryContextSwitchTo(function_context->multi_call_memory_ctx);
        auto* rows = static_cast<QueryRows*>(palloc0(sizeof(QueryRows)));
        rows->ids = ids;
        rows->count = count;
        rows->cleanup.func = release_rows;
        rows->cleanup.arg = rows;
        MemoryContextRegisterResetCallback(function_context->multi_call_memory_ctx,&rows->cleanup);
        function_context->user_fctx = rows;
        function_context->max_calls = count;
        MemoryContextSwitchTo(old_context);
    }

    function_context = SRF_PERCALL_SETUP();
    auto* rows = static_cast<QueryRows*>(function_context->user_fctx);
    if (function_context->call_cntr < rows->count) {
        // SRF_RETURN_NEXT increments call_cntr before evaluating its result
        // argument, so capture the current row first.
        const auto point_id = rows->ids[function_context->call_cntr];
        SRF_RETURN_NEXT(function_context, Int64GetDatum(point_id));
    }
    qmap_runtime_free_ids(rows->ids);
    rows->ids = nullptr;
    SRF_RETURN_DONE(function_context);
}

extern "C" Datum qmap_range_count(PG_FUNCTION_ARGS) {
    std::array<char, 1024> error{};
    std::size_t count = 0;
    std::size_t candidates = 0;
    try {
        auto* binding = count_binding(fcinfo);
        const auto coordinates = transform(
            PG_GETARG_FLOAT8(1), PG_GETARG_FLOAT8(2),
            PG_GETARG_FLOAT8(3), PG_GETARG_FLOAT8(4));
        const auto status = qmap_runtime_count(
            binding->handle, coordinates.xmin, coordinates.ymin,
            coordinates.xmax, coordinates.ymax,
            &count, &candidates, error.data(), error.size());
        if (status != 0) throw std::runtime_error(error.data());
        ++binding->counters->query_count;
    } catch (const std::exception& exception) {
        ereport(ERROR, (errcode(ERRCODE_EXTERNAL_ROUTINE_EXCEPTION), errmsg("%s", exception.what())));
    }
    PG_RETURN_INT64(static_cast<std::int64_t>(count));
}

extern "C" Datum qmap_preload_index(PG_FUNCTION_ARGS) {
    const std::string method(text_to_cstring(PG_GETARG_TEXT_PP(0)));
    try {
        (void)get_handle(method);
    } catch (const std::exception& exception) {
        ereport(ERROR, (errcode(ERRCODE_EXTERNAL_ROUTINE_EXCEPTION), errmsg("%s", exception.what())));
    }
    PG_RETURN_BOOL(true);
}

extern "C" Datum qmap_fairness_counters(PG_FUNCTION_ARGS) {
    const std::string method(text_to_cstring(PG_GETARG_TEXT_PP(0)));
    if (!supported(method)) {
        ereport(ERROR, (errcode(ERRCODE_INVALID_PARAMETER_VALUE), errmsg("unsupported method: %s", method.c_str())));
    }
    const auto& counters = fairness_counters[method];
    const auto value = std::string("{\"method\":\"") + method
        + "\",\"load_count\":" + std::to_string(counters.load_count)
        + ",\"query_count\":" + std::to_string(counters.query_count)
        + ",\"query_rebuild_count\":" + std::to_string(counters.query_rebuild_count)
        + ",\"query_reload_count\":" + std::to_string(counters.query_reload_count)
        + ",\"query_training_count\":" + std::to_string(counters.query_training_count)
        + ",\"query_external_process_count\":" + std::to_string(counters.query_external_process_count)
        + ",\"query_python_count\":" + std::to_string(counters.query_python_count)
        + ",\"query_quantum_count\":" + std::to_string(counters.query_quantum_count) + "}";
    PG_RETURN_TEXT_P(cstring_to_text(value.c_str()));
}

extern "C" Datum qmap_reset_index_cache(PG_FUNCTION_ARGS) {
    handles.clear();
    fairness_counters.clear();
    ++cache_generation;
    PG_RETURN_VOID();
}

extern "C" Datum qmap_profile_query(PG_FUNCTION_ARGS) {
    using Clock = std::chrono::steady_clock;
    const auto started = Clock::now();
    const std::string method(text_to_cstring(PG_GETARG_TEXT_PP(0)));
    const auto entry_end = Clock::now();
    qmap_query_profile p{};
    std::array<char,1024> error{};
    std::uint64_t adapter_ns = 0;
    try {
        const auto c = transform(PG_GETARG_FLOAT8(1),PG_GETARG_FLOAT8(2),PG_GETARG_FLOAT8(3),PG_GETARG_FLOAT8(4));
        auto* handle = get_handle(method);
        adapter_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-entry_end).count();
        if (qmap_runtime_profile_query(handle,c.xmin,c.ymin,c.xmax,c.ymax,&p,error.data(),error.size()))
            throw std::runtime_error(error.data());
    } catch (const std::exception& exception) {
        ereport(ERROR,(errcode(ERRCODE_EXTERNAL_ROUTINE_EXCEPTION),errmsg("%s",exception.what())));
    }
    const auto entry_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(entry_end-started).count();
    const auto total_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-started).count();
    const auto residual_ns = static_cast<int64_t>(total_ns-entry_ns-adapter_ns)
        - static_cast<int64_t>(p.traversal_ns+p.leaf_access_ns+p.refinement_ns+p.result_count_ns);
    const auto value = std::string("{\"result_count\":")+std::to_string(p.result_count)
        +",\"candidates\":"+std::to_string(p.candidate_count)+",\"internal\":"+std::to_string(p.visited_internal_nodes)
        +",\"leaves\":"+std::to_string(p.visited_leaves)+",\"crosses\":"+std::to_string(p.cross_partitions)
        +",\"depth\":"+std::to_string(p.depth)+",\"sql_entry_ns\":"+std::to_string(entry_ns)
        +",\"adapter_ns\":"+std::to_string(adapter_ns)+",\"traversal_ns\":"+std::to_string(p.traversal_ns)
        +",\"leaf_access_ns\":"+std::to_string(p.leaf_access_ns)+",\"refinement_ns\":"+std::to_string(p.refinement_ns)
        +",\"result_count_ns\":"+std::to_string(p.result_count_ns)+",\"measurement_residual_ns\":"+std::to_string(residual_ns)
        +",\"total_ns\":"+std::to_string(total_ns)+"}";
    PG_RETURN_TEXT_P(cstring_to_text(value.c_str()));
}
