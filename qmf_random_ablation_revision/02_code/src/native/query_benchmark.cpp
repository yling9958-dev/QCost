#include "qmapli/static_qmap_index.hpp"
#include <fstream>
#include <sstream>
#include <iostream>
#include <iomanip>
#include <chrono>
#include <vector>
#include <string>
#include <stdexcept>
#ifdef PROFILE
extern unsigned long long fair_visits,fair_covered,fair_refined;
#endif
struct Q {std::string id,split; qmapli::Rect b; size_t truth;};
int main(int argc,char** argv){try{
 if(argc!=5)throw std::runtime_error("index query_csv output repetitions");
 auto idx=qmapli::make_static_qmap_index("qmap_uniform_qmf");idx->load(argv[1]);
 std::ifstream f(argv[2]);std::string line;std::getline(f,line);std::vector<Q> qs;
 while(std::getline(f,line)){std::istringstream in(line);std::vector<std::string> a;std::string t;while(std::getline(in,t,','))a.push_back(t);
  if(a.size()!=9)throw std::runtime_error("expected frozen 9-field queries");
  qs.push_back({a[0],a[1],{std::stod(a[3]),std::stod(a[4]),std::stod(a[5]),std::stod(a[6])},std::stoull(a[8])});}
 std::ofstream o(argv[3]);
#ifdef PROFILE
 o<<"query_id,count,boundary_points_scanned,leaf_accesses,subtree_shortcuts\n";
 for(auto&q:qs)if(q.split=="performance"){
  fair_visits=fair_covered=fair_refined=0;auto r=idx->range_query(q.b);if(r.matched_count!=q.truth)throw std::runtime_error("profile mismatch");
  o<<q.id<<','<<r.matched_count<<','<<fair_refined<<','<<r.visited_leaves<<','<<fair_covered<<'\n';}
#else
 std::ofstream correct(std::string(argv[3])+".correctness.csv");correct<<"query_id,expected,count,returned_ids\n";
 for(auto&q:qs)if(q.split=="correctness"){
  auto r=idx->range_query(q.b);auto c=idx->range_count(q.b).count;
  if(c!=q.truth||r.ids.size()!=q.truth)throw std::runtime_error("correctness count mismatch");
  correct<<q.id<<','<<q.truth<<','<<c<<',';for(auto id:r.ids)correct<<id<<';';correct<<'\n';}
 for(auto&q:qs)if(q.split=="warmup")(void)idx->range_count(q.b);
 o<<"repetition,query_id,latency_ns,count\n";
 for(int rep=0;rep<std::stoi(argv[4]);rep++)for(auto&q:qs)if(q.split=="performance"){
  auto start=std::chrono::steady_clock::now();auto c=idx->range_count(q.b).count;auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
  if(c!=q.truth)throw std::runtime_error("performance count mismatch");o<<rep<<','<<q.id<<','<<ns<<','<<c<<'\n';}
#endif
 return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
