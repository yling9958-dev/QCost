#include "qmapli/formal_baselines.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <utility>

#include <boost/geometry.hpp>
#include <boost/geometry/geometries/box.hpp>
#include <boost/geometry/geometries/point_xy.hpp>
#include <boost/geometry/index/rtree.hpp>
#include <morton-nd/mortonND_LUT.h>

namespace qmapli {
namespace {

constexpr std::uint32_t kFormatVersion = 2;

template <typename T>
void write_value(std::ostream& stream, const T& value) {
    stream.write(reinterpret_cast<const char*>(&value), sizeof(value));
    if (!stream) throw std::runtime_error("cannot serialize formal baseline state");
}

template <typename T>
T read_value(std::istream& stream) {
    T value{};
    stream.read(reinterpret_cast<char*>(&value), sizeof(value));
    if (!stream) throw std::runtime_error("truncated formal baseline state");
    return value;
}

class StoredPointIndex : public RangeIndex {
public:
    explicit StoredPointIndex(std::string method) : method_(std::move(method)) {}

    std::string method_name() const override { return method_; }

    void build(const std::vector<Point>& points) override {
        points_ = points;
        rebuild();
    }

    void save(const std::filesystem::path& path) const override {
        std::ofstream stream(path, std::ios::binary | std::ios::trunc);
        if (!stream) {
            throw std::runtime_error("cannot create index file: " + path.string());
        }
        const std::uint64_t count = points_.size();
        write_value(stream, kFormatVersion);
        write_value(stream, count);
        stream.write(reinterpret_cast<const char*>(points_.data()),
                     static_cast<std::streamsize>(points_.size() * sizeof(Point)));
        save_query_state(stream);
        if (!stream) throw std::runtime_error("cannot finish formal baseline index: " + path.string());
    }

    void load(const std::filesystem::path& path) override {
        std::ifstream stream(path, std::ios::binary);
        if (!stream) {
            throw std::runtime_error("cannot open index file: " + path.string());
        }
        std::uint32_t version = 0;
        std::uint64_t count = 0;
        version = read_value<std::uint32_t>(stream);
        count = read_value<std::uint64_t>(stream);
        if (version != kFormatVersion) {
            throw std::runtime_error("unsupported formal baseline index version");
        }
        points_.resize(static_cast<std::size_t>(count));
        stream.read(reinterpret_cast<char*>(points_.data()),
                    static_cast<std::streamsize>(points_.size() * sizeof(Point)));
        if (!stream) throw std::runtime_error("truncated formal baseline points");
        load_instrumentation_ = {};
        load_query_state(stream);
        load_instrumentation_.query_ready = query_state_is_ready();
    }

    std::size_t serialized_size_bytes() const override {
        return sizeof(kFormatVersion) + sizeof(std::uint64_t) + points_.size() * sizeof(Point)
            + metadata_size();
    }

    PersistenceInstrumentation persistence_instrumentation() const override {
        return load_instrumentation_;
    }

protected:
    virtual void rebuild() = 0;
    virtual void save_query_state(std::ostream&) const = 0;
    virtual void load_query_state(std::istream&) = 0;
    virtual bool query_state_is_ready() const { return true; }
    virtual std::size_t metadata_size() const { return 0; }

    QueryResult refine_positions(const Rect& query, const std::vector<std::size_t>& positions) const {
        QueryResult result;
        result.candidates = positions.size();
        result.ids.reserve(positions.size());
        for (const auto position : positions) {
            const auto& point = points_[position];
            if (contains(query, point)) {
                result.ids.push_back(point.id);
            }
        }
        std::sort(result.ids.begin(), result.ids.end());
        return result;
    }

