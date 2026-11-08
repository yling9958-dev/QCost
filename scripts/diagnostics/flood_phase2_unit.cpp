#include "qmapli/formal_baselines.hpp"
#include <cassert>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>

std::vector<char> bytes(const std::string& path){std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
int main(int argc,char**argv){
    assert(argc==2);std::string root=argv[1];
    for(bool swap:{false,true}){
        std::vector<qmapli::Point> points;
        for(unsigned i=0;i<4096;++i){
            float x=float(i%31)/31.f,y=float(i%47)/47.f;
            if(i%11==0)x=i%2?0.f:-0.f;
            if(i%17==0)y=std::nextafter(0.5f,1.f);
            points.push_back({x,y,4095-i});
        }
        points.push_back(points[3]); // repeated ID, not merely repeated coordinate
        auto input=root+"/unit"+std::to_string(swap)+".idx";
        {std::ofstream f(input,std::ios::binary);std::uint64_t n=points.size();f.write((char*)&n,8);f.write((char*)&swap,1);f.write((char*)points.data(),points.size()*sizeof(points[0]));}
        auto index=qmapli::make_learnedbench_flood({});index->load(input);
        auto size=index->serialized_size_bytes();assert(size>=bytes(input).size());
        {std::ofstream stats(root+"/size"+std::to_string(swap)+".txt");stats<<size<<'\n';}
        for(qmapli::Rect q:std::vector<qmapli::Rect>{{-1,-1,2,2},{0,0,0,1},{0.1,0.2,0.8,0.9},{0.5,0.5,0.5,0.5}}){
            std::vector<std::uint32_t> expected;
            for(auto p:points)if(p.x>=q.xmin&&p.x<=q.xmax&&p.y>=q.ymin&&p.y<=q.ymax)expected.push_back(p.id);
            std::sort(expected.begin(),expected.end());expected.erase(std::unique(expected.begin(),expected.end()),expected.end());
            auto actual=index->range_query(q);assert(actual.ids==expected);assert(actual.candidates==expected.size());assert(index->range_count(q).count==expected.size());
        }
        auto copy=input+".copy";index->save(copy);assert(bytes(input)==bytes(copy));
        index->save(input);assert(bytes(input)==bytes(copy)); // same inode must not truncate
        index->load(copy);assert(index->serialized_size_bytes()==size);
    }
}
