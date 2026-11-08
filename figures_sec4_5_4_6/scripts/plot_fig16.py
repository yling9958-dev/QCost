"""Matched native-kernel campaign only; never splice historical R4/Cost-H1."""
from plot_style import *
from matplotlib.ticker import FuncFormatter

METHODS=['Recursive Exact','Cached Anytime Recursive','Hybrid-BestFirst','Hybrid-QMF']

def grouped(ax,s,points,metric,methods,with_ci):
    width=.175 if len(methods)==4 else .15;x=np.arange(4)
    for i,method in enumerate(methods):
        g=s[(s.points==points)&(s.metric==metric)&(s.method==method)].set_index('dataset').loc[DATASETS]
        kw={}
        if with_ci:kw=dict(yerr=cierr(g),capsize=1.8,error_kw={'elinewidth':.9})
        ax.bar(x+(i-(len(methods)-1)/2)*width,g['mean'],width=width*.91,
          color=COLORS[method],edgecolor='#333333',lw=.45,hatch='//' if method=='Hybrid-BestFirst' else '',zorder=3,**kw)
    maximum=(s[(s.points==points)&(s.metric==metric)].ci_high.max() if with_ci else s[(s.points==points)&(s.metric==metric)]['mean'].max())
    ax.set(xticks=x,xticklabels=['GeoLife','Gowalla','NYC\nTaxi','Skewed\n2D'],xlim=(-.5,3.5),ylim=(0,maximum*1.13))
    if metric=='build_seconds':
        ax.set_ylabel('Construction time (s)');ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
    else:
        ax.set_ylabel('Mean query latency (ms)');ax.yaxis.set_major_locator(MultipleLocator(.0002 if points==20000 else .0004))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p:'0' if v==0 else f'{v:.4f}'))
    ax.tick_params(axis='x',labelsize=11);clean(ax)

def main():
    style();s=read('scalability_summary.csv')
    assert s.independent_builds.eq(1).all() and s.ci_low.isna().all()
    fig,axs=plt.subplots(2,2,figsize=(7.1,4.8))
    for ax,n,metric,title in zip(axs.flat,[20000,50000,20000,50000],['build_seconds']*2+['mean_ms']*2,
        ['(a) Build time at 20K','(b) Build time at 50K','(c) Query latency at 20K','(d) Query latency at 50K']):
        grouped(ax,s,n,metric,METHODS,False);panel(fig,ax,title)
    lg=legend(fig,method_handles(METHODS,kind='bar'),cols=4,fontsize=10.5)
    compact_layout(fig,axs,[lg],plot_height_pt=120,col_gap_pt=9,row_gap_pt=7,legend_gap_pt=3)
    export(fig,'fig16_index_scalability')
    # Independent 20K five-build replication: separate campaign, no fabricated 50K CI.
    p=read('hybrid_20k_five_build_summary.csv');methods=METHODS[:1]+['Original Analytic QMF']+METHODS[1:]
    assert p.independent_builds.eq(5).all()
    fig,axs=plt.subplots(1,2,figsize=(7.1,2.8))
    for ax,metric,title in zip(axs,['build_seconds','mean_ms'],['(a) Build time at 20K','(b) Query latency at 20K']):
        grouped(ax,p,20000,metric,methods,True);panel(fig,ax,title)
    lg=legend(fig,method_handles(methods,kind='bar'),cols=3,fontsize=10.5)
    compact_layout(fig,axs,[lg],plot_height_pt=121,col_gap_pt=9,legend_gap_pt=3)
    export(fig,'fig16_20k_five_builds_supplement')

if __name__=='__main__':main()
