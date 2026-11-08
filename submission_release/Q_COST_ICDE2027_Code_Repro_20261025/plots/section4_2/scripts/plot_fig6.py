"""Every ECDF is computed from all 15,000 retained query timings."""
from plot_style import *

def main():
    style();raw=read('fullscale_latency_observations.csv')
    summary=read('fullscale_results.csv');fig,axs=plt.subplots(1,2,figsize=(7.1,3.0))
    fig.subplots_adjust(left=.087,right=.975,bottom=.27,top=.765,wspace=.27)
    all_ecdf=[];stats=[]
    for j,(ax,ds) in enumerate(zip(axs,['GeoLife','Skewed 2D'])):
        for m in METHODS:
            g=raw[(raw.dataset==ds)&(raw.method_display==m)]
            if g.empty: continue
            v=np.sort(g.latency_ns.to_numpy(dtype=np.float64)/1e6)
            assert len(v)==15000 and (v>0).all()
            x,counts=np.unique(v,return_counts=True);p=np.cumsum(counts)/len(v)
            ref=summary[(summary.dataset==ds)&(summary.method==m)].iloc[0]
            if ds=='Skewed 2D' and m=='Flood':
                # Original nanosecond observations versus the confirmed six-decimal summary.
                assert abs(v.mean()-ref.mean_ms)<=0.5e-6
                assert abs(np.quantile(v,.95)-ref.p95_ms)<=0.5e-6
            else:
                assert np.isclose(v.mean(),ref.mean_ms,rtol=1e-12)
                assert np.isclose(np.quantile(v,.95),ref.p95_ms,rtol=1e-12)
            # Duplicate x anchors the initial jump at the observed minimum.
            ax.step(np.r_[x[0],x],np.r_[0,p],where='post',color=COLORS[m],
                    ls=LINESTYLES[m],lw=2 if m=='Q-COST' else 1.4,zorder=5 if m=='Q-COST' else 3)
            # Sparse markers sit exactly on empirical steps, without interpolation.
            ids=np.searchsorted(p,[.2,.4,.6,.8,.95])
            ax.plot(x[ids],p[ids],linestyle='',marker=MARKERS[m],color=COLORS[m],
                    ms=4,markeredgecolor='white',markeredgewidth=.3,zorder=6)
            all_ecdf.append(pd.DataFrame(dict(dataset=ds,method=m,latency_ms=x,cumulative_probability=p,multiplicity=counts)))
            stats.append(dict(dataset=ds,method=m,observations=len(v),minimum_ms=v[0],maximum_ms=v[-1],
                              mean_ms=v.mean(),p95_ms=np.quantile(v,.95),p99_ms=np.quantile(v,.99),source_file=g.source_file.iloc[0]))
        ax.set(xlabel='Query latency (ms)',ylim=(0,1),yticks=[0,.25,.5,.75,1])
        if j==0: ax.set_ylabel('Cumulative probability')
        v=raw[(raw.dataset==ds)].latency_ns.to_numpy(dtype=float)/1e6
        log_axis(ax,axis='x',lim=(10**np.floor(np.log10(v.min())),1.5*10**np.ceil(np.log10(v.max()))))
        ax.xaxis.set_major_locator(LogLocator(base=10,numticks=5))
        clean(ax)
        # Separate the bottom-left log tick from the zero-probability tick.
        ax.tick_params(axis='x',pad=3.5)
        panel(fig,ax,f'({chr(97+j)}) {ds}',.085)
    h=[Line2D([],[],color=COLORS[m],ls=LINESTYLES[m],marker=MARKERS[m],ms=4,lw=1.7,label=m) for m in METHODS]
    lg=fig.legend(handles=row_major(h,4),loc='upper center',bbox_to_anchor=(.5,.995),ncol=4,
               frameon=False,fontsize=10.8,columnspacing=1.35,handlelength=2.05,
               handletextpad=.4,labelspacing=.35,borderaxespad=0,borderpad=0)
    compact_layout(fig,axs,[lg],plot_height_pt=112,col_gap_pt=7,legend_gap_pt=3)
    export(fig,'fig6_latency_ecdf')
    # Keep historical derived data byte-for-byte; only verify it during layout work.
    if (OUT/'data/fig6_ecdf_steps.csv').exists():
        old=read('fig6_ecdf_steps.csv');new=pd.concat(all_ecdf,ignore_index=True)
        assert len(old)==len(new)
        # A newly admitted curve can be appended without rewriting historical CSV rows.
        groups=old.groupby(['dataset','method'],sort=False)
        assert set(groups.groups)==set(new.groupby(['dataset','method']).groups)
        for (dataset,method),prior in groups:
            current=new[(new.dataset==dataset)&(new.method==method)]
            assert np.allclose(prior.latency_ms,current.latency_ms,rtol=1e-12)
            assert np.allclose(prior.cumulative_probability,current.cumulative_probability,rtol=1e-12)
            assert np.array_equal(prior.multiplicity,current.multiplicity)
    else:
        pd.concat(all_ecdf,ignore_index=True).to_csv(OUT/'data/fig6_ecdf_steps.csv',index=False)
        pd.DataFrame(stats).to_csv(OUT/'data/fig6_ecdf_statistics.csv',index=False)

if __name__=='__main__':main()
