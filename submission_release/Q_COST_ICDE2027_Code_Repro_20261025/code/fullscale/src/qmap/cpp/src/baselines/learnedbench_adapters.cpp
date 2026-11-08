#include "qmapli/formal_baselines.hpp"

#include <algorithm>
#include <cstdint>
#include <fstream>
#include <map>
#include <memory>
#include <stdexcept>
#include <utility>
#include <vector>

#include "indexes/learned/flood.hpp"
#include "indexes/learned/lisa2.hpp"
#include "flood_ownership.hpp"
#include "flood_compact_lookup.hpp"

namespace qmapli {
namespace {

using LBPoint = point_t<2>;
using LBPoints = std::vector<LBPoint>;
using LBBox = box_t<2>;

template <bool Swap>
LBPoint to_learnedbench(const Point& point) {
    if constexpr (Swap) return {point.y, point.x};
    return {point.x, point.y};
}

template <bool Swap>
LBBox to_learnedbench(const Rect& query) {
    if constexpr (Swap) {
        return LBBox(LBPoint{query.ymin, query.xmin}, LBPoint{query.ymax, query.xmax});
    }
    return LBBox(LBPoint{query.xmin, query.ymin}, LBPoint{query.xmax, query.ymax});
}

template <bool Swap>
class FloodImpl {
public:
    void build(const std::vector<Point>& points) {
        construct(points.size(),[&](std::size_t i){return points[i];});
    }
    void load(flood_memory::MappedPoints& points) {
        compact_=true;
        count_=points.size();coordinates_.reserve(count_);
        for(std::size_t i=0;i<count_;++i)coordinates_.push_back(to_learnedbench<Swap>(points.at(i)));
        observe("after_coordinates_creation",count_*sizeof(Point));
        compact_ids_.build(count_,[&](std::size_t i){return points.at(i);});
        lookup_bytes_=compact_ids_.bytes();id_capacity_=compact_ids_.id_bytes();
        observe("after_coordinate_ID_map_creation",count_*sizeof(Point));
        observe("after_compact_lookup_finalization",count_*sizeof(Point));
        points.release_pages();observe("after_points_release_before_model");
        // The exact original-order double vector enters the same frozen model.
        index_=std::make_unique<bench::index::Flood<2,32,64,1>>(coordinates_);
        cached_index_bytes_=index_->index_size();
        observe("after_Flood_model_construction");
    }
    template<class Get> void construct(std::size_t count,Get get) {
        count_=count;
        coordinates_.clear();
        ids_.clear();
        coordinates_.reserve(count);
        for (std::size_t ordinal=0;ordinal<count;++ordinal) {
            const auto point=get(ordinal);
            const auto converted = to_learnedbench<Swap>(point);
            coordinates_.push_back(converted);
            ids_[converted].push_back(point.id);
        }
        id_capacity_=0;
        for(const auto& entry:ids_)id_capacity_+=entry.second.capacity()*sizeof(std::uint32_t);
        lookup_bytes_=ids_.size()*sizeof(std::_Rb_tree_node<std::pair<const LBPoint,std::vector<std::uint32_t>>>)+id_capacity_;
        observe("after_coordinates_creation",count*sizeof(Point));
        observe("after_coordinate_ID_map_creation",count*sizeof(Point));
        index_ = std::make_unique<bench::index::Flood<2, 32, 64, 1>>(coordinates_);
        cached_index_bytes_=index_->index_size();
        observe("after_Flood_model_construction",count*sizeof(Point));
    }

    void release_coordinates(){LBPoints().swap(coordinates_);observe("after_coordinates_release");}
    void observe(const char* phase,std::size_t points=0,std::size_t matches=0,std::size_t results=0)const {
        flood_memory::trace(phase,count_,points,coordinates_.capacity()*sizeof(LBPoint),
            cached_index_bytes_?count_*sizeof(LBPoint)+cached_index_bytes_-count_*sizeof(std::size_t):0,
            lookup_bytes_,compact_?compact_ids_.distinct():ids_.size(),id_capacity_,matches,results);
    }

