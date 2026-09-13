#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct qmap_runtime_handle qmap_runtime_handle;

typedef struct {
    uint64_t result_count, candidate_count, visited_internal_nodes, visited_leaves;
    uint64_t cross_partitions, depth, traversal_ns, leaf_access_ns;
    uint64_t refinement_ns, result_count_ns, total_ns;
} qmap_query_profile;

int qmap_runtime_profile_query(
    qmap_runtime_handle* handle, double xmin, double ymin, double xmax, double ymax,
    qmap_query_profile* profile, char* error, size_t error_size);

qmap_runtime_handle* qmap_runtime_open(
    const char* method,
    const char* index_path,
    char* error,
    size_t error_size);

int qmap_runtime_query(
    qmap_runtime_handle* handle,
    double xmin,
    double ymin,
    double xmax,
    double ymax,
    uint32_t** ids,
    size_t* count,
    size_t* candidates,
    char* error,
    size_t error_size);

int qmap_runtime_count(
    qmap_runtime_handle* handle,
    double xmin,
    double ymin,
    double xmax,
    double ymax,
    size_t* count,
    size_t* candidates,
    char* error,
    size_t error_size);

int qmap_runtime_query_diagnostics(
    qmap_runtime_handle* handle,
    double xmin,
    double ymin,
    double xmax,
    double ymax,
    uint32_t** ids,
    size_t* count,
    size_t* candidates,
    size_t* visited_leaves,
    size_t* cross_partitions,
    size_t* visited_internal_nodes,
    char* error,
    size_t error_size);

int qmap_runtime_query_breakdown(
    qmap_runtime_handle* handle,
    double xmin,
    double ymin,
    double xmax,
    double ymax,
    uint32_t** ids,
    size_t* count,
    size_t* candidates,
    size_t* visited_leaves,
    size_t* cross_partitions,
    size_t* visited_internal_nodes,
    uint64_t* traversal_ns,
    uint64_t* refinement_ns,
    char* error,
    size_t error_size);

void qmap_runtime_free_ids(uint32_t* ids);
void qmap_runtime_close(qmap_runtime_handle* handle);

#ifdef __cplusplus
}
#endif
