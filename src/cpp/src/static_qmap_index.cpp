#include "qmapli/static_qmap_index.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>
#if defined(__x86_64__) || defined(__i386__)
#include <immintrin.h>
#endif

namespace qmapli {
namespace {

constexpr std::array<char, 8> kMagic{'Q', 'M', 'A', 'P', 'N', 'A', 'I', '1'};

template <typename T>
T read_value(std::istream& stream) {
    T value{};
    stream.read(reinterpret_cast<char*>(&value), sizeof(value));
    if (!stream) throw std::runtime_error("truncated QMap-NAI static index");
    return value;
}

template <typename T>
std::vector<T> read_vector(std::istream& stream, std::size_t count) {
    std::vector<T> values(count);
    stream.read(reinterpret_cast<char*>(values.data()), static_cast<std::streamsize>(count * sizeof(T)));
    if (!stream) throw std::runtime_error("truncated QMap-NAI static array");
    return values;
}

struct Node {
    Rect mbr{};
    std::uint32_t storage_start = 0;
    std::uint32_t storage_end = 0;
    std::int32_t left = -1;
    std::int32_t right = -1;
    std::int32_t leaf = -1;
    std::uint8_t strategy = 255;
};

struct Segment {
    std::uint32_t start = 0;
    std::uint32_t end = 0;
    Rect mbr{};
};

struct Suffix {
    std::vector<float> x_values;
    std::vector<std::uint32_t> x_positions;
    std::vector<float> y_values;
    std::vector<std::uint32_t> y_positions;
    std::vector<std::uint32_t> segment_positions;
    std::vector<Segment> segments;
};

bool intersects(const Rect& left, const Rect& right) {
    return !(left.xmax < right.xmin || left.xmin > right.xmax
             || left.ymax < right.ymin || left.ymin > right.ymax);
}

bool covers(const Rect& query, const Rect& box) {
    return query.xmin <= box.xmin && query.ymin <= box.ymin
        && query.xmax >= box.xmax && query.ymax >= box.ymax;
}

class TraversalStack {
public:
    void push(std::int32_t value) {
        if (size_ < local_.size()) local_[size_++] = value;
        else overflow_.push_back(value);
    }
    bool empty() const { return size_ == 0 && overflow_.empty(); }
    std::int32_t pop() {
        if (!overflow_.empty()) {
            const auto result = overflow_.back();
            overflow_.pop_back();
            return result;
        }
        return local_[--size_];
    }
private:
    std::array<std::int32_t,64> local_{};
    std::size_t size_ = 0;
    std::vector<std::int32_t> overflow_;
};

#if defined(__x86_64__) || defined(__i386__)
__attribute__((target("avx2"))) unsigned exact_mask4(
    const float* xs, const float* ys, const std::uint32_t* positions, const Rect& query) {
    const auto offsets = _mm_loadu_si128(reinterpret_cast<const __m128i*>(positions));
    // Promote stored floats exactly. Rounding query bounds to float is forbidden.
    const auto x = _mm256_cvtps_pd(_mm_i32gather_ps(xs,offsets,4));
    const auto y = _mm256_cvtps_pd(_mm_i32gather_ps(ys,offsets,4));
    const auto inside_x = _mm256_and_pd(_mm256_cmp_pd(x,_mm256_set1_pd(query.xmin),_CMP_GE_OQ),
                                      _mm256_cmp_pd(x,_mm256_set1_pd(query.xmax),_CMP_LE_OQ));
    const auto inside_y = _mm256_and_pd(_mm256_cmp_pd(y,_mm256_set1_pd(query.ymin),_CMP_GE_OQ),
                                      _mm256_cmp_pd(y,_mm256_set1_pd(query.ymax),_CMP_LE_OQ));
    return static_cast<unsigned>(_mm256_movemask_pd(_mm256_and_pd(inside_x,inside_y)));
}
#endif

class StaticQMapIndex final : public RangeIndex {
public:
    explicit StaticQMapIndex(std::string method) : method_(std::move(method)) {}

    std::string method_name() const override { return method_; }

    void build(const std::vector<Point>&) override {
        throw std::logic_error("StaticQMapIndex must be materialized by the Python build pipeline");
    }

    void save(const std::filesystem::path& path) const override {
        if (source_path_.empty()) throw std::logic_error("cannot save an unloaded QMap index");
        if (std::filesystem::absolute(source_path_) == std::filesystem::absolute(path)) return;
        std::filesystem::copy_file(source_path_, path, std::filesystem::copy_options::overwrite_existing);
    }

