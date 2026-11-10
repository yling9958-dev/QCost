#include "qmapli/runtime_c_api.h"

#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

struct Query {
    std::string id;
    double xmin;
    double ymin;
    double xmax;
    double ymax;
};

std::unordered_map<std::string, std::string> arguments(int argc, char** argv) {
    std::unordered_map<std::string, std::string> output;
    for (int index = 1; index + 1 < argc; index += 2) output[argv[index]] = argv[index + 1];
    return output;
}

std::vector<std::string> fields(const std::string& line) {
    std::vector<std::string> output;
    std::stringstream stream(line);
    std::string field;
    while (std::getline(stream, field, ',')) output.push_back(field);
    return output;
}

std::vector<Query> read_queries(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open queries: " + path);
    std::string line;
    std::getline(input, line);
    std::vector<Query> queries;
    while (std::getline(input, line)) {
        const auto row = fields(line);
        if (row.size() < 7) continue;
        queries.push_back({row[0], std::stod(row[3]), std::stod(row[4]), std::stod(row[5]), std::stod(row[6])});
    }
    return queries;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const auto args = arguments(argc, argv);
        const auto method = args.at("--method");
        const auto queries = read_queries(args.at("--queries"));
        std::ofstream output(args.at("--output"), std::ios::trunc);
        output << "query_id,result_ids,candidates,latency_ns\n";
        char error[1024]{};
        auto* handle = qmap_runtime_open(method.c_str(), args.at("--index").c_str(), error, sizeof(error));
        if (!handle) throw std::runtime_error(error);
        for (const auto& query : queries) {
            std::uint32_t* ids = nullptr;
            std::size_t count = 0;
            std::size_t candidates = 0;
            const auto start = std::chrono::steady_clock::now();
            const auto status = qmap_runtime_query(
                handle, query.xmin, query.ymin, query.xmax, query.ymax,
                &ids, &count, &candidates, error, sizeof(error));
            const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - start).count();
            if (status != 0) throw std::runtime_error(error);
            output << query.id << ',';
            for (std::size_t index = 0; index < count; ++index) {
                if (index) output << ';';
                output << ids[index];
            }
            output << ',' << candidates << ',' << elapsed << '\n';
            qmap_runtime_free_ids(ids);
        }
        qmap_runtime_close(handle);
        return 0;
    } catch (const std::exception& exception) {
        std::cerr << exception.what() << '\n';
        return 2;
    }
}
