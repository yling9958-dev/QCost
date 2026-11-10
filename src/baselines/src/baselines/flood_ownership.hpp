#pragma once
#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <chrono>
#include <malloc.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

namespace qmapli { namespace flood_memory {
template<class Matches> void match_digest(const Matches& points,bool orientation,std::size_t candidates) {
    const char* path=std::getenv("QMF_FLOOD_MATCH_TRACE");if(!path||!*path)return;
    std::uint64_t h=14695981039346656037ULL;
    for(const auto& p:points)for(double value:p){std::uint64_t bits;std::memcpy(&bits,&value,8);for(int b=0;b<8;++b){h^=(bits>>(8*b))&255;h*=1099511628211ULL;}}
    std::ofstream out(path,std::ios::app);out<<orientation<<','<<points.size()<<','<<candidates<<','<<h<<'\n';
}
inline unsigned long long kb(const std::string& path,const std::string& key) {
    std::ifstream in(path);std::string name,line;
    while(in>>name){if(name==key){unsigned long long n=0;in>>n;return n*1024;}std::getline(in,line);}return 0;
}
inline std::string scalar(const std::string& path){std::ifstream in(path);std::string v;in>>v;return v;}
inline void trace(const char* phase,std::size_t n,std::size_t points,std::size_t coordinates,
                  std::size_t model,std::size_t lookup,std::size_t distinct=0,
                  std::size_t id_capacity=0,std::size_t matches=0,std::size_t results=0) {
    const char* path=std::getenv("QMF_FLOOD_OWNERSHIP_TRACE");if(!path||!*path)return;
    std::ofstream out(path,std::ios::app);if(!out)throw std::runtime_error("Flood ownership trace open failed");
    if(out.tellp()==0)out<<"timestamp,phase,N,rss_bytes,pss_bytes,cgroup_memory_current,cgroup_memory_peak,host_MemAvailable,points_resident_estimate,coordinates_bytes,model_min_bytes,lookup_estimated_bytes,U,id_capacity_bytes,matches_bytes,result_ids_bytes,allocator_inuse,allocator_free\n";
    std::ifstream cgroup("/proc/self/cgroup");std::string line,root;
    while(std::getline(cgroup,line))if(line.rfind("0::",0)==0)root="/sys/fs/cgroup"+line.substr(3);
    auto heap=mallinfo2();out.precision(17);
    out<<std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count()<<','<<phase<<','<<n
       <<','<<kb("/proc/self/status","VmRSS:")<<','<<kb("/proc/self/smaps_rollup","Pss:")
       <<','<<scalar(root+"/memory.current")<<','<<scalar(root+"/memory.peak")<<','<<kb("/proc/meminfo","MemAvailable:")
       <<','<<points<<','<<coordinates<<','<<model<<','<<lookup<<','<<distinct<<','<<id_capacity
       <<','<<matches<<','<<results<<','<<heap.uordblks<<','<<heap.fordblks<<'\n';
}

// The on-disk 9-byte header makes Point records unaligned. Always memcpy them.
class MappedPoints {
    int fd_=-1; void* data_=MAP_FAILED;std::size_t bytes_=0,count_=0;
public:
    MappedPoints()=default;
    MappedPoints(const MappedPoints&)=delete;
    ~MappedPoints(){reset();}
    void reset(){if(data_!=MAP_FAILED)munmap(data_,bytes_);if(fd_>=0)close(fd_);fd_=-1;data_=MAP_FAILED;bytes_=count_=0;}
    void open(const std::filesystem::path& path,bool& orientation) {
        reset();fd_=::open(path.c_str(),O_RDONLY);struct stat st{};
        if(fd_<0||fstat(fd_,&st)||st.st_size<9)throw std::runtime_error("Invalid Flood index");
        bytes_=st.st_size;data_=mmap(nullptr,bytes_,PROT_READ,MAP_PRIVATE,fd_,0);
        if(data_==MAP_FAILED)throw std::runtime_error("Flood mmap failed");
        std::uint64_t n;std::memcpy(&n,data_,8);
        static_assert(sizeof(Point)==12&&sizeof(bool)==1,"Frozen Flood record layout");
        if(n!=(bytes_-9)/sizeof(Point)||(bytes_-9)%sizeof(Point))throw std::runtime_error("Flood index length mismatch");
        count_=n;std::memcpy(&orientation,static_cast<const char*>(data_)+8,1);
    }
    bool active()const{return data_!=MAP_FAILED;}
    std::size_t size()const{return count_;}
    Point at(std::size_t i)const{Point p;std::memcpy(&p,static_cast<const char*>(data_)+9+i*sizeof(Point),sizeof(p));return p;}
    void release_pages(){if(active()&&madvise(data_,bytes_,MADV_DONTNEED))throw std::runtime_error("Flood MADV_DONTNEED failed");}
    void save(const std::filesystem::path& path)const {
        struct stat src{},dst{};if(fstat(fd_,&src))throw std::runtime_error("Flood mapping stat failed");
        if(!stat(path.c_str(),&dst)&&src.st_dev==dst.st_dev&&src.st_ino==dst.st_ino)return;
        std::ofstream out(path,std::ios::binary|std::ios::trunc);
        for(std::size_t pos=0;pos<bytes_;){auto len=std::min<std::size_t>(1024*1024,bytes_-pos);out.write(static_cast<const char*>(data_)+pos,len);pos+=len;}
        if(!out)throw std::runtime_error("Flood mapped save failed");
    }
};
}}
