#pragma once

#include <filesystem>
#include <memory>
#include <string>
#include <vector>

#include "qmapli/range_index.hpp"

namespace qmapli {

struct BaselineBuildContext {
    std::vector<Rect> training_queries;
    std::vector<Rect> validation_queries;
    std::filesystem::path bmtree_model;
    std::filesystem::path rsmi_model_prefix;
};

std::unique_ptr<RangeIndex> make_formal_baseline(
    const std::string& name,
    BaselineBuildContext context = {});

std::unique_ptr<RangeIndex> make_learnedbench_flood(
    const std::vector<Rect>& training_queries);
std::unique_ptr<RangeIndex> make_learnedbench_lisa();
std::unique_ptr<RangeIndex> make_official_rsmi(
    const std::filesystem::path& model_prefix);

std::vector<std::string> formal_baseline_names();

}  // namespace qmapli
