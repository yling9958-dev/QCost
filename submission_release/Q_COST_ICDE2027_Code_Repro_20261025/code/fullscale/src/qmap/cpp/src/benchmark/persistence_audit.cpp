#include "qmapli/formal_baselines.hpp"
#include "qmapli/static_qmap_index.hpp"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;

std::vector<std::string> split(const std::string& line) {
    std::vector<std::string> fields;
    std::stringstream stream(line);
    std::string field;
    while (std::getline(stream, field, ',')) fields.push_back(field);
    return fields;
}

std::unordered_map<std::string, std::string> parse_args(int argc, char** argv) {
    std::unordered_map<std::string, std::string> values;
    for (int index = 1; index + 1 < argc; index += 2) values[argv[index]] = argv[index + 1];
    return values;
}

std::vector<qmapli::Point> load_points(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open points: " + path.string());
    std::string line;
    std::getline(input, line);
    std::vector<qmapli::Point> points;
    while (std::getline(input, line)) {
        const auto fields = split(line);
        if (fields.size() < 3) continue;
        points.push_back({std::stof(fields[1]), std::stof(fields[2]),
                          static_cast<std::uint32_t>(std::stoul(fields[0]))});
    }
    return points;
}

std::vector<qmapli::Rect> load_queries(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open queries: " + path.string());
    std::string line;
    std::getline(input, line);
    std::vector<qmapli::Rect> queries;
    while (std::getline(input, line)) {
        const auto fields = split(line);
        if (fields.size() < 7) continue;
        queries.push_back({std::stod(fields[3]), std::stod(fields[4]),
                           std::stod(fields[5]), std::stod(fields[6])});
    }
    return queries;
}

std::vector<std::vector<std::uint32_t>> query_all(
    const qmapli::RangeIndex& index, const std::vector<qmapli::Rect>& queries) {
    std::vector<std::vector<std::uint32_t>> results;
    results.reserve(queries.size());
    for (const auto& query : queries) results.push_back(index.range_query(query).ids);
    return results;
}

std::uint64_t elapsed_ns(Clock::time_point start) {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count());
}

std::size_t peak_rss_kib() {
    std::ifstream status("/proc/self/status");
    std::string key;
    while (status >> key) {
        if (key == "VmHWM:") {
            std::size_t value = 0;
            std::string unit;
            status >> value >> unit;
            return value;
        }
        std::string rest;
        std::getline(status, rest);
    }
    return 0;
}

bool is_qmap(const std::string& method) { return method.rfind("qmap_", 0) == 0; }

}  // namespace

int main(int argc, char** argv) {
    try {
        const auto args = parse_args(argc, argv);
        const auto method = args.at("--method");
        const auto queries = load_queries(args.at("--queries"));
        const auto serialized = std::filesystem::path(args.at("--serialized"));
        std::filesystem::create_directories(serialized.parent_path());

        std::unique_ptr<qmapli::RangeIndex> built;
        if (is_qmap(method)) {
            built = qmapli::make_static_qmap_index(method);
            built->load(args.at("--source-index"));
        } else {
            qmapli::BaselineBuildContext context;
            context.training_queries = load_queries(args.at("--train-queries"));
            context.validation_queries = load_queries(args.at("--validation-queries"));
            const auto model = args.find("--bmtree-model");
            if (model != args.end()) context.bmtree_model = model->second;
            built = qmapli::make_formal_baseline(method, std::move(context));
            built->build(load_points(args.at("--points")));
        }
        const auto before = query_all(*built, queries);
        const auto save_started = Clock::now();
        built->save(serialized);
        const auto save_ns = elapsed_ns(save_started);
        built.reset();

        std::unique_ptr<qmapli::RangeIndex> loaded;
        if (is_qmap(method)) {
            loaded = qmapli::make_static_qmap_index(method);
        } else {
            loaded = qmapli::make_formal_baseline(method);
        }
        const auto load_started = Clock::now();
        loaded->load(serialized);
        const auto load_ns = elapsed_ns(load_started);
        const auto instrumentation = loaded->persistence_instrumentation();
        const auto after = query_all(*loaded, queries);
        const bool exact = before == after;

        std::ofstream output(args.at("--output"), std::ios::trunc);
        if (!output) throw std::runtime_error("cannot create persistence output");
        output << "method,status,roundtrip_exact,queries,serialized_bytes,save_ns,cold_load_ns,peak_rss_kib,"
                  "sort_count,fit_count,partition_count,tree_build_count,model_generation_count,query_ready\n";
        output << method << ','
               << (instrumentation.query_ready ? "QUERY_READY" : "PERSISTENCE_UNAVAILABLE") << ','
               << (exact ? "true" : "false") << ',' << queries.size() << ',';
        if (instrumentation.query_ready) {
            output << std::filesystem::file_size(serialized) << ',' << save_ns << ',' << load_ns << ',';
        } else {
            output << ",,,";
        }
        output << peak_rss_kib() << ',' << instrumentation.sort_count << ','
               << instrumentation.fit_count << ',' << instrumentation.partition_count << ','
               << instrumentation.tree_build_count << ','
               << instrumentation.model_generation_count << ','
               << (instrumentation.query_ready ? "true" : "false") << '\n';
        return exact ? 0 : 1;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