    std::string method_;
    std::vector<Point> points_;
    PersistenceInstrumentation load_instrumentation_{};
};

std::uint32_t quantize(double value, unsigned bits) {
    const auto clipped = std::clamp(value, 0.0, 1.0);
    const auto scale = static_cast<double>((std::uint64_t{1} << bits) - 1);
    return static_cast<std::uint32_t>(std::floor(clipped * scale));
}

std::uint64_t morton_encode(std::uint32_t x, std::uint32_t y, unsigned bits) {
    if (bits == 16U) {
        static constexpr mortonnd::MortonNDLutEncoder<2, 16, 8> encoder;
        // The project convention places y in even positions and x in odd
        // positions. morton-nd places its first input in even positions.
        return encoder.Encode(y, x);
    }
    std::uint64_t code = 0;
    for (unsigned bit = 0; bit < bits; ++bit) {
        code |= static_cast<std::uint64_t>((y >> bit) & 1U) << (2U * bit);
        code |= static_cast<std::uint64_t>((x >> bit) & 1U) << (2U * bit + 1U);
    }
    return code;
}

struct CodeInterval {
    std::uint64_t low;
    std::uint64_t high;
};

void decompose_prefix(
    unsigned depth,
    unsigned target_depth,
    unsigned code_bits,
    std::uint32_t xmin,
    std::uint32_t ymin,
    std::uint32_t size,
    std::uint64_t prefix,
    const std::array<std::uint32_t, 4>& query,
    std::vector<CodeInterval>& output) {
    const auto xmax = xmin + size - 1U;
    const auto ymax = ymin + size - 1U;
    if (xmax < query[0] || xmin > query[2] || ymax < query[1] || ymin > query[3]) {
        return;
    }
    const bool covered = query[0] <= xmin && xmax <= query[2]
        && query[1] <= ymin && ymax <= query[3];
    if (covered || depth == target_depth) {
        const auto remaining = code_bits - depth;
        const auto shift = 2U * remaining;
        const auto low = prefix << shift;
        const auto mask = shift == 64U ? std::numeric_limits<std::uint64_t>::max()
                                       : ((std::uint64_t{1} << shift) - 1U);
        output.push_back({low, low | mask});
        return;
    }
    const auto half = size / 2U;
    for (std::uint64_t child = 0; child < 4; ++child) {
        const auto xbit = static_cast<std::uint32_t>((child >> 1U) & 1U);
        const auto ybit = static_cast<std::uint32_t>(child & 1U);
        decompose_prefix(
            depth + 1U,
            target_depth,
            code_bits,
            xmin + xbit * half,
            ymin + ybit * half,
            half,
            (prefix << 2U) | child,
            query,
            output);
    }
}

class ZOrderBigMinIndex final : public StoredPointIndex {
public:
    ZOrderBigMinIndex() : StoredPointIndex("Z-order-BigMin") {}

    QueryResult range_query(const Rect& query) const override {
        const std::array<std::uint32_t, 4> quantized{
            quantize(query.xmin, kBits), quantize(query.ymin, kBits),
            quantize(query.xmax, kBits), quantize(query.ymax, kBits)};
        std::vector<CodeInterval> intervals;
        decompose_prefix(0, kDirectoryBits, kBits, 0, 0, 1U << kBits, 0, quantized, intervals);
        std::vector<std::size_t> candidates;
        for (const auto interval : intervals) {
            const auto lower = std::lower_bound(codes_.begin(), codes_.end(), interval.low,
                [](const auto& row, auto value) { return row.first < value; });
            const auto upper = std::upper_bound(codes_.begin(), codes_.end(), interval.high,
                [](auto value, const auto& row) { return value < row.first; });
            for (auto iterator = lower; iterator != upper; ++iterator) {
                candidates.push_back(iterator->second);
            }
        }
        return refine_positions(query, candidates);
    }

protected:
    void rebuild() override {
        codes_.clear();
        codes_.reserve(points_.size());
        for (std::size_t index = 0; index < points_.size(); ++index) {
            codes_.push_back({morton_encode(quantize(points_[index].x, kBits),
                                            quantize(points_[index].y, kBits), kBits), index});
        }
        std::stable_sort(codes_.begin(), codes_.end());
    }

    std::size_t metadata_size() const override { return codes_.size() * sizeof(codes_[0]); }

    void save_query_state(std::ostream& stream) const override {
        write_value(stream, static_cast<std::uint64_t>(codes_.size()));
        for (const auto& [code, position] : codes_) {
            write_value(stream, code);
            write_value(stream, static_cast<std::uint64_t>(position));
        }
    }

    void load_query_state(std::istream& stream) override {
        const auto count = read_value<std::uint64_t>(stream);
        codes_.clear();
        codes_.reserve(static_cast<std::size_t>(count));
        for (std::uint64_t row = 0; row < count; ++row) {
            const auto code = read_value<std::uint64_t>(stream);
            const auto position = read_value<std::uint64_t>(stream);
            if (position >= points_.size()) throw std::runtime_error("Z-order position out of range");
            codes_.push_back({code, static_cast<std::size_t>(position)});
        }
    }

private:
    static constexpr unsigned kBits = 16;
    static constexpr unsigned kDirectoryBits = 12;
    std::vector<std::pair<std::uint64_t, std::size_t>> codes_;
};

class BoostRStarIndex final : public StoredPointIndex {
public:
    explicit BoostRStarIndex(std::vector<Rect> selection_queries)
        : StoredPointIndex("Boost R*-tree 1.74"), selection_queries_(std::move(selection_queries)) {}

