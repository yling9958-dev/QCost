#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

#include "qmapli/geometry.hpp"
#include "qmapli/query_result.hpp"

namespace qmapli {

struct PersistenceInstrumentation {
    std::size_t sort_count = 0;
    std::size_t fit_count = 0;
    std::size_t partition_count = 0;
    std::size_t tree_build_count = 0;
    std::size_t model_generation_count = 0;
    bool query_ready = false;
};

class RangeIndex {
public:
    virtual ~RangeIndex() = default;
    virtual std::string method_name() const = 0;
    virtual void build(const std::vector<Point>& points) = 0;
    virtual void save(const std::filesystem::path& path) const = 0;
    virtual void load(const std::filesystem::path& path) = 0;
    virtual QueryResult range_query(const Rect& query) const = 0;
    virtual CountResult range_count(const Rect& query) const {
        const auto result = range_query(query);
        return {result.ids.size(), result.candidates};
    }
    virtual std::size_t serialized_size_bytes() const = 0;
    virtual PersistenceInstrumentation persistence_instrumentation() const { return {}; }
};

}  // namespace qmapli