    void load(const std::filesystem::path& path) override {
        std::ifstream stream(path, std::ios::binary);
        if (!stream) throw std::runtime_error("cannot open QMap-NAI index: " + path.string());
        std::array<char, 8> magic{};
        stream.read(magic.data(), static_cast<std::streamsize>(magic.size()));
        if (magic != kMagic) throw std::runtime_error("invalid QMap-NAI static index magic");
        const auto version = read_value<std::uint32_t>(stream);
        const auto variant = read_value<std::uint32_t>(stream);
        if ((version != 1U && version != 2U) || variant > 2U) throw std::runtime_error("unsupported QMap-NAI index version");
        const auto point_count = read_value<std::uint64_t>(stream);
        const auto node_count = read_value<std::uint64_t>(stream);
        const auto leaf_count = read_value<std::uint64_t>(stream);
        if (point_count > std::numeric_limits<std::uint32_t>::max()
            || node_count > std::numeric_limits<std::int32_t>::max()
            || leaf_count > node_count)
            throw std::runtime_error("static index element offsets exceed the supported range");
        const auto minimum_bytes = 40ULL + 12ULL * point_count + 40ULL * node_count + 12ULL * leaf_count;
        if (minimum_bytes > std::filesystem::file_size(path))
            throw std::runtime_error("static index header exceeds available file bytes");
        if (version == 2U) {
            point_x_ = read_vector<float>(stream, point_count);
            point_y_ = read_vector<float>(stream, point_count);
            point_ids_ = read_vector<std::uint32_t>(stream, point_count);
        } else {
            point_x_.resize(point_count);
            point_y_.resize(point_count);
            point_ids_.resize(point_count);
            for (std::size_t i = 0; i < point_count; ++i) {
                point_x_[i] = read_value<float>(stream);
                point_y_[i] = read_value<float>(stream);
                point_ids_[i] = read_value<std::uint32_t>(stream);
            }
        }
        nodes_.resize(static_cast<std::size_t>(node_count));
        for (auto& node : nodes_) {
            node.mbr.xmin = read_value<float>(stream);
            node.mbr.ymin = read_value<float>(stream);
            node.mbr.xmax = read_value<float>(stream);
            node.mbr.ymax = read_value<float>(stream);
            node.storage_start = read_value<std::uint32_t>(stream);
            node.storage_end = read_value<std::uint32_t>(stream);
            node.left = read_value<std::int32_t>(stream);
            node.right = read_value<std::int32_t>(stream);
            node.leaf = read_value<std::int32_t>(stream);
            node.strategy = read_value<std::uint8_t>(stream);
            std::array<char, 3> padding{};
            stream.read(padding.data(), 3);
        }
        suffixes_.resize(static_cast<std::size_t>(leaf_count));
        for (auto& suffix : suffixes_) {
            const auto count = read_value<std::uint32_t>(stream);
            if (version == 1U) suffix.x_values = read_vector<float>(stream, count);
            suffix.x_positions = read_vector<std::uint32_t>(stream, count);
            if (version == 1U) suffix.y_values = read_vector<float>(stream, count);
            suffix.y_positions = read_vector<std::uint32_t>(stream, count);
            const auto position_count = read_value<std::uint32_t>(stream);
            suffix.segment_positions = read_vector<std::uint32_t>(stream, position_count);
            const auto segment_count = read_value<std::uint32_t>(stream);
            suffix.segments.resize(segment_count);
            for (auto& segment : suffix.segments) {
                segment.start = read_value<std::uint32_t>(stream);
                segment.end = read_value<std::uint32_t>(stream);
                segment.mbr.xmin = read_value<float>(stream);
                segment.mbr.ymin = read_value<float>(stream);
                segment.mbr.xmax = read_value<float>(stream);
                segment.mbr.ymax = read_value<float>(stream);
            }
        }
        if (nodes_.empty()) throw std::runtime_error("QMap-NAI static index contains no root node");
        for (const auto& node : nodes_) {
            if (node.storage_start > node.storage_end || node.storage_end > point_ids_.size()
                || (node.leaf >= 0 && static_cast<std::size_t>(node.leaf) >= suffixes_.size()))
                throw std::runtime_error("invalid static point or leaf range");
        }
        for (const auto& suffix : suffixes_) {
            for (const auto* positions : {&suffix.x_positions,&suffix.y_positions,&suffix.segment_positions}) {
                for (const auto position : *positions)
                    if (position >= point_ids_.size()) throw std::runtime_error("invalid suffix point offset");
            }
        }
#if defined(__x86_64__) || defined(__i386__)
        // Indirect gathers lost to scalar in the registered paired system audit.
        // Keep the exact AVX2 implementation opt-in for other hardware/workloads.
        simd_ = __builtin_cpu_supports("avx2") && std::getenv("QMAP_QMF_SIMD")
            && !std::getenv("QMAP_QMF_SCALAR")
            && point_ids_.size() <= static_cast<std::size_t>(std::numeric_limits<std::int32_t>::max());
#endif
        depths_.assign(nodes_.size(), 0);
        std::vector<std::int32_t> pending{0};
        depths_[0] = 1;
        while (!pending.empty()) {
            const auto parent = pending.back();
            pending.pop_back();
            for (const auto child : {nodes_.at(parent).left, nodes_.at(parent).right}) {
                if (child < 0) continue;
                if (static_cast<std::size_t>(child) >= nodes_.size() || depths_[child])
                    throw std::runtime_error("invalid or cyclic QMap child offset");
                depths_[child] = depths_[parent] + 1;
                pending.push_back(child);
            }
        }
        source_path_ = path;
        serialized_size_ = std::filesystem::file_size(path);
    }

