#pragma once

#include <memory>

#include "qmapli/range_index.hpp"

namespace qmapli {

std::unique_ptr<RangeIndex> make_static_qmap_index(const std::string& method);

}  // namespace qmapli
