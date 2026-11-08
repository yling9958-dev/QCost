#include "qmapli/static_qmap_index.hpp"
#include <fstream>
#include <cstdlib>
#include <sstream>
#include <iostream>
#include <stdexcept>
#include <vector>
#include <string>
extern unsigned long long fair_visits,fair_covered,fair_refined;
int main(int argc,char**argv){try{
 if(argc!=4)throw std::runtime_error("index queries output");
 auto index=qmapli::make_static_qmap_index("qmap_uniform_qmf");index->load(argv[1]);
 std::ifstream f(argv[2]);std::ofstream o(argv[3]);std::string l;std::getline(f,l);
 o<<"query_id,result_count,visited_nodes,subtree_count_additions,boundary_points_checked\n";
 while(std::getline(f,l)){
  std::istringstream s(l);std::vector<std::string>a;std::string v;while(std::getline(s,v,','))a.push_back(v);
  if(a.size()<8)throw std::runtime_error("query fields");
  if(a[1]!="performance"&&a[1]!="probe")continue;
  qmapli::Rect q{std::strtod(a[3].c_str(),nullptr),std::strtod(a[4].c_str(),nullptr),std::strtod(a[5].c_str(),nullptr),std::strtod(a[6].c_str(),nullptr)};
  fair_visits=fair_covered=fair_refined=0;auto count=index->range_count(q).count;
  if(count!=std::stoull(a[7]))throw std::runtime_error("instrumented count mismatch");
  o<<a[0]<<','<<count<<','<<fair_visits<<','<<fair_covered<<','<<fair_refined<<'\n';
 }
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
