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

namespace {

using Clock = std::chrono::steady_clock;

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
    Result result(PQprepare(connection, name, sql.c_str(), 4, nullptr));
    require_status(connection, result.get(), PGRES_COMMAND_OK);
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
        if (correctness.size() != 5000 || warmup.size() != 1000 || performance.size() != 15000) {
            throw std::runtime_error("query split cardinalities violate the frozen pilot protocol");
        }

        PGconn* connection = PQconnectdb(args.at("--conninfo").c_str());
        if (!connection || PQstatus(connection) != CONNECTION_OK) {
            const auto message = connection ? PQerrorMessage(connection) : "cannot allocate PGconn";
            if (connection) PQfinish(connection);
            throw std::runtime_error(message);
        }
        try {
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
                Result reset(PQexec(connection, "SELECT qmap_reset_index_cache()"));
                require_status(connection, reset.get(), PGRES_TUPLES_OK);
                const auto preload_started = Clock::now();
                Result preload(PQexec(connection, ("SELECT qmap_preload_index(" + literal(method) + ")").c_str()));
                require_status(connection, preload.get(), PGRES_TUPLES_OK);
                preload_ns = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
                    Clock::now() - preload_started).count());
            }
            prepare(connection, "pilot_correctness", correctness_sql(method, table));
            prepare(connection, "pilot_count", count_sql(method, table));

            std::ofstream correctness_output(args.at("--correctness-output"), std::ios::trunc);
            correctness_output << "method,query_id,selectivity_group,truth_count,result_count,missing,extra,exact,count_result,count_exact\n";
            std::uint64_t total_missing = 0;
            std::uint64_t total_extra = 0;
            for (const auto& query : correctness) {
                auto result = execute_prepared(connection, "pilot_correctness", query);
                const auto truth_count = std::stoull(PQgetvalue(result.get(), 0, 0));
                const auto result_count = std::stoull(PQgetvalue(result.get(), 0, 1));
                const auto missing = std::stoull(PQgetvalue(result.get(), 0, 2));
                const auto extra = std::stoull(PQgetvalue(result.get(), 0, 3));
                auto counted = execute_prepared(connection, "pilot_count", query);
                const auto count_result = std::stoull(PQgetvalue(counted.get(),0,0));
                total_missing += missing;
                total_extra += extra;
                correctness_output << method << ',' << query.id << ',' << query.selectivity << ','
                    << truth_count << ',' << result_count << ',' << missing << ',' << extra << ','
                    << (missing == 0 && extra == 0 && count_result == truth_count ? 1 : 0) << ','
                    << count_result << ',' << (count_result == truth_count ? 1 : 0) << '\n';
                if (missing || extra || count_result != truth_count) {
                    correctness_output.flush();
                    throw std::runtime_error("correctness failed; performance is invalid and will not run");
                }
            }
            correctness_output.close();

            for (const auto& query : warmup) (void)execute_prepared(connection, "pilot_count", query);
            std::ofstream latency(args.at("--latency-output"), std::ios::trunc);
            latency << "method,repetition,ordinal,query_id,selectivity_group,latency_ns,result_count\n";
            for (int repetition = 0; repetition < repetitions; ++repetition) {
                for (std::size_t ordinal = 0; ordinal < performance.size(); ++ordinal) {
                    const auto started = Clock::now();
                    auto result = execute_prepared(connection, "pilot_count", performance[ordinal]);
                    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
                        Clock::now() - started).count();
                    latency << method << ',' << repetition << ',' << ordinal << ','
                        << performance[ordinal].id << ',' << performance[ordinal].selectivity << ','
                        << elapsed << ',' << PQgetvalue(result.get(), 0, 0) << '\n';
                }
            }
            latency.close();

            std::string fairness = "NATIVE_POSTGIS";
            if (method != "postgis_gist") {
                Result counters(PQexec(connection, ("SELECT qmap_fairness_counters(" + literal(method) + ")").c_str()));
                require_status(connection, counters.get(), PGRES_TUPLES_OK);
                fairness = PQgetvalue(counters.get(), 0, 0);
            }
            std::ofstream summary(args.at("--summary-output"), std::ios::trunc);
            summary << "method,preload_ns,backend_pid,backend_peak_rss_kib,client_peak_rss_kib,total_peak_rss_kib,"
                       "correctness_queries,total_missing,total_extra,warmup_queries,measured_queries,repetitions,fairness_json\n";
            const auto backend_peak = sampler.peak();
            const auto client_peak = client_peak_rss_kib();
            std::string fairness_csv;
            for (const auto character : fairness) fairness_csv += character == '\"' ? "\"\"" : std::string(1, character);
            summary << method << ',' << preload_ns << ',' << PQbackendPID(connection) << ',' << backend_peak << ','
                << client_peak << ',' << backend_peak + client_peak << ',' << correctness.size() << ','
                << total_missing << ',' << total_extra << ',' << warmup.size() << ','
                << performance.size() << ',' << repetitions << ",\"" << fairness_csv << "\"\n";
            summary.close();
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