    QueryResult query(const Rect& query) {
        auto box = to_learnedbench<Swap>(query);
        auto matches = index_->range_query(box);
        observe("query_matches",0,matches.capacity()*sizeof(LBPoint));
        // The final API returns unique IDs. A coordinate occurring d times in
        // Flood must expand its d IDs once, not d times (d*d temporary IDs).
        // Keep the learned index and its returned point multiset unchanged;
        // deduplicate only this adapter-owned result buffer before expansion.
        std::sort(matches.begin(), matches.end());
        matches.erase(std::unique(matches.begin(), matches.end()), matches.end());
        QueryResult result;
        result.candidates = matches.size();
        for (const auto& match : matches) {
            if(compact_){compact_ids_.append(match,result.ids);continue;}
            const auto found = ids_.find(match);
            if (found != ids_.end()) {
                result.ids.insert(result.ids.end(), found->second.begin(), found->second.end());
            }
        }
        std::sort(result.ids.begin(), result.ids.end());
        result.ids.erase(std::unique(result.ids.begin(), result.ids.end()), result.ids.end());
        result.candidates = result.ids.size();
        observe("query_result_IDs",0,matches.capacity()*sizeof(LBPoint),result.ids.capacity()*sizeof(std::uint32_t));
        flood_memory::match_digest(matches,Swap,result.candidates);
        return result;
    }

    std::size_t index_size() const { return cached_index_bytes_; }

private:
    LBPoints coordinates_;
    std::map<LBPoint, std::vector<std::uint32_t>> ids_;
    std::unique_ptr<bench::index::Flood<2, 32, 64, 1>> index_;
    std::size_t count_=0,cached_index_bytes_=0,lookup_bytes_=0,id_capacity_=0;
    bool compact_=false;
    FloodCompactLookup<Swap> compact_ids_;
};

class FloodAdapter final : public RangeIndex {
public:
    explicit FloodAdapter(std::vector<Rect> training_queries)
        : training_queries_(std::move(training_queries)) {}

    std::string method_name() const override { return "Flood-learnedbench"; }

    void build(const std::vector<Point>& points) override {
        mapped_.reset();
        points_ = points;
        choose_orientation();
        rebuild();
    }

    void save(const std::filesystem::path& path) const override {
        if(mapped_.active()){mapped_.save(path);return;}
        std::ofstream output(path, std::ios::binary | std::ios::trunc);
        const std::uint64_t count = points_.size();
        output.write(reinterpret_cast<const char*>(&count), sizeof(count));
        output.write(reinterpret_cast<const char*>(&swap_), sizeof(swap_));
        output.write(reinterpret_cast<const char*>(points_.data()), points_.size() * sizeof(Point));
    }

    void load(const std::filesystem::path& path) override {
        flood_memory::trace("before_deserialize",0,0,0,0,0);
        std::vector<Point>().swap(points_);
        mapped_.open(path,swap_);
        flood_memory::trace("after_points_deserialize_mapping",mapped_.size(),0,0,0,0);
        load_instrumentation_ = {1, 1, 1, 0, 1, false};
        normal_.reset();swapped_.reset();
        if(swap_){swapped_=std::make_unique<FloodImpl<true>>();swapped_->load(mapped_);swapped_->release_coordinates();}
        else {normal_=std::make_unique<FloodImpl<false>>();normal_->load(mapped_);normal_->release_coordinates();}
        mapped_.release_pages();
        if(swap_)swapped_->observe("after_points_release");else normal_->observe("after_points_release");
    }

    QueryResult range_query(const Rect& query) const override {
        return swap_ ? swapped_->query(query) : normal_->query(query);
    }

    std::size_t serialized_size_bytes() const override {
        const auto learned = swap_ ? swapped_->index_size() : normal_->index_size();
        return sizeof(std::uint64_t) + sizeof(bool) + (mapped_.active()?mapped_.size():points_.size()) * sizeof(Point) + learned;
    }

