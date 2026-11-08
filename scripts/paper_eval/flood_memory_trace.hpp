#pragma once
#include <chrono>
#include <fstream>
#include <string>
#include <stdexcept>
#include <unistd.h>

// Opt-in diagnostic observation only; never called inside a timed query.
class FloodMemoryTrace {
    std::ofstream out_;
    int pid_;
    static unsigned long long kb(const std::string& file, const std::string& key) {
        std::ifstream in(file); std::string name, rest;
        while (in >> name) {
            if (name == key) { unsigned long long value=0; in >> value; return value*1024; }
            std::getline(in, rest);
        }
        return 0;
    }
    static std::string scalar(const std::string& file) {
        std::ifstream in(file); std::string value; in >> value; return value;
    }
public:
    explicit FloodMemoryTrace(const std::string& path, int pid):pid_(pid) {
        if (path.empty()) return;
        out_.open(path, std::ios::app);
        if (!out_) throw std::runtime_error("cannot open Flood memory trace");
        if (out_.tellp()==0) out_ << "timestamp,phase,query_count,rss_bytes,pss_bytes,peak_rss_bytes,cgroup_memory_current,cgroup_memory_peak,cgroup_swap_current,host_MemAvailable\n";
    }
    void emit(const std::string& phase, std::size_t count=0) {
        if (!out_.is_open()) return;
        const auto proc="/proc/"+std::to_string(pid_)+"/";
        std::ifstream cg(proc+"cgroup"); std::string line, root;
        while (std::getline(cg,line)) if (line.rfind("0::",0)==0) root="/sys/fs/cgroup"+line.substr(3);
        const auto now=std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
        out_.precision(17);
        out_ << now << ',' << phase << ',' << count << ',' << kb(proc+"status","VmRSS:")
             << ',' << kb(proc+"smaps_rollup","Pss:") << ',' << kb(proc+"status","VmHWM:")
             << ',' << scalar(root+"/memory.current") << ',' << scalar(root+"/memory.peak")
             << ',' << scalar(root+"/memory.swap.current") << ',' << kb("/proc/meminfo","MemAvailable:") << '\n';
        out_.flush();
    }
};
