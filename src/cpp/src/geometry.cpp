#include "qmapli/geometry.hpp"

namespace qmapli {

bool contains(const Rect& rect, const Point& point) noexcept {
    return point.x >= rect.xmin && point.x <= rect.xmax &&
           point.y >= rect.ymin && point.y <= rect.ymax;
}

}  // namespace qmapli
