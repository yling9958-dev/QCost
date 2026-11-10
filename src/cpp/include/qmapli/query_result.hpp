#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace qmapli {

struct QueryResult {
    std::vector<std::uint32_t> ids;
    std::size_t candidates = 0;
    std::size_t visited_leaves = 0;
    std::size_t cross_partitions = 0;
    std::size_t visited_internal_nodes = 0;
    std::uint64_t traversal_ns = 0;
    std::uint64_t refinement_ns = 0;
    std::uint64_t leaf_access_ns = 0;
    std::uint64_t result_count_ns = 0;
    std::size_t max_depth_encountered = 0;
    std::size_t matched_count = 0;
};

struct CountResult {
    std::size_t count = 0;
    std::size_t candidates = 0;
};

}  // namespace qmapli
