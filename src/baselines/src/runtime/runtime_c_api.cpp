#include "qmapli/runtime_c_api.h"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <memory>
#include <stdexcept>
#include <string>

#include "qmapli/formal_baselines.hpp"
#include "qmapli/static_qmap_index.hpp"

struct qmap_runtime_handle {
    std::unique_ptr<qmapli::RangeIndex> index;
};

namespace {

void set_error(char* destination, std::size_t size, const char* message) {
    if (!destination || size == 0) return;
    std::strncpy(destination, message, size - 1);
    destination[size - 1] = '\0';
}

bool is_qmap(const std::string& method) {
    return method.rfind("qmap_", 0) == 0;
}

}  // namespace

extern "C" qmap_runtime_handle* qmap_runtime_open(
    const char* method, const char* index_path, char* error, size_t error_size) {
    try {
        if (!method || !index_path) throw std::invalid_argument("method and index path are required");
        auto handle = std::make_unique<qmap_runtime_handle>();
        const std::string name(method);
        handle->index = is_qmap(name) ? qmapli::make_static_qmap_index(name)
                                     : qmapli::make_formal_baseline(name);
        handle->index->load(index_path);
        return handle.release();
    } catch (const std::exception& exception) {
        set_error(error, error_size, exception.what());
        return nullptr;
    }
}

extern "C" int qmap_runtime_query(
    qmap_runtime_handle* handle, double xmin, double ymin, double xmax, double ymax,
    uint32_t** ids, size_t* count, size_t* candidates, char* error, size_t error_size) {
    std::size_t visited_leaves = 0;
    std::size_t cross_partitions = 0;
    std::size_t visited_internal_nodes = 0;
    return qmap_runtime_query_diagnostics(
        handle, xmin, ymin, xmax, ymax, ids, count, candidates,
        &visited_leaves, &cross_partitions, &visited_internal_nodes,
        error, error_size);
}

extern "C" int qmap_runtime_count(
    qmap_runtime_handle* handle, double xmin, double ymin, double xmax, double ymax,
    size_t* count, size_t* candidates, char* error, size_t error_size) {
    try {
        if (!handle || !count || !candidates) throw std::invalid_argument("invalid count arguments");
        if (xmin > xmax || ymin > ymax) throw std::invalid_argument("invalid query rectangle");
        const auto result = handle->index->range_count({xmin, ymin, xmax, ymax});
        *count = result.count;
        *candidates = result.candidates;
        return 0;
    } catch (const std::exception& exception) {
        set_error(error, error_size, exception.what());
        return 1;
    }
}

extern "C" int qmap_runtime_query_diagnostics(
    qmap_runtime_handle* handle, double xmin, double ymin, double xmax, double ymax,
    uint32_t** ids, size_t* count, size_t* candidates, size_t* visited_leaves,
    size_t* cross_partitions, size_t* visited_internal_nodes,
    char* error, size_t error_size) {
    return qmap_runtime_query_breakdown(
        handle, xmin, ymin, xmax, ymax, ids, count, candidates,
        visited_leaves, cross_partitions, visited_internal_nodes,
        nullptr, nullptr, error, error_size);
}

extern "C" int qmap_runtime_query_breakdown(
    qmap_runtime_handle* handle, double xmin, double ymin, double xmax, double ymax,
    uint32_t** ids, size_t* count, size_t* candidates, size_t* visited_leaves,
    size_t* cross_partitions, size_t* visited_internal_nodes,
    uint64_t* traversal_ns, uint64_t* refinement_ns,
    char* error, size_t error_size) {
    try {
        if (!handle || !ids || !count || !candidates) throw std::invalid_argument("invalid query arguments");
        if (xmin > xmax || ymin > ymax) throw std::invalid_argument("invalid query rectangle");
        auto result = handle->index->range_query({xmin, ymin, xmax, ymax});
        *count = result.ids.size();
        *candidates = result.candidates;
        if (visited_leaves) *visited_leaves = result.visited_leaves;
        if (cross_partitions) *cross_partitions = result.cross_partitions;
        if (visited_internal_nodes) *visited_internal_nodes = result.visited_internal_nodes;
        if (traversal_ns) *traversal_ns = result.traversal_ns;
        if (refinement_ns) *refinement_ns = result.refinement_ns;
        *ids = nullptr;
        if (!result.ids.empty()) {
            *ids = static_cast<uint32_t*>(std::malloc(result.ids.size() * sizeof(uint32_t)));
            if (!*ids) throw std::bad_alloc();
            std::memcpy(*ids, result.ids.data(), result.ids.size() * sizeof(uint32_t));
        }
        return 0;
    } catch (const std::exception& exception) {
        set_error(error, error_size, exception.what());
        return 1;
    }
}

extern "C" void qmap_runtime_free_ids(uint32_t* ids) { std::free(ids); }

extern "C" int qmap_runtime_profile_query(
    qmap_runtime_handle* handle, double xmin, double ymin, double xmax, double ymax,
    qmap_query_profile* profile, char* error, size_t error_size) {
    try {
        if (!handle || !profile) throw std::invalid_argument("invalid profile arguments");
        const auto started = std::chrono::steady_clock::now();
        auto result = handle->index->range_query({xmin,ymin,xmax,ymax});
        *profile = {result.ids.size(), result.candidates, result.visited_internal_nodes,
                    result.visited_leaves, result.cross_partitions, result.max_depth_encountered,
                    result.traversal_ns, result.leaf_access_ns, result.refinement_ns,
                    result.result_count_ns,
                    static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
                        std::chrono::steady_clock::now()-started).count())};
        return 0;
    } catch (const std::exception& exception) {
        set_error(error,error_size,exception.what());
        return 1;
    }
}

extern "C" void qmap_runtime_close(qmap_runtime_handle* handle) { delete handle; }