    std::string method_name() const override {
        if (variant_ == Variant::quadratic) return "Boost quadratic R-tree 1.74";
        if (variant_ == Variant::incremental_rstar) return "Boost R*-tree 1.74";
        return "Boost packed R*-tree 1.74";
    }

    QueryResult range_query(const Rect& query) const override {
        Box box(BGPoint(query.xmin, query.ymin), BGPoint(query.xmax, query.ymax));
        std::vector<Value> hits;
        if (variant_ == Variant::quadratic) {
            quadratic_tree_->query(boost::geometry::index::intersects(box), std::back_inserter(hits));
        } else {
            rstar_tree_->query(boost::geometry::index::intersects(box), std::back_inserter(hits));
        }
        std::vector<std::size_t> positions;
        positions.reserve(hits.size());
        for (const auto& hit : hits) {
            positions.push_back(hit.second);
        }
        return refine_positions(query, positions);
    }

protected:
    void rebuild() override {
        std::vector<Value> values;
        values.reserve(points_.size());
        for (std::size_t index = 0; index < points_.size(); ++index) {
            values.push_back({BGPoint(points_[index].x, points_[index].y), index});
        }
        auto quadratic = std::make_unique<QuadraticTree>();
        auto incremental_rstar = std::make_unique<RStarTree>();
        for (const auto& value : values) {
            quadratic->insert(value);
            incremental_rstar->insert(value);
        }
        auto packed_rstar = std::make_unique<RStarTree>(values.begin(), values.end());
        variant_ = Variant::packed_rstar;
        if (!selection_queries_.empty()) {
            const auto quadratic_ns = selection_time(*quadratic);
            const auto incremental_ns = selection_time(*incremental_rstar);
            const auto packed_ns = selection_time(*packed_rstar);
            if (quadratic_ns <= incremental_ns && quadratic_ns <= packed_ns) {
                variant_ = Variant::quadratic;
            } else if (incremental_ns <= packed_ns) {
                variant_ = Variant::incremental_rstar;
            }
        }
        quadratic_tree_.reset();
        rstar_tree_.reset();
        if (variant_ == Variant::quadratic) {
            quadratic_tree_ = std::move(quadratic);
        } else if (variant_ == Variant::incremental_rstar) {
            rstar_tree_ = std::move(incremental_rstar);
        } else {
            rstar_tree_ = std::move(packed_rstar);
        }
    }

    std::size_t metadata_size() const override { return points_.size() * sizeof(Value); }

    void save_query_state(std::ostream& stream) const override {
        write_value(stream, static_cast<std::uint8_t>(variant_));
    }

    void load_query_state(std::istream& stream) override {
        const auto stored_variant = read_value<std::uint8_t>(stream);
        if (stored_variant > static_cast<std::uint8_t>(Variant::packed_rstar)) {
            throw std::runtime_error("invalid stored R-tree variant");
        }
        variant_ = static_cast<Variant>(stored_variant);
        std::vector<Value> values;
        values.reserve(points_.size());
        for (std::size_t index = 0; index < points_.size(); ++index) {
            values.push_back({BGPoint(points_[index].x, points_[index].y), index});
        }
        quadratic_tree_.reset();
        rstar_tree_.reset();
        if (variant_ == Variant::quadratic) {
            quadratic_tree_ = std::make_unique<QuadraticTree>();
            for (const auto& value : values) quadratic_tree_->insert(value);
        } else if (variant_ == Variant::incremental_rstar) {
            rstar_tree_ = std::make_unique<RStarTree>();
            for (const auto& value : values) rstar_tree_->insert(value);
        } else {
            rstar_tree_ = std::make_unique<RStarTree>(values.begin(), values.end());
        }
        load_instrumentation_.tree_build_count = 1;
    }

    bool query_state_is_ready() const override { return false; }

private:
    // Queries arrive as doubles. A double-valued Boost box keeps candidate
    // generation conservative at boundaries; stored point coordinates are
    // promoted exactly from float.
    using BGPoint = boost::geometry::model::d2::point_xy<double>;
    using Box = boost::geometry::model::box<BGPoint>;
    using Value = std::pair<BGPoint, std::size_t>;
    using QuadraticTree = boost::geometry::index::rtree<Value, boost::geometry::index::quadratic<16>>;
    using RStarTree = boost::geometry::index::rtree<Value, boost::geometry::index::rstar<16>>;
    enum class Variant { quadratic, incremental_rstar, packed_rstar };

