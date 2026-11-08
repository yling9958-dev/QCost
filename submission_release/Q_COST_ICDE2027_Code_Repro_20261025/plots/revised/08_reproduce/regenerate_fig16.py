"""Matched native-kernel campaign only; never splice historical R4/Cost-H1."""
from plot_style import *
from matplotlib.ticker import FuncFormatter

METHODS=['Recursive Exact','Cached Anytime Recursive','Hybrid-QMF']

def grouped(ax,s,points,metric,methods,with_ci):
    width=.70/len(methods);x=np.arange(4)
    for i,method in enumerate(methods):
        g=s[(s.points==points)&(s.metric==metric)&(s.method==method)].set_index('dataset').loc[DATASETS]
        kw={}
        if with_ci:kw=dict(yerr=cierr(g),capsize=1.8,error_kw={'elinewidth':.9})
        ax.bar(x+(i-(len(methods)-1)/2)*width,g['mean'],width=width*.91,
          color=COLORS[method],edgecolor='#333333',lw=.45,hatch='',zorder=3,**kw)
    maximum=(s[(s.points==points)&(s.metric==metric)].ci_high.max() if with_ci else s[(s.points==points)&(s.metric==metric)]['mean'].max())
    ax.set(xticks=x,xticklabels=['GeoLife','Gowalla','NYC\nTaxi','Skewed\n2D'],xlim=(-.5,3.5),ylim=axis_limits('fig16'+{(20000,'build_seconds'):'a',(50000,'build_seconds'):'b',(20000,'mean_ms'):'c',(50000,'mean_ms'):'d'}[(points,metric)]))
    if metric=='build_seconds':
        ax.set_ylabel('Construction time (s)');ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
    else:
        ax.set_ylabel('Mean query latency (ms)');ax.yaxis.set_major_locator(MultipleLocator(.0002 if points==20000 else .0004))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p:'0' if v==0 else f'{v:.4f}'))
    ax.tick_params(axis='x',labelsize=11);clean(ax)

def main():
    style();SHORT['Hybrid-QMF']='Q-COST';s=read('FIG16_REVISED_DATA.csv')
    assert s.independent_builds.eq(1).all() and s.ci_low.isna().all()
    fig,axs=plt.subplots(2,2,figsize=(7.1,4.8))
    for ax,n,metric,title in zip(axs.flat,[20000,50000,20000,50000],['build_seconds']*2+['mean_ms']*2,
        ['(a) Build time at 20K','(b) Build time at 50K','(c) Query latency at 20K','(d) Query latency at 50K']):
        grouped(ax,s,n,metric,METHODS,False);panel(fig,ax,title)
    lg=legend(fig,method_handles(METHODS,kind='bar'),cols=3,fontsize=10.5)
    compact_layout(fig,axs,[lg],plot_height_pt=120,col_gap_pt=9,row_gap_pt=7,legend_gap_pt=3)
    export(fig,'fig16_index_scalability')

if __name__=='__main__':main()
