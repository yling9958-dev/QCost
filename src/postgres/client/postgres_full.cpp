#include <libpq-fe.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>
#include <filesystem>
#include <fcntl.h>
#include <unistd.h>
#include "flood_memory_trace.hpp"

namespace {

using Clock = std::chrono::steady_clock;

bool flood_session_bindings = false;
std::string bound_sql(std::string sql) {
    if (!flood_session_bindings) return sql;
    // PostgreSQL does not search temporary schemas for unqualified functions.
    // Bind only this Flood session to the isolated implementation explicitly.
    for (const std::string name : {"qmap_range_query", "qmap_range_count",
             "qmap_reset_index_cache", "qmap_preload_index", "qmap_fairness_counters"}) {
        std::size_t pos = 0;
        while ((pos = sql.find(name + "(", pos)) != std::string::npos) {
            if (!pos || sql[pos - 1] != '.') { sql.insert(pos, "pg_temp."); pos += 8; }
            pos += name.size();
        }
    }
    return sql;
}

struct Query {
    std::string id;
    std::string selectivity;
    std::string split;
    double xmin = 0;
    double ymin = 0;
    double xmax = 0;
    double ymax = 0;
};

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

std::vector<Query> read_queries(const std::string& path) {
    std::ifstream stream(path);
    if (!stream) throw std::runtime_error("cannot open query file: " + path);
    std::string line;
    std::getline(stream, line);
    std::vector<Query> output;
    while (std::getline(stream, line)) {
        const auto row = fields(line);
        if (row.size() < 7) throw std::runtime_error("invalid query row");
        output.push_back({row[0], row[1], row[2], std::stod(row[3]), std::stod(row[4]),
                          std::stod(row[5]), std::stod(row[6])});
    }
    return output;
}

std::vector<Query> split_queries(const std::vector<Query>& source, const std::string& split) {
    std::vector<Query> output;
    for (const auto& query : source) if (query.split == split) output.push_back(query);
    return output;
}

class Result {
public:
    explicit Result(PGresult* result) : result_(result) {}
    ~Result() { if (result_) PQclear(result_); }
    Result(const Result&) = delete;
    Result& operator=(const Result&) = delete;
    Result(Result&& other) noexcept : result_(other.result_) { other.result_ = nullptr; }
    Result& operator=(Result&& other) noexcept {
        if (this != &other) {
            if (result_) PQclear(result_);
            result_ = other.result_;
            other.result_ = nullptr;
        }
        return *this;
    }
    PGresult* get() const { return result_; }
private:
    PGresult* result_;
};

void require_status(PGconn* connection, PGresult* result, ExecStatusType expected) {
    if (!result || PQresultStatus(result) != expected) {
        const auto message = result ? PQresultErrorMessage(result) : PQerrorMessage(connection);
        throw std::runtime_error(message && message[0] ? message : "PostgreSQL command failed");
    }
}

void execute(PGconn* connection, const std::string& sql) {
    Result result(PQexec(connection, sql.c_str()));
    require_status(connection, result.get(), PGRES_COMMAND_OK);
}

std::string literal(const std::string& value) {
    std::string output = "'";
    for (const auto character : value) output += character == '\'' ? "''" : std::string(1, character);
    return output + "'";
}

std::uint64_t rss_kib(int pid) {
    std::ifstream stream("/proc/" + std::to_string(pid) + "/status");
    std::string key;
    while (stream >> key) {
        if (key == "VmRSS:") {
            std::uint64_t value = 0;
            stream >> value;
            return value;
        }
        std::string remainder;
        std::getline(stream, remainder);
    }
    return 0;
}

std::uint64_t client_peak_rss_kib() {
    rusage usage{};
    getrusage(RUSAGE_SELF, &usage);
    return static_cast<std::uint64_t>(usage.ru_maxrss);
}

class RssSampler {
public:
    explicit RssSampler(int pid) : pid_(pid), thread_([this] { run(); }) {}
    ~RssSampler() {
        stop_.store(true);
        if (thread_.joinable()) thread_.join();
    }
    std::uint64_t peak() const { return peak_.load(); }
private:
    void run() {
        while (!stop_.load()) {
            const auto value = rss_kib(pid_);
            auto current = peak_.load();
            while (value > current && !peak_.compare_exchange_weak(current, value)) {}
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    }
    int pid_;
    std::atomic<bool> stop_{false};
    std::atomic<std::uint64_t> peak_{0};
    std::thread thread_;
};

Result execute_prepared(PGconn* connection, const char* name, const Query& query) {
    std::ostringstream x1, y1, x2, y2;
    x1 << std::setprecision(17) << query.xmin;
    y1 << std::setprecision(17) << query.ymin;
    x2 << std::setprecision(17) << query.xmax;
    y2 << std::setprecision(17) << query.ymax;
    const std::array<std::string, 4> storage{x1.str(), y1.str(), x2.str(), y2.str()};
    const std::array<const char*, 4> values{
        storage[0].c_str(), storage[1].c_str(), storage[2].c_str(), storage[3].c_str()};
    Result result(PQexecPrepared(connection, name, 4, values.data(), nullptr, nullptr, 0));
    require_status(connection, result.get(), PGRES_TUPLES_OK);
    return result;
}

std::string postgis_candidate(const std::string& table) {
    return "SELECT id FROM " + table
        + " WHERE geom && ST_MakeEnvelope($1,$2,$3,$4,4326)"
          " AND lon >= $1 AND lon <= $3 AND lat >= $2 AND lat <= $4";
}

std::string learned_candidate(const std::string& method) {
    return "SELECT qmap_range_query(" + literal(method) + ",$1,$2,$3,$4) AS id";
}

std::string count_sql(const std::string& method, const std::string& table) {
    if (method == "postgis_gist") return "SELECT count(*) FROM (" + postgis_candidate(table) + ") rows";
    return "SELECT qmap_range_count(" + literal(method) + ",$1,$2,$3,$4)";
}

std::string correctness_sql(const std::string& method, const std::string& table) {
    const auto truth = postgis_candidate(table);
    const auto candidate = method == "postgis_gist" ? truth : learned_candidate(method);
    return "WITH truth AS MATERIALIZED (" + truth + "), candidate AS MATERIALIZED (" + candidate + ") "
        "SELECT (SELECT count(*) FROM truth), (SELECT count(*) FROM candidate), "
        "(SELECT count(*) FROM (SELECT id FROM truth EXCEPT SELECT id FROM candidate) missing), "
        "(SELECT count(*) FROM (SELECT id FROM candidate EXCEPT SELECT id FROM truth) extra)";
}

void prepare(PGconn* connection, const char* name, const std::string& sql) {
    Result result(PQprepare(connection, name, bound_sql(sql).c_str(), 4, nullptr));
    require_status(connection, result.get(), PGRES_COMMAND_OK);
}

void commit_file(const std::string& path) {
    const int fd = ::open(path.c_str(), O_RDONLY);
    if (fd < 0 || ::fsync(fd) != 0) throw std::runtime_error("checkpoint fsync failed");
    ::close(fd);
}

std::string fairness_json(PGconn* connection, const std::string& method) {
    if (method == "postgis_gist") return "NATIVE_POSTGIS";
    Result counters(PQexec(connection, bound_sql("SELECT qmap_fairness_counters(" + literal(method) + ")").c_str()));
    require_status(connection, counters.get(), PGRES_TUPLES_OK);
    return PQgetvalue(counters.get(), 0, 0);
}

void checkpoint(const std::string& path, PGconn* connection, const std::string& method,
                RssSampler& sampler, int repetition) {
    const auto fairness = fairness_json(connection, method);
    std::ofstream file(path + ".part");
    file << "{\"repetition\":" << repetition << ",\"backend_peak_rss_kib\":" << sampler.peak()
         << ",\"client_peak_rss_kib\":" << client_peak_rss_kib() << ",\"fairness\":"
         << (method == "postgis_gist" ? "\"NATIVE_POSTGIS\"" : fairness) << "}\n";
    file.close(); commit_file(path + ".part");
    std::filesystem::rename(path + ".part", path);
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const auto args = arguments(argc, argv);
        const auto method = args.at("--method");
        const auto table = args.at("--table");
        const auto queries = read_queries(args.at("--queries"));
        const auto correctness = split_queries(queries, "correctness");
        const auto warmup = split_queries(queries, "warmup");
        const auto performance = split_queries(queries, "performance");
        const auto repetitions = std::stoi(args.at("--repetitions"));
        const auto phase = args.at("--phase");
        const auto first_repetition = std::stoi(args.at("--start-repetition"));
        if (correctness.size() != 1000 || warmup.size() != 300 || performance.size() != 3000 || split_queries(queries, "train").size() != 1000 || split_queries(queries, "validation").size() != 1000 || queries.size() != 6300 || repetitions != 5) {
            throw std::runtime_error("query split cardinalities violate the frozen paper protocol");
        }

        PGconn* connection = PQconnectdb(args.at("--conninfo").c_str());
        if (!connection || PQstatus(connection) != CONNECTION_OK) {
            const auto message = connection ? PQerrorMessage(connection) : "cannot allocate PGconn";
            if (connection) PQfinish(connection);
            throw std::runtime_error(message);
        }
        try {
            FloodMemoryTrace flood_trace(
                method == "flood" && phase == "correctness" && args.count("--memory-trace")
                    ? args.at("--memory-trace") : "", PQbackendPID(connection));
            flood_trace.emit("after_PostgreSQL_connection");
            if (args.count("--flood-session-setup")) {
                if (method != "flood") throw std::runtime_error("Flood binding cannot be used by another method");
                std::ifstream setup(args.at("--flood-session-setup"));
                if (!setup) throw std::runtime_error("cannot read Flood session bindings");
                const std::string sql((std::istreambuf_iterator<char>(setup)),{});
                execute(connection,sql);
                flood_session_bindings = true;
            }
            execute(connection, "SET jit=off; SET max_parallel_workers_per_gather=0;");
            RssSampler sampler(PQbackendPID(connection));
            std::uint64_t preload_ns = 0;
            if (method != "postgis_gist") {
                execute(connection, "SET qmap_benchmark.index_root=" + literal(args.at("--index-root")) + ";");
                execute(connection, "SET qmap_benchmark.normalize_coordinates=on;");
                execute(connection, "SET qmap_benchmark.source_xmin=" + args.at("--source-xmin") + ";");
                execute(connection, "SET qmap_benchmark.source_xmax=" + args.at("--source-xmax") + ";");
                execute(connection, "SET qmap_benchmark.source_ymin=" + args.at("--source-ymin") + ";");
                execute(connection, "SET qmap_benchmark.source_ymax=" + args.at("--source-ymax") + ";");
                Result reset(PQexec(connection, bound_sql("SELECT qmap_reset_index_cache()").c_str()));
                require_status(connection, reset.get(), PGRES_TUPLES_OK);
                const auto preload_started = Clock::now();
                flood_trace.emit("before_index_load");
                Result preload(PQexec(connection, bound_sql("SELECT qmap_preload_index(" + literal(method) + ")").c_str()));
                require_status(connection, preload.get(), PGRES_TUPLES_OK);
                flood_trace.emit("after_index_load");
                flood_trace.emit("after_point_data_load"); // Flood load already owns the points.
                preload_ns = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
                    Clock::now() - preload_started).count());
            }
            if (phase == "correctness") execute(connection, "SET enable_hashagg=off;");
            prepare(connection, "pilot_correctness", correctness_sql(method, table));
            prepare(connection, "pilot_count", count_sql(method, table));

