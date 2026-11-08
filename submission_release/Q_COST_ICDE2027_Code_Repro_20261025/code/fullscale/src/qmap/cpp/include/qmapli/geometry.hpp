#pragma once

#include <cstdint>

namespace qmapli {

struct Point {
    float x;
    float y;
    std::uint32_t id;
};

struct Rect {
    // Query files and the PostgreSQL API use doubles. Keeping the public
    // rectangle at that precision prevents boundary expansion/contraction
    // before exact refinement against the stored float coordinates.
    double xmin;
    double ymin;
    double xmax;
    double ymax;
};

bool contains(const Rect& rect, const Point& point) noexcept;

}  // namespace qmapli