    template <typename Tree>
    std::uint64_t selection_time(const Tree& tree) const {
        std::uint64_t best = std::numeric_limits<std::uint64_t>::max();
        volatile std::size_t sink = 0;
        for (int repeat = 0; repeat < 3; ++repeat) {
            const auto start = std::chrono::steady_clock::now();
            for (const auto& query : selection_queries_) {
                const Box box(BGPoint(query.xmin, query.ymin), BGPoint(query.xmax, query.ymax));
                std::vector<Value> hits;
                tree.query(boost::geometry::index::intersects(box), std::back_inserter(hits));
                sink += hits.size();
            }
            const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - start).count();
            best = std::min(best, static_cast<std::uint64_t>(elapsed));
        }
        (void)sink;
        return best;
    }

    std::vector<Rect> selection_queries_;
    Variant variant_ = Variant::packed_rstar;
    std::unique_ptr<QuadraticTree> quadratic_tree_;
    std::unique_ptr<RStarTree> rstar_tree_;
};

class TsunamiIndex final : public StoredPointIndex {
public:
    explicit TsunamiIndex(std::vector<Rect> training_queries)
        : StoredPointIndex("Tsunami-reproduced"), training_queries_(std::move(training_queries)) {}

    QueryResult range_query(const Rect& query) const override {
        std::vector<std::size_t> candidates;
        const double primary_low = axis_ == 0 ? query.xmin : query.ymin;
        const double primary_high = axis_ == 0 ? query.xmax : query.ymax;
        const double secondary_low = axis_ == 0 ? query.ymin : query.xmin;
        const double secondary_high = axis_ == 0 ? query.ymax : query.xmax;
        for (const auto& leaf : leaves_) {
            if (leaf.upper < primary_low || leaf.lower > primary_high) {
                continue;
            }
            const auto mapped_a = secondary_low - (leaf.slope * primary_low + leaf.intercept);
            const auto mapped_b = secondary_low - (leaf.slope * primary_high + leaf.intercept);
            const auto mapped_c = secondary_high - (leaf.slope * primary_low + leaf.intercept);
            const auto mapped_d = secondary_high - (leaf.slope * primary_high + leaf.intercept);
            const auto residual_low = std::min({mapped_a, mapped_b, mapped_c, mapped_d});
            const auto residual_high = std::max({mapped_a, mapped_b, mapped_c, mapped_d});
            const auto lower = std::lower_bound(leaf.residuals.begin(), leaf.residuals.end(), residual_low,
                [](const auto& row, double value) { return row.first < value; });
            const auto upper = std::upper_bound(leaf.residuals.begin(), leaf.residuals.end(), residual_high,
                [](double value, const auto& row) { return value < row.first; });
            for (auto iterator = lower; iterator != upper; ++iterator) {
                candidates.push_back(iterator->second);
            }
        }
        return refine_positions(query, candidates);
    }

protected:
    struct Leaf {
        float lower;
        float upper;
        float slope;
        float intercept;
        std::vector<std::pair<float, std::size_t>> residuals;
    };

    void rebuild() override {
        float mean_width[2] = {1.0F, 1.0F};
        if (!training_queries_.empty()) {
            mean_width[0] = mean_width[1] = 0.0F;
            for (const auto& query : training_queries_) {
                mean_width[0] += query.xmax - query.xmin;
                mean_width[1] += query.ymax - query.ymin;
            }
            mean_width[0] /= training_queries_.size();
            mean_width[1] /= training_queries_.size();
        }
        axis_ = mean_width[0] <= mean_width[1] ? 0 : 1;
        constexpr std::size_t fanout = 32;
        std::vector<float> primary;
        primary.reserve(points_.size());
        for (const auto& point : points_) {
            primary.push_back(axis_ == 0 ? point.x : point.y);
        }
        std::sort(primary.begin(), primary.end());
        leaves_.assign(fanout, {});
        for (std::size_t leaf = 0; leaf < fanout; ++leaf) {
            const auto begin = leaf * primary.size() / fanout;
            const auto end = std::min(primary.size() - 1, (leaf + 1) * primary.size() / fanout);
            leaves_[leaf].lower = leaf == 0 ? -std::numeric_limits<float>::infinity() : primary[begin];
            leaves_[leaf].upper = leaf + 1 == fanout ? std::numeric_limits<float>::infinity() : primary[end];
        }
        for (std::size_t leaf_index = 0; leaf_index < leaves_.size(); ++leaf_index) {
            auto& leaf = leaves_[leaf_index];
            std::vector<std::size_t> members;
            for (std::size_t index = 0; index < points_.size(); ++index) {
                const auto value = axis_ == 0 ? points_[index].x : points_[index].y;
                const bool upper_inclusive = leaf_index + 1 == leaves_.size();
                if (value >= leaf.lower && (value < leaf.upper || (upper_inclusive && value <= leaf.upper))) {
                    members.push_back(index);
                }
            }
            double sx = 0, sy = 0, sxx = 0, sxy = 0;
            for (const auto position : members) {
                const auto x = axis_ == 0 ? points_[position].x : points_[position].y;
                const auto y = axis_ == 0 ? points_[position].y : points_[position].x;
                sx += x; sy += y; sxx += x * x; sxy += x * y;
            }
            const auto n = static_cast<double>(members.size());
            const auto denominator = n * sxx - sx * sx;
            leaf.slope = std::abs(denominator) > 1e-12 ? static_cast<float>((n * sxy - sx * sy) / denominator) : 0.0F;
            leaf.intercept = n > 0 ? static_cast<float>((sy - leaf.slope * sx) / n) : 0.0F;
            for (const auto position : members) {
                const auto x = axis_ == 0 ? points_[position].x : points_[position].y;
                const auto y = axis_ == 0 ? points_[position].y : points_[position].x;
                leaf.residuals.push_back({y - (leaf.slope * x + leaf.intercept), position});
            }
            std::stable_sort(leaf.residuals.begin(), leaf.residuals.end());
        }
    }

