"""Keeps measured wall time and historical phase sums in distinct panels."""
from plot_style import *
def main():
    style();d=read('current_wallclock_summary.csv');p=read('historical_phase_summary.csv')
    fig,axs=plt.subplots(1,2,figsize=(7.1,3.1));a,b=axs
    methods=['Original Recursive Exact','Original Analytic QMF','Cached Anytime Recursive','Hybrid-BestFirst','Hybrid-QMF']
    g=d[d.metric=='total_optimizer_time'].set_index('method').loc[methods]
    a.bar(np.arange(len(g)),g['mean'],yerr=cierr(g),color=[COLORS[m] for m in methods],
          width=.64,edgecolor='#333333',linewidth=.45,capsize=2.1,error_kw={'elinewidth':.9},zorder=3)
    a.set(xticks=np.arange(len(g)),xticklabels=['Original\nExact','Analytic\nQMF','Cached\nAnytime','Hybrid\nBestFirst','Hybrid\nQMF'],
          ylabel='Optimization time (s)',ylim=(0,g.ci_high.max()*1.08))
    stages=['scoring','expansion','cost','selection','other']
    labels=['Scorer evaluation','Conditional expansion','Cost evaluation','Selection','Other measured overhead']
    colors=['#AFC4DF','#4C72B0','#D5B180','#E76F51','#D9D9D9'];hatches=['','//','','','..']
    pm=['Exact Enumeration','Original Recursive Exact','Original Analytic QMF','Random Search','Beam Search']
    bottom=np.zeros(len(pm));x=np.arange(len(pm))
    for stage,c,h in zip(stages,colors,hatches):
        s=p[p.metric==stage].set_index('method').loc[pm]['mean'].to_numpy()
        b.bar(x,s,bottom=bottom,width=.64,color=c,hatch=h,edgecolor='#333333',linewidth=.45,zorder=3);bottom+=s
    total=p[p.metric=='total'].set_index('method').loc[pm]
    b.errorbar(x,bottom,yerr=cierr(total),fmt='none',ecolor='#333333',elinewidth=.9,capsize=2.1,zorder=4)
    assert np.allclose(bottom,total['mean'])
    b.set(xticks=x,xticklabels=['Exact\nenum.','Recursive\nExact','Analytic\nQMF','Random\nSearch','Beam\nSearch'],
          ylabel='Measured phase sum (s)',ylim=(0,total.ci_high.max()*1.08))
    for ax in axs:clean(ax);ax.tick_params(axis='x',labelsize=10);ax.yaxis.set_major_locator(MultipleLocator(.1))
    panel(fig,a,'(a) Wall-clock time');panel(fig,b,'(b) Historical phase costs')
    h=[Patch(facecolor=c,hatch=ht,edgecolor='#333333',linewidth=.45,label=l) for c,ht,l in zip(colors,hatches,labels)]
    lg=legend(fig,h,cols=3,fontsize=10.5)
    compact_layout(fig,axs,[lg],plot_height_pt=127,col_gap_pt=10,row_gap_pt=5,legend_gap_pt=3)
    export(fig,'fig12_optimization_efficiency')
if __name__=='__main__':main()
