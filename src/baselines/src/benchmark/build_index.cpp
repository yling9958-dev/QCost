#include "qmapli/formal_baselines.hpp"

#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <unordered_map>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;

std::unordered_map<std::string, std::string> arguments(int argc, char** argv) {
    std::unordered_map<std::string, std::string> output;
    for (int index = 1; index + 1 < argc; index += 2) output[argv[index]] = argv[index + 1];
    return output;
}

std::vector<std::string> fields(const std::string& line) {
    std::vector<std::string> output;
    std::stringstream stream(line);
    std::string value;
    while (std::getline(stream, value, ',')) output.push_back(value);
    return output;
}

std::vector<qmapli::Point> read_points(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open points: " + path);
    std::string line;
    std::getline(input, line);
    std::vector<qmapli::Point> output;
    while (std::getline(input, line)) {
        const auto row = fields(line);
        if (row.size() >= 3) output.push_back({
            std::stof(row[1]), std::stof(row[2]), static_cast<std::uint32_t>(std::stoul(row[0]))});
    }
    return output;
}

std::vector<qmapli::Rect> read_queries(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open queries: " + path);
    std::string line;
    std::getline(input, line);
    std::vector<qmapli::Rect> output;
    while (std::getline(input, line)) {
        const auto row = fields(line);
        if (row.size() >= 7) output.push_back({
            std::stod(row[3]), std::stod(row[4]), std::stod(row[5]), std::stod(row[6])});
    }
    return output;
}

std::uint64_t elapsed_ns(Clock::time_point started) {
    return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        Clock::now() - started).count());
}

std::uint64_t peak_rss_kib() {
    rusage usage{};
    getrusage(RUSAGE_SELF, &usage);
    return static_cast<std::uint64_t>(usage.ru_maxrss);
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const auto args = arguments(argc, argv);
        const auto points = read_points(args.at("--points"));
        qmapli::BaselineBuildContext context;
        context.training_queries = read_queries(args.at("--train-queries"));
        context.validation_queries = read_queries(args.at("--validation-queries"));
        const auto model = args.find("--bmtree-model");
        if (model != args.end()) context.bmtree_model = model->second;
        const auto rsmi_model = args.find("--rsmi-model-prefix");
        if (rsmi_model != args.end()) context.rsmi_model_prefix = rsmi_model->second;
        auto index = qmapli::make_formal_baseline(args.at("--method"), std::move(context));
        const auto build_started = Clock::now();
        index->build(points);
        const auto build_ns = elapsed_ns(build_started);
        const auto serialize_started = Clock::now();
        index->save(args.at("--index"));
        const auto serialize_ns = elapsed_ns(serialize_started);
        std::ofstream output(args.at("--output"), std::ios::trunc);
        output << "method,build_ns,serialize_ns,total_ns,file_bytes,reported_index_bytes,peak_rss_kib\n";
        output << index->method_name() << ',' << build_ns << ',' << serialize_ns << ','
               << build_ns + serialize_ns << ',' << std::filesystem::file_size(args.at("--index"))
               << ',' << index->serialized_size_bytes() << ',' << peak_rss_kib() << '\n';
        return 0;
    } catch (const std::exception& exception) {
        std::cerr << exception.what() << '\n';
        return 2;
    }
}
