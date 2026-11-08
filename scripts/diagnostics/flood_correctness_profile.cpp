#include "qmapli/formal_baselines.hpp"
#include "../paper_eval/flood_memory_trace.hpp"
#include <algorithm>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <vector>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>

// Engineering-only: all frozen correctness boxes, exact ID-set comparison to
// an independently scanned, read-only mapped prefix. No formal output writes.
int main(int argc,char** argv) {
    try {
        if(argc!=5) throw std::runtime_error("INDEX QUERY_CSV OUTPUT_CSV TRACE_CSV required");
        FloodMemoryTrace trace(argv[4],getpid());
        trace.emit("before_index_load");
        auto index=qmapli::make_learnedbench_flood({});
        index->load(argv[1]);
        trace.emit("after_index_load");
        int fd=open(argv[1],O_RDONLY); struct stat st{};
        if(fd<0||fstat(fd,&st)) throw std::runtime_error("prefix open failed");
        auto* bytes=static_cast<const unsigned char*>(mmap(nullptr,st.st_size,PROT_READ,MAP_PRIVATE,fd,0));
        if(bytes==MAP_FAILED) throw std::runtime_error("prefix mmap failed");
        std::uint64_t count=0; std::memcpy(&count,bytes,8);
        trace.emit("after_point_data_load");
        std::ifstream queries(argv[2]); std::string line;
        std::getline(queries,line);
        std::ofstream out(argv[3]); out << "query_id,truth_count,result_count,missing,extra,exact,count_exact,id_digest\n";
        std::size_t ordinal=0;
        while(std::getline(queries,line)) {
            std::stringstream ss(line); std::string value; std::vector<std::string> f;
            while(std::getline(ss,value,',')) f.push_back(value);
            if(f.size()<7||f[2]!="correctness") continue;
            qmapli::Rect box{std::stod(f[3]),std::stod(f[4]),std::stod(f[5]),std::stod(f[6])};
            trace.emit("before_query",ordinal);
            auto result=index->range_query(box);
            trace.emit("after_query",ordinal+1);
            std::vector<std::uint32_t> expected;
            for(std::uint64_t i=0;i<count;++i) {
                qmapli::Point p; std::memcpy(&p,bytes+9+i*sizeof(p),sizeof(p));
                if(p.x>=box.xmin && p.x<=box.xmax && p.y>=box.ymin && p.y<=box.ymax) expected.push_back(p.id);
            }
            std::sort(expected.begin(),expected.end()); expected.erase(std::unique(expected.begin(),expected.end()),expected.end());
            std::vector<std::uint32_t> missing,extra;
            std::set_difference(expected.begin(),expected.end(),result.ids.begin(),result.ids.end(),std::back_inserter(missing));
            std::set_difference(result.ids.begin(),result.ids.end(),expected.begin(),expected.end(),std::back_inserter(extra));
            auto counted=index->range_count(box);
            std::uint64_t digest=14695981039346656037ULL;
            for(auto id:result.ids) for(int b=0;b<4;++b) {digest^=(id>>(8*b))&255; digest*=1099511628211ULL;}
            out<<f[0]<<','<<expected.size()<<','<<result.ids.size()<<','<<missing.size()<<','<<extra.size()<<','
               <<(missing.empty()&&extra.empty())<<','<<(counted.count==expected.size())<<','<<digest<<'\n'; out.flush();
            if(!missing.empty()||!extra.empty()||counted.count!=expected.size()) throw std::runtime_error("exactness failed "+f[0]);
            ++ordinal;
            if(ordinal==1||ordinal==100||ordinal==500||ordinal==1000) trace.emit("after_"+std::to_string(ordinal)+"_queries",ordinal);
        }
        if(ordinal!=1000) throw std::runtime_error("expected all 1000 correctness queries");
        munmap(const_cast<unsigned char*>(bytes),st.st_size);close(fd);
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
