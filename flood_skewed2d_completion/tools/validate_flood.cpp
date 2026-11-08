#include "qmapli/formal_baselines.hpp"
#include "qmapli/geometry.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <random>
#include <sstream>
#include <stdexcept>
#include <vector>

using qmapli::Point;
using qmapli::Rect;

std::vector<Point> read_points(const std::filesystem::path& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("Missing validation sample");
    std::string line;
    std::getline(in, line);
    std::vector<Point> points;
    while (std::getline(in, line)) {
        std::stringstream stream(line);
        std::string id, x, y;
        std::getline(stream, id, ','); std::getline(stream, x, ','); std::getline(stream, y, ',');
        points.push_back({std::stof(x), std::stof(y), std::uint32_t(std::stoul(id))});
    }
    return points;
}

std::uint64_t hash_ids(const std::vector<std::uint32_t>& ids) {
    std::uint64_t hash = 14695981039346656037ULL;
    for (auto id : ids) for (int shift = 0; shift < 32; shift += 8) {
        hash ^= (id >> shift) & 255; hash *= 1099511628211ULL;
    }
    return hash;
}

int main(int argc, char** argv) {
    try {
        if (argc != 4) throw std::runtime_error("sample.csv output.csv archive-prefix required");
        auto points = read_points(argv[1]);
        std::uint32_t next_id = 0;
        for (auto p : points) next_id = std::max(next_id, p.id + 1);
        // Additional adversarial engineering fixtures, never formal inputs.
        for (int i = 0; i < 256; ++i) points.push_back({0.75f, 0.125f, next_id++});
        for (auto xy : std::vector<std::array<float, 2>>{{0,0},{1,1},{0,1},{1,0},{-0.0f,0.0f},
                   {0.125f,0.75f},{0.125f,0.75f},{std::numeric_limits<float>::min(),0.5f},
                   {std::nextafter(1.f,0.f),std::nextafter(0.f,1.f)}})
            points.push_back({xy[0], xy[1], next_id++});
        std::vector<Rect> queries;
        std::mt19937_64 random(20261009);
        std::uniform_real_distribution<double> coord(-0.05,1.05);
        for (int i = 0; i < 1000; ++i) {
            double x0=coord(random),x1=coord(random),y0=coord(random),y1=coord(random);
            queries.push_back({std::min(x0,x1),std::min(y0,y1),std::max(x0,x1),std::max(y0,y1)});
        }
        for (Rect q : std::vector<Rect>{{-2,-2,-1,-1},{0,0,1,1},{0,0,0,0},{1,1,1,1},
                  {0.75,0.125,0.75,0.125},{0.74,0.12,0.76,0.13},{0.125,0.75,0.125,0.75},
                  {0,0,1,0.5},{0,0.5,1,1},{0.5,0,0.5,1}}) queries.push_back(q);
        for (std::size_t i=0; i<std::min<std::size_t>(64,points.size()); ++i) {
            auto p=points[i];
            queries.push_back({p.x,p.y,p.x,p.y});
            queries.push_back({std::nextafter(double(p.x),-std::numeric_limits<double>::infinity()),
                               std::nextafter(double(p.y),-std::numeric_limits<double>::infinity()),p.x,p.y});
            queries.push_back({std::nextafter(double(p.x),std::numeric_limits<double>::infinity()),
                               std::nextafter(double(p.y),std::numeric_limits<double>::infinity()),p.x+0.001,p.y+0.001});
        }
        std::ofstream out(argv[2]);
        out << "orientation,lifecycle,query_id,truth_count,candidate_count,ids_hash,missing,extra,exact\n";
        for (bool swapped : {false,true}) {
            std::vector<Rect> training{swapped?Rect{0,0,0.01,0.9}:Rect{0,0,0.9,0.01}};
            auto index=qmapli::make_learnedbench_flood(training);
            index->build(points);
            auto archive=std::string(argv[3])+(swapped?"-swapped.idx":"-normal.idx");
            index->save(archive);
            for (int lifecycle=0; lifecycle<2; ++lifecycle) {
                if (lifecycle) {index.reset();index=qmapli::make_learnedbench_flood(training);index->load(archive);}
                for (std::size_t i=0; i<queries.size(); ++i) {
                    std::vector<std::uint32_t> truth;
                    for (auto p : points) if (qmapli::contains(queries[i],p)) truth.push_back(p.id);
                    std::sort(truth.begin(),truth.end());
                    truth.erase(std::unique(truth.begin(),truth.end()),truth.end());
                    auto result=index->range_query(queries[i]);
                    if (result.ids!=truth || result.candidates!=truth.size())
                        throw std::runtime_error("Validation mismatch: query "+std::to_string(i));
                    out << swapped << ',' << lifecycle << ',' << i << ',' << truth.size() << ','
                        << result.candidates << ',' << hash_ids(result.ids) << ",0,0,1\n";
                }
            }
        }
        std::cout << "VALIDATED_RANDOM_QUERIES=1000 PER_ORIENTATION; TOTAL_CHECKS=" << queries.size()*4
                  << "; POINTS=" << points.size() << "; RB_TREE_NODE_BYTES="
                  << sizeof(std::_Rb_tree_node<std::pair<const std::array<double,2>,std::vector<std::uint32_t>>>)
                  << "; Point_BYTES=" << sizeof(Point) << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