    std::size_t metadata_size() const override {
        std::size_t bytes = leaves_.size() * sizeof(Leaf);
        for (const auto& leaf : leaves_) bytes += leaf.residuals.size() * sizeof(leaf.residuals[0]);
        return bytes;
    }

    void save_query_state(std::ostream& stream) const override {
        write_value(stream, static_cast<std::int32_t>(axis_));
        write_value(stream, static_cast<std::uint64_t>(leaves_.size()));
        for (const auto& leaf : leaves_) {
            write_value(stream, leaf.lower);
            write_value(stream, leaf.upper);
            write_value(stream, leaf.slope);
            write_value(stream, leaf.intercept);
            write_value(stream, static_cast<std::uint64_t>(leaf.residuals.size()));
            for (const auto& [residual, position] : leaf.residuals) {
                write_value(stream, residual);
                write_value(stream, static_cast<std::uint64_t>(position));
            }
        }
    }

    void load_query_state(std::istream& stream) override {
        axis_ = read_value<std::int32_t>(stream);
        if (axis_ != 0 && axis_ != 1) throw std::runtime_error("invalid Tsunami axis");
        const auto count = read_value<std::uint64_t>(stream);
        leaves_.assign(static_cast<std::size_t>(count), {});
        for (auto& leaf : leaves_) {
            leaf.lower = read_value<float>(stream);
            leaf.upper = read_value<float>(stream);
            leaf.slope = read_value<float>(stream);
            leaf.intercept = read_value<float>(stream);
            const auto residual_count = read_value<std::uint64_t>(stream);
            leaf.residuals.reserve(static_cast<std::size_t>(residual_count));
            for (std::uint64_t row = 0; row < residual_count; ++row) {
                const auto residual = read_value<float>(stream);
                const auto position = read_value<std::uint64_t>(stream);
                if (position >= points_.size()) throw std::runtime_error("Tsunami position out of range");
                leaf.residuals.push_back({residual, static_cast<std::size_t>(position)});
            }
        }
    }

private:
    std::vector<Rect> training_queries_;
    int axis_ = 0;
    std::vector<Leaf> leaves_;
};

class LMSFCIndex final : public StoredPointIndex {
public:
    explicit LMSFCIndex(std::vector<Rect> training_queries)
        : StoredPointIndex("LMSFC-reproduced"), training_queries_(std::move(training_queries)) {}