            if (phase == "counts") {
                std::ofstream counts(args.at("--correctness-output"));
                counts << "query_id,selectivity_group,split,exact_count\n";
                for (const auto& query : correctness) {
                    auto counted = execute_prepared(connection, "pilot_count", query);
                    counts << query.id << ',' << query.selectivity << ',' << query.split << ','
                           << PQgetvalue(counted.get(),0,0) << '\n';
                }
                counts.close(); commit_file(args.at("--correctness-output"));
                // Keep the connection alive until the sampler has been destroyed.
            } else {

            if (phase == "correctness") {
            std::ofstream correctness_output(args.at("--correctness-output"), std::ios::trunc);
            correctness_output << "method,query_id,selectivity_group,truth_count,result_count,missing,extra,exact,count_result,count_exact\n";
            std::uint64_t total_missing = 0;
            std::uint64_t total_extra = 0;
            std::size_t completed_correctness = 0;
            for (const auto& query : correctness) {
                flood_trace.emit("before_correctness_query",completed_correctness);
                auto result = execute_prepared(connection, "pilot_correctness", query);
                flood_trace.emit("after_ID_query",completed_correctness+1);
                const auto truth_count = std::stoull(PQgetvalue(result.get(), 0, 0));
                const auto result_count = std::stoull(PQgetvalue(result.get(), 0, 1));
                const auto missing = std::stoull(PQgetvalue(result.get(), 0, 2));
                const auto extra = std::stoull(PQgetvalue(result.get(), 0, 3));
                auto counted = execute_prepared(connection, "pilot_count", query);
                ++completed_correctness;
                flood_trace.emit("after_count_query",completed_correctness);
                if (completed_correctness == 1 || completed_correctness == 100 ||
                    completed_correctness == 500 || completed_correctness == 1000)
                    flood_trace.emit("after_"+std::to_string(completed_correctness)+"_queries",completed_correctness);
                const auto count_result = std::stoull(PQgetvalue(counted.get(),0,0));
                total_missing += missing;
                total_extra += extra;
                correctness_output << method << ',' << query.id << ',' << query.selectivity << ','
                    << truth_count << ',' << result_count << ',' << missing << ',' << extra << ','
                    << (missing == 0 && extra == 0 && count_result == truth_count ? 1 : 0) << ','
                    << count_result << ',' << (count_result == truth_count ? 1 : 0) << '\n';
                correctness_output.flush(); // Read-only live progress; outside all timed queries.
                if (missing || extra || count_result != truth_count) {
                    correctness_output.flush();
                    throw std::runtime_error("correctness failed; performance is invalid and will not run");
                }
            }
            correctness_output.close();
            commit_file(args.at("--correctness-output"));
            checkpoint(args.at("--summary-output"), connection, method, sampler, -1);
            }

            if (phase == "timing") {
            for (const auto& query : warmup) (void)execute_prepared(connection, "pilot_count", query);
            for (int repetition = first_repetition; repetition < repetitions; ++repetition) {
            const auto latency_path = args.at("--latency-output") + ".r" + std::to_string(repetition) + ".csv";
            std::ofstream latency(latency_path + ".part", std::ios::trunc);
            latency << "method,repetition,ordinal,query_id,selectivity_group,latency_ns,result_count\n";
                for (std::size_t ordinal = 0; ordinal < performance.size(); ++ordinal) {
                    const auto started = Clock::now();
                    auto result = execute_prepared(connection, "pilot_count", performance[ordinal]);
                    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
                        Clock::now() - started).count();
                    latency << method << ',' << repetition << ',' << ordinal << ','
                        << performance[ordinal].id << ',' << performance[ordinal].selectivity << ','
                        << elapsed << ',' << PQgetvalue(result.get(), 0, 0) << '\n';
                    if ((ordinal + 1) % 100 == 0) latency.flush(); // Outside measured interval.
                }
            latency.close();
            commit_file(latency_path + ".part");
            std::filesystem::rename(latency_path + ".part", latency_path);
            checkpoint(latency_path + ".ready", connection, method, sampler, repetition);
            }
            }

            }
        } catch (...) {
            PQfinish(connection);
            throw;
        }
        PQfinish(connection);
        return 0;
    } catch (const std::exception& exception) {
        std::cerr << exception.what() << '\n';
        return 2;
    }
}