    QueryResult range_query(const Rect& query) const override {
        return query_impl<true>(query);
    }

    CountResult range_count(const Rect& query) const override {
        const auto result = query_impl<false>(query);
        return {result.matched_count,result.candidates};
    }

    template <bool CollectIds>
    QueryResult query_impl(const Rect& query) const {
        using Clock=std::chrono::steady_clock;
        Clock::time_point started{};
        if constexpr (CollectIds) started=Clock::now();
        QueryResult result;
        TraversalStack stack;
        stack.push(0);
        while (!stack.empty()) {
            const auto number = stack.pop();
            const auto& node = nodes_.at(static_cast<std::size_t>(number));
            if (!intersects(node.mbr, query)) continue;
            result.max_depth_encountered=std::max(result.max_depth_encountered,static_cast<std::size_t>(depths_[number]));
            if (covers(query, node.mbr)) {
                const auto count=static_cast<std::size_t>(node.storage_end-node.storage_start);
                result.matched_count+=count;
                result.candidates+=count;
                if constexpr (CollectIds)
                    for (auto p=node.storage_start;p<node.storage_end;++p) result.ids.push_back(point_ids_[p]);
                continue;
            }
            if (node.leaf >= 0) {
                ++result.visited_leaves;
                Clock::time_point leaf_start{};
                if constexpr (CollectIds) leaf_start=Clock::now();
                const auto& suffix=suffixes_.at(static_cast<std::size_t>(node.leaf));
                if (node.strategy <= 3U) {
                    const auto x=axis_bounds(suffix.x_values,suffix.x_positions,point_x_,query.xmin,query.xmax);
                    const auto y=axis_bounds(suffix.y_values,suffix.y_positions,point_y_,query.ymin,query.ymax);
                    const bool use_x=node.strategy==0U || (node.strategy!=1U && x.second-x.first<=y.second-y.first);
                    const auto range=use_x?x:y;
                    const auto& positions=use_x?suffix.x_positions:suffix.y_positions;
                    if constexpr (CollectIds)
                        result.leaf_access_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-leaf_start).count();
                    Clock::time_point refine_start{};
                    if constexpr (CollectIds) refine_start=Clock::now();
                    const auto before=result.matched_count;
                    refine_slice<CollectIds>(positions,range,query,result);
                    result.candidates+=node.strategy==3U?result.matched_count-before:range.second-range.first;
                    if constexpr (CollectIds)
                        result.refinement_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-refine_start).count();
                } else {
                    std::vector<std::uint32_t> positions;
                    append_suffix(node,suffix,query,positions);
                    result.candidates+=positions.size();
                    refine_slice<CollectIds>(positions,{0,positions.size()},query,result);
                    if constexpr (CollectIds)
                        result.leaf_access_ns+=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-leaf_start).count();
                }
            } else {
                ++result.visited_internal_nodes;
                const bool left_hit = node.left >= 0
                    && intersects(nodes_.at(static_cast<std::size_t>(node.left)).mbr, query);
                const bool right_hit = node.right >= 0
                    && intersects(nodes_.at(static_cast<std::size_t>(node.right)).mbr, query);
                result.cross_partitions += static_cast<std::size_t>(left_hit && right_hit);
                if (right_hit) stack.push(node.right);
                if (left_hit) stack.push(node.left);
            }
        }
        if constexpr (CollectIds) {
            result.traversal_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-started).count()
                -result.leaf_access_ns-result.refinement_ns;
            const auto sort_start=Clock::now();
            std::sort(result.ids.begin(),result.ids.end());
            result.result_count_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-sort_start).count();
        }
        return result;
    }

    std::size_t serialized_size_bytes() const override { return serialized_size_; }

    PersistenceInstrumentation persistence_instrumentation() const override {
        PersistenceInstrumentation result;
        result.query_ready = true;
        return result;
    }