    QueryResult range_query(const Rect& query) const override {
        const auto low = encode(query.xmin, query.ymin);
        const auto high = encode(query.xmax, query.ymax);
        const auto lower = std::lower_bound(codes_.begin(), codes_.end(), low,
            [](const auto& row, auto value) { return row.first < value; });
        const auto upper = std::upper_bound(codes_.begin(), codes_.end(), high,
            [](auto value, const auto& row) { return value < row.first; });
        std::vector<std::size_t> candidates;
        for (auto iterator = lower; iterator != upper; ++iterator) candidates.push_back(iterator->second);
        return refine_positions(query, candidates);
    }

protected:
    void rebuild() override {
        float widths[2] = {1.0F, 1.0F};
        if (!training_queries_.empty()) {
            widths[0] = widths[1] = 0;
            for (const auto& query : training_queries_) {
                widths[0] += query.xmax - query.xmin;
                widths[1] += query.ymax - query.ymin;
            }
        }
        int preferred = widths[0] <= widths[1] ? 0 : 1;
        std::vector<std::vector<std::pair<int, unsigned>>> candidates;
        candidates.push_back(alternating_schedule(preferred));
        candidates.push_back(axis_first_schedule(0));
        candidates.push_back(axis_first_schedule(1));
        schedule_ = candidates.front();
        auto best_objective = workload_objective(schedule_);
        for (const auto& candidate : candidates) {
            const auto objective = workload_objective(candidate);
            if (objective < best_objective) {
                schedule_ = candidate;
                best_objective = objective;
            }
        }

        // Online clean-room refinement: adjacent cross-axis exchanges preserve
        // each axis's MSB-to-LSB order. Training-query cost is the only signal.
        auto refined = schedule_;
        for (std::size_t position = 0; position + 1 < schedule_.size(); ++position) {
            if (schedule_[position].first == schedule_[position + 1].first) continue;
            auto candidate = schedule_;
            std::swap(candidate[position], candidate[position + 1]);
            const auto objective = workload_objective(candidate);
            if (objective < best_objective) {
                refined = std::move(candidate);
                best_objective = objective;
            }
        }
        schedule_ = std::move(refined);
        codes_.clear();
        for (std::size_t index = 0; index < points_.size(); ++index) {
            codes_.push_back({encode(points_[index].x, points_[index].y), index});
        }
        std::stable_sort(codes_.begin(), codes_.end());
    }

    std::size_t metadata_size() const override {
        return schedule_.size() * sizeof(schedule_[0]) + codes_.size() * sizeof(codes_[0]);
    }

    void save_query_state(std::ostream& stream) const override {
        write_value(stream, static_cast<std::uint64_t>(schedule_.size()));
        for (const auto& [axis, bit] : schedule_) {
            write_value(stream, static_cast<std::int32_t>(axis));
            write_value(stream, static_cast<std::uint32_t>(bit));
        }
        write_value(stream, static_cast<std::uint64_t>(codes_.size()));
        for (const auto& [code, position] : codes_) {
            write_value(stream, code);
            write_value(stream, static_cast<std::uint64_t>(position));
        }
    }

    void load_query_state(std::istream& stream) override {
        const auto schedule_count = read_value<std::uint64_t>(stream);
        schedule_.clear();
        schedule_.reserve(static_cast<std::size_t>(schedule_count));
        for (std::uint64_t row = 0; row < schedule_count; ++row) {
            const auto axis = read_value<std::int32_t>(stream);
            const auto bit = read_value<std::uint32_t>(stream);
            if ((axis != 0 && axis != 1) || bit >= kBits) {
                throw std::runtime_error("invalid LMSFC schedule");
            }
            schedule_.push_back({axis, bit});
        }
        const auto code_count = read_value<std::uint64_t>(stream);
        codes_.clear();
        codes_.reserve(static_cast<std::size_t>(code_count));
        for (std::uint64_t row = 0; row < code_count; ++row) {
            const auto code = read_value<std::uint64_t>(stream);
            const auto position = read_value<std::uint64_t>(stream);
            if (position >= points_.size()) throw std::runtime_error("LMSFC position out of range");
            codes_.push_back({code, static_cast<std::size_t>(position)});
        }
    }

private:
    std::vector<std::pair<int, unsigned>> alternating_schedule(int preferred) const {
        std::array<unsigned, 2> next{kBits, kBits};
        std::vector<std::pair<int, unsigned>> schedule;
        while (next[0] || next[1]) {
            const auto axis = next[preferred] ? preferred : 1 - preferred;
            schedule.push_back({axis, --next[axis]});
            if (next[1 - axis]) preferred = 1 - axis;
        }
        return schedule;
    }

    std::vector<std::pair<int, unsigned>> axis_first_schedule(int first) const {
        std::vector<std::pair<int, unsigned>> schedule;
        for (const auto axis : {first, 1 - first}) {
            for (unsigned bit = kBits; bit > 0; --bit) schedule.push_back({axis, bit - 1});
        }
        return schedule;
    }

    std::uint64_t encode_with_schedule(
        double x,
        double y,
        const std::vector<std::pair<int, unsigned>>& schedule) const {
        const std::array<std::uint32_t, 2> coordinates{quantize(x, kBits), quantize(y, kBits)};
        std::uint64_t value = 0;
        for (const auto& [axis, bit] : schedule) {
            value = (value << 1U) | ((coordinates[axis] >> bit) & 1U);
        }
        return value;
    }

