#include "qmapli/formal_baselines.hpp"
#include <stdexcept>

namespace qmapli {
// The final registry excludes RSMI. Retain only its frozen unavailable factory.
std::unique_ptr<RangeIndex> make_official_rsmi(const std::filesystem::path& model_prefix) {
    (void)model_prefix;
    throw std::runtime_error("RSMI support is unavailable: configure QMAP_ENABLE_RSMI with LibTorch");
}
}  // namespace qmapli
