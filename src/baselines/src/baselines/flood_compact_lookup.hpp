#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <vector>

// Adapter recovery storage only. Model coordinates and ordering are untouched.
template<bool Swap> class FloodCompactLookup {
    using Key=std::array<float,2>;
    std::vector<Key> keys_;
    std::vector<std::uint64_t> offsets_;
    std::vector<std::uint32_t> ids_;
    template<class Point>static Key key(Point p){return Swap?Key{p.y,p.x}:Key{p.x,p.y};}
public:
    template<class Get>void build(std::size_t n,Get get){
        if(n>std::numeric_limits<std::uint32_t>::max())throw std::runtime_error("Flood lookup ordinal capacity exceeded");
        ids_.resize(n);std::iota(ids_.begin(),ids_.end(),0u);
        std::sort(ids_.begin(),ids_.end(),[&](auto a,auto b){
            auto ka=key(get(a)),kb=key(get(b));
            if(ka<kb)return true;if(kb<ka)return false;return a<b;
        });
        std::size_t u=0;Key prior{};
        for(std::size_t i=0;i<n;++i){auto k=key(get(ids_[i]));if(!i||k!=prior){++u;prior=k;}}
        keys_.resize(u);offsets_.resize(u+1);u=0;
        for(std::size_t i=0;i<n;++i){auto point=get(ids_[i]);auto k=key(point);
            if(!i||k!=prior){keys_[u]=k;offsets_[u]=i;++u;prior=k;}
            ids_[i]=point.id;
        }
        offsets_[u]=n;
    }
    template<class Point>void append(const Point& match,std::vector<std::uint32_t>& out)const{
        // Exact float-to-double promotion, with numeric +0/-0 equivalence.
        // No epsilon, packed-bit equality, quantization or hash collisions.
        auto i=std::lower_bound(keys_.begin(),keys_.end(),match,[](const Key& a,const Point& b){
            return double(a[0])<b[0] || (double(a[0])==b[0] && double(a[1])<b[1]);
        });
        if(i==keys_.end()||double((*i)[0])!=match[0]||double((*i)[1])!=match[1])return;
        auto ordinal=i-keys_.begin();out.insert(out.end(),ids_.begin()+offsets_[ordinal],ids_.begin()+offsets_[ordinal+1]);
    }
    std::size_t distinct()const{return keys_.size();}
    std::size_t id_bytes()const{return ids_.capacity()*sizeof(std::uint32_t);}
    std::size_t bytes()const{return keys_.capacity()*sizeof(Key)+offsets_.capacity()*sizeof(std::uint64_t)+id_bytes();}
};