    double workload_objective(const std::vector<std::pair<int, unsigned>>& schedule) const {
        if (training_queries_.empty() || points_.empty()) return 0.0;
        std::vector<std::uint64_t> codes;
        codes.reserve(points_.size());
        for (const auto& point : points_) codes.push_back(encode_with_schedule(point.x, point.y, schedule));
        std::sort(codes.begin(), codes.end());
        double total = 0.0;
        for (const auto& query : training_queries_) {
            const auto low = encode_with_schedule(query.xmin, query.ymin, schedule);
            const auto high = encode_with_schedule(query.xmax, query.ymax, schedule);
            total += std::upper_bound(codes.begin(), codes.end(), high)
                - std::lower_bound(codes.begin(), codes.end(), low);
        }
        return total / training_queries_.size();
    }

    std::uint64_t encode(double x, double y) const {
        return encode_with_schedule(x, y, schedule_);
    }

    static constexpr unsigned kBits = 16;
    std::vector<Rect> training_queries_;
    std::vector<std::pair<int, unsigned>> schedule_;
    std::vector<std::pair<std::uint64_t, std::size_t>> codes_;
};

class BMTreeOfficialIndex final : public StoredPointIndex {
public:
    BMTreeOfficialIndex(std::vector<Rect> training_queries, std::filesystem::path model)
        : StoredPointIndex("BMTree-official"), training_queries_(std::move(training_queries)), model_(std::move(model)) {}

    QueryResult range_query(const Rect& query) const override {
        std::vector<std::size_t> candidates;
        for (const auto& segment : segments_) {
            if (!(segment.xmax < query.xmin || segment.xmin > query.xmax
                  || segment.ymax < query.ymin || segment.ymin > query.ymax)) {
                candidates.insert(candidates.end(), segment.positions.begin(), segment.positions.end());
            }
        }
        return refine_positions(query, candidates);
    }

protected:
    struct Segment {
        float xmin = 1, ymin = 1, xmax = 0, ymax = 0;
        std::vector<std::size_t> positions;
    };

    void rebuild() override {
        schedule_ = {1, 0};
        if (official_codes_.empty() && !model_.empty()) {
            std::ifstream stream(model_);
            std::string key;
            while (stream >> key) {
                if (key == "schedule") {
                    schedule_.clear();
                    std::string schedule;
                    stream >> schedule;
                    for (const auto value : schedule) schedule_.push_back(value - '0');
                } else if (key == "codes") {
                    std::size_t count = 0;
                    stream >> count;
                    official_codes_.assign(count, 0);
                    for (std::size_t row = 0; row < count; ++row) {
                        std::size_t id = 0;
                        std::uint64_t code = 0;
                        stream >> id >> code;
                        if (id >= official_codes_.size()) throw std::runtime_error("BMTree model ID out of range");
                        official_codes_[id] = code;
                    }
                }
            }
        }
        std::vector<std::pair<std::uint64_t, std::size_t>> codes;
        for (std::size_t index = 0; index < points_.size(); ++index) {
            const auto x = quantize(points_[index].x, kBits);
            const auto y = quantize(points_[index].y, kBits);
            unsigned consumed[2] = {0, 0};
            std::uint64_t code = points_[index].id < official_codes_.size()
                ? official_codes_[points_[index].id] : 0;
            if (points_[index].id < official_codes_.size()) {
                codes.push_back({code, index});
                continue;
            }
            int previous = schedule_.empty() ? 1 : schedule_.back();
            for (const auto axis : schedule_) {
                const auto bit = kBits - 1U - consumed[axis]++;
                code = (code << 1U) | (((axis == 0 ? x : y) >> bit) & 1U);
                previous = axis;
            }
            while (consumed[0] < kBits || consumed[1] < kBits) {
                int axis = 1 - previous;
                if (consumed[axis] >= kBits) axis = 1 - axis;
                const auto bit = kBits - 1U - consumed[axis]++;
                code = (code << 1U) | (((axis == 0 ? x : y) >> bit) & 1U);
                previous = axis;
            }
            codes.push_back({code, index});
        }
        std::stable_sort(codes.begin(), codes.end());
        constexpr std::size_t segment_size = 128;
        segments_.clear();
        for (std::size_t begin = 0; begin < codes.size(); begin += segment_size) {
            Segment segment;
            const auto end = std::min(codes.size(), begin + segment_size);
            for (std::size_t offset = begin; offset < end; ++offset) {
                const auto position = codes[offset].second;
                const auto& point = points_[position];
                segment.xmin = std::min(segment.xmin, point.x);
                segment.ymin = std::min(segment.ymin, point.y);
                segment.xmax = std::max(segment.xmax, point.x);
                segment.ymax = std::max(segment.ymax, point.y);
                segment.positions.push_back(position);
            }
            segments_.push_back(std::move(segment));
        }
    }