    PersistenceInstrumentation persistence_instrumentation() const override {
        return load_instrumentation_;
    }

private:
    void choose_orientation() {
        if (training_queries_.empty()) {
            swap_ = false;
            return;
        }
        double x_width = 0, y_width = 0;
        for (const auto& query : training_queries_) {
            x_width += query.xmax - query.xmin;
            y_width += query.ymax - query.ymin;
        }
        // The learnedbench template sorts its second coordinate. Swap when x
        // is the more selective sort dimension.
        swap_ = x_width < y_width;
    }

    void rebuild() {
        normal_.reset();
        swapped_.reset();
        if (swap_) {
            swapped_ = std::make_unique<FloodImpl<true>>();
            swapped_->build(points_);
        } else {
            normal_ = std::make_unique<FloodImpl<false>>();
            normal_->build(points_);
        }
    }

    std::vector<Rect> training_queries_;
    std::vector<Point> points_;
    flood_memory::MappedPoints mapped_;
    bool swap_ = false;
    mutable std::unique_ptr<FloodImpl<false>> normal_;
    mutable std::unique_ptr<FloodImpl<true>> swapped_;
    PersistenceInstrumentation load_instrumentation_{};
};

class LisaAdapter final : public RangeIndex {
public:
    std::string method_name() const override { return "LISA-learnedbench"; }

    void build(const std::vector<Point>& points) override {
        points_ = points;
        rebuild();
    }

    void save(const std::filesystem::path& path) const override {
        std::ofstream output(path, std::ios::binary | std::ios::trunc);
        const std::uint64_t count = points_.size();
        output.write(reinterpret_cast<const char*>(&count), sizeof(count));
        output.write(reinterpret_cast<const char*>(points_.data()), points_.size() * sizeof(Point));
    }

    void load(const std::filesystem::path& path) override {
        std::ifstream input(path, std::ios::binary);
        std::uint64_t count = 0;
        input.read(reinterpret_cast<char*>(&count), sizeof(count));
        points_.resize(count);
        input.read(reinterpret_cast<char*>(points_.data()), points_.size() * sizeof(Point));
        load_instrumentation_ = {1, 1, 1, 0, 1, false};
        rebuild();
    }

    QueryResult range_query(const Rect& query) const override {
        auto box = to_learnedbench<false>(query);
        const auto matches = index_->range_query(box);
        QueryResult result;
        result.candidates = matches.size();
        for (const auto& match : matches) {
            const auto found = ids_.find(match);
            if (found != ids_.end()) result.ids.insert(result.ids.end(), found->second.begin(), found->second.end());
        }
        std::sort(result.ids.begin(), result.ids.end());
        result.ids.erase(std::unique(result.ids.begin(), result.ids.end()), result.ids.end());
        result.candidates = result.ids.size();
        return result;
    }

    std::size_t serialized_size_bytes() const override {
        return sizeof(std::uint64_t) + points_.size() * sizeof(Point) + (index_ ? index_->index_size() : 0);
    }

    PersistenceInstrumentation persistence_instrumentation() const override {
        return load_instrumentation_;
    }

private:
    void rebuild() {
        coordinates_.clear();
        ids_.clear();
        for (const auto& point : points_) {
            const auto converted = to_learnedbench<false>(point);
            ids_[converted].push_back(point.id);
        }
        coordinates_.reserve(ids_.size());
        for (const auto& [coordinate, _ids] : ids_) coordinates_.push_back(coordinate);
        index_ = std::make_unique<bench::index::LISA2<2, 32, 64>>(coordinates_);
    }

    std::vector<Point> points_;
    LBPoints coordinates_;
    std::map<LBPoint, std::vector<std::uint32_t>> ids_;
    mutable std::unique_ptr<bench::index::LISA2<2, 32, 64>> index_;
    PersistenceInstrumentation load_instrumentation_{};
};

}  // namespace

std::unique_ptr<RangeIndex> make_learnedbench_flood(const std::vector<Rect>& training_queries) {
    return std::make_unique<FloodAdapter>(training_queries);
}

std::unique_ptr<RangeIndex> make_learnedbench_lisa() {
    return std::make_unique<LisaAdapter>();
}

}  // namespace qmapli