private:
    template <bool CollectIds>
    void refine_slice(const std::vector<std::uint32_t>& positions,
                      std::pair<std::size_t,std::size_t> range, const Rect& query, QueryResult& result) const {
        auto current=range.first;
#if defined(__x86_64__) || defined(__i386__)
        if (simd_) {
            for (;current+4<=range.second;current+=4) {
                auto mask=exact_mask4(point_x_.data(),point_y_.data(),positions.data()+current,query);
                result.matched_count+=static_cast<unsigned>(__builtin_popcount(mask));
                if constexpr (CollectIds) {
                    while (mask) {
                        const auto offset=static_cast<unsigned>(__builtin_ctz(mask));
                        result.ids.push_back(point_ids_[positions[current+offset]]);
                        mask&=mask-1;
                    }
                }
            }
        }
#endif
        for (;current<range.second;++current) {
            const auto p=positions[current];
            if (query.xmin <= point_x_[p] && point_x_[p] <= query.xmax
                && query.ymin <= point_y_[p] && point_y_[p] <= query.ymax) {
                ++result.matched_count;
                if constexpr (CollectIds) result.ids.push_back(point_ids_[p]);
            }
        }
    }
    static std::pair<std::size_t, std::size_t> bounds(
        const std::vector<float>& values, double low, double high) {
        return {
            static_cast<std::size_t>(std::lower_bound(values.begin(), values.end(), low) - values.begin()),
            static_cast<std::size_t>(std::upper_bound(values.begin(), values.end(), high) - values.begin())};
    }

    static std::pair<std::size_t, std::size_t> axis_bounds(
        const std::vector<float>& values, const std::vector<std::uint32_t>& positions,
        const std::vector<float>& coordinates, double low, double high) {
        if (!values.empty()) return bounds(values, low, high);
        const auto first = std::lower_bound(positions.begin(), positions.end(), low,
            [&](std::uint32_t p, double bound) { return coordinates[p] < bound; });
        const auto last = std::upper_bound(positions.begin(), positions.end(), high,
            [&](double bound, std::uint32_t p) { return bound < coordinates[p]; });
        return {static_cast<std::size_t>(first - positions.begin()),
                static_cast<std::size_t>(last - positions.begin())};
    }

    static void append_slice(
        const std::vector<std::uint32_t>& source,
        std::pair<std::size_t, std::size_t> range,
        std::vector<std::uint32_t>& output) {
        output.insert(output.end(), source.begin() + static_cast<std::ptrdiff_t>(range.first),
                      source.begin() + static_cast<std::ptrdiff_t>(range.second));
    }

    static void append_intersection(
        const std::vector<std::uint32_t>& first,
        std::pair<std::size_t, std::size_t> first_range,
        const std::vector<std::uint32_t>& second,
        std::pair<std::size_t, std::size_t> second_range,
        std::vector<std::uint32_t>& output) {
        std::vector<std::uint32_t> left(first.begin() + first_range.first, first.begin() + first_range.second);
        std::vector<std::uint32_t> right(second.begin() + second_range.first, second.begin() + second_range.second);
        std::sort(left.begin(), left.end());
        std::sort(right.begin(), right.end());
        std::set_intersection(left.begin(), left.end(), right.begin(), right.end(), std::back_inserter(output));
    }

    void append_suffix(
        const Node& node, const Suffix& suffix, const Rect& query,
        std::vector<std::uint32_t>& output) const {
        const auto x = axis_bounds(suffix.x_values, suffix.x_positions, point_x_, query.xmin, query.xmax);
        const auto y = axis_bounds(suffix.y_values, suffix.y_positions, point_y_, query.ymin, query.ymax);
        if (node.strategy == 0U) return append_slice(suffix.x_positions, x, output);
        if (node.strategy == 1U) return append_slice(suffix.y_positions, y, output);
        if (node.strategy == 2U) {
            return (x.second - x.first <= y.second - y.first)
                ? append_slice(suffix.x_positions, x, output)
                : append_slice(suffix.y_positions, y, output);
        }
        if (node.strategy == 3U) {
            return append_intersection(suffix.x_positions, x, suffix.y_positions, y, output);
        }
        for (const auto& segment : suffix.segments) {
            if (!intersects(segment.mbr, query)) continue;
            output.insert(
                output.end(), suffix.segment_positions.begin() + segment.start,
                suffix.segment_positions.begin() + segment.end);
        }
    }

    std::string method_;
    std::filesystem::path source_path_;
    std::size_t serialized_size_ = 0;
    std::vector<std::uint32_t> point_ids_;
    std::vector<float> point_x_,point_y_;
    bool simd_=false;
    std::vector<Node> nodes_;
    std::vector<std::uint32_t> depths_;
    std::vector<Suffix> suffixes_;
};

}  // namespace

std::unique_ptr<RangeIndex> make_static_qmap_index(const std::string& method) {
    if (method != "qmap_uniform_qmf" && method != "qmap_qw")
        throw std::invalid_argument("only QMF index methods are supported");
    return std::make_unique<StaticQMapIndex>(method);
}

}  // namespace qmapli
