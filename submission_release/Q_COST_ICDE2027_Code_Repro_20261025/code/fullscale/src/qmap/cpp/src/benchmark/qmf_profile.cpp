#include "qmapli/runtime_c_api.h"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <new>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
thread_local std::size_t allocation_count = 0;
thread_local std::size_t allocated_bytes = 0;
}

void* operator new(std::size_t size) {
    void* storage = std::malloc(size ? size : 1);
    if (!storage) throw std::bad_alloc();
    ++allocation_count;
    allocated_bytes += size;
    return storage;
}
void operator delete(void* storage) noexcept { std::free(storage); }
void operator delete(void* storage, std::size_t) noexcept { std::free(storage); }
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete[](void* storage) noexcept { std::free(storage); }
void operator delete[](void* storage, std::size_t) noexcept { std::free(storage); }

namespace {
using Clock = std::chrono::steady_clock;
struct Query {
    std::string identifier, group, split;
    double xmin, ymin, xmax, ymax;
};
struct Measurement {
    std::size_t count = 0, candidates = 0, leaves = 0, crosses = 0, internal = 0;
    std::size_t allocations = 0, bytes = 0;
    std::uint64_t total = 0, traversal = 0, refinement = 0;
};

std::vector<std::string> fields(const std::string& line) {
    std::stringstream stream(line);
    std::vector<std::string> result;
    std::string value;
    while (std::getline(stream, value, ',')) result.push_back(value);
    return result;
}

Measurement execute(qmap_runtime_handle* handle, const Query& query, bool diagnostics) {
    Measurement result;
    char error[1024]{};
    std::uint32_t* identifiers = nullptr;
    const auto before_count = allocation_count;
    const auto before_bytes = allocated_bytes;
    const auto started = Clock::now();
    const auto status = diagnostics
        ? qmap_runtime_query_breakdown(handle, query.xmin, query.ymin, query.xmax, query.ymax,
            &identifiers, &result.count, &result.candidates, &result.leaves, &result.crosses,
            &result.internal, &result.traversal, &result.refinement, error, sizeof(error))
        : qmap_runtime_count(handle, query.xmin, query.ymin, query.xmax, query.ymax,
            &result.count, &result.candidates, error, sizeof(error));
    result.total = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-started).count();
    result.allocations = allocation_count-before_count;
    result.bytes = allocated_bytes-before_bytes;
    qmap_runtime_free_ids(identifiers);
    if (status) throw std::runtime_error(error);
    return result;
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 6) throw std::invalid_argument("method index normalized-query-csv output mode=count|diagnostics");
        std::ifstream source(argv[3]);
        if (!source) throw std::runtime_error("query file unavailable");
        std::string line;
        std::getline(source, line);
        std::vector<Query> warmup, queries;
        while (std::getline(source, line)) {
            auto row = fields(line);
            if (row.size() < 7) throw std::runtime_error("invalid query record");
            Query query{row[0], row[1], row[2], std::stod(row[3]), std::stod(row[4]), std::stod(row[5]), std::stod(row[6])};
            if (query.split == "warmup") warmup.push_back(query);
            if (query.split == "performance") queries.push_back(query);
        }
        char error[1024]{};
        auto* handle = qmap_runtime_open(argv[1], argv[2], error, sizeof(error));
        if (!handle) throw std::runtime_error(error);
        const bool diagnostics = std::string(argv[5]) == "diagnostics";
        for (const auto& query : warmup) (void)execute(handle, query, diagnostics);
        std::vector<Measurement> measurements;
        measurements.reserve(queries.size());
        for (const auto& query : queries) measurements.push_back(execute(handle, query, diagnostics));
        std::ofstream output(argv[4]);
        output << "query_id,selectivity_group,result_count,candidate_count,visited_internal_nodes,visited_leaves,cross_partition_count,traversal_ns,refinement_ns,total_ns,heap_allocations,allocated_bytes\n";
        for (std::size_t ordinal = 0; ordinal < queries.size(); ++ordinal) {
            const auto& query = queries[ordinal];
            const auto& result = measurements[ordinal];
            output << query.identifier << ',' << query.group << ',' << result.count << ',' << result.candidates
                   << ',' << result.internal << ',' << result.leaves << ',' << result.crosses << ',' << result.traversal
                   << ',' << result.refinement << ',' << result.total << ',' << result.allocations << ',' << result.bytes << '\n';
        }
        qmap_runtime_close(handle);
        std::cout << "queries=" << measurements.size() << " warmup=" << warmup.size() << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