    std::size_t metadata_size() const override {
        std::size_t bytes = schedule_.size() * sizeof(int) + segments_.size() * sizeof(Segment);
        for (const auto& segment : segments_) bytes += segment.positions.size() * sizeof(std::size_t);
        return bytes + sizeof(std::uint64_t) + official_codes_.size() * sizeof(std::uint64_t);
    }

    void save_query_state(std::ostream& stream) const override {
        write_value(stream, static_cast<std::uint64_t>(schedule_.size()));
        for (const auto axis : schedule_) write_value(stream, static_cast<std::int32_t>(axis));
        write_value(stream, static_cast<std::uint64_t>(official_codes_.size()));
        for (const auto code : official_codes_) write_value(stream, code);
        write_value(stream, static_cast<std::uint64_t>(segments_.size()));
        for (const auto& segment : segments_) {
            write_value(stream, segment.xmin);
            write_value(stream, segment.ymin);
            write_value(stream, segment.xmax);
            write_value(stream, segment.ymax);
            write_value(stream, static_cast<std::uint64_t>(segment.positions.size()));
            for (const auto position : segment.positions) {
                write_value(stream, static_cast<std::uint64_t>(position));
            }
        }
    }

    void load_query_state(std::istream& stream) override {
        const auto schedule_count = read_value<std::uint64_t>(stream);
        schedule_.clear();
        schedule_.reserve(static_cast<std::size_t>(schedule_count));
        for (std::uint64_t row = 0; row < schedule_count; ++row) {
            const auto axis = read_value<std::int32_t>(stream);
            if (axis != 0 && axis != 1) throw std::runtime_error("invalid BMTree schedule");
            schedule_.push_back(axis);
        }
        const auto official_count = read_value<std::uint64_t>(stream);
        official_codes_.resize(static_cast<std::size_t>(official_count));
        for (auto& code : official_codes_) code = read_value<std::uint64_t>(stream);
        const auto segment_count = read_value<std::uint64_t>(stream);
        segments_.assign(static_cast<std::size_t>(segment_count), {});
        for (auto& segment : segments_) {
            segment.xmin = read_value<float>(stream);
            segment.ymin = read_value<float>(stream);
            segment.xmax = read_value<float>(stream);
            segment.ymax = read_value<float>(stream);
            const auto position_count = read_value<std::uint64_t>(stream);
            segment.positions.reserve(static_cast<std::size_t>(position_count));
            for (std::uint64_t row = 0; row < position_count; ++row) {
                const auto position = read_value<std::uint64_t>(stream);
                if (position >= points_.size()) throw std::runtime_error("BMTree position out of range");
                segment.positions.push_back(static_cast<std::size_t>(position));
            }
        }
    }

private:
    static constexpr unsigned kBits = 16;
    std::vector<Rect> training_queries_;
    std::filesystem::path model_;
    std::vector<int> schedule_;
    std::vector<std::uint64_t> official_codes_;
    std::vector<Segment> segments_;
};

}  // namespace

std::vector<std::string> formal_baseline_names() {
    return {"flood", "tsunami", "lisa", "rsmi", "lmsfc", "bmtree", "rtree", "zorder"};
}

std::unique_ptr<RangeIndex> make_formal_baseline(
    const std::string& name,
    BaselineBuildContext context) {
    if (name == "flood") return make_learnedbench_flood(context.training_queries);
    if (name == "lisa") return make_learnedbench_lisa();
    if (name == "rsmi") return make_official_rsmi(context.rsmi_model_prefix);
    if (name == "tsunami") return std::make_unique<TsunamiIndex>(std::move(context.training_queries));
    if (name == "lmsfc") return std::make_unique<LMSFCIndex>(std::move(context.training_queries));
    if (name == "bmtree") return std::make_unique<BMTreeOfficialIndex>(std::move(context.training_queries), std::move(context.bmtree_model));
    if (name == "rtree") return std::make_unique<BoostRStarIndex>(std::move(context.validation_queries));
    if (name == "zorder") return std::make_unique<ZOrderBigMinIndex>();
    throw std::invalid_argument("unknown formal baseline: " + name);
}

}  // namespace qmapli
