"""Separate four-root H=2..4 candidate; does not replace the 25/40-node H=1..3 study."""
from plot_style import *
from matplotlib.ticker import LogLocator,LogFormatterMathtext

def main():
    style();d=read('hybrid_parameter_matched_summary.csv')
    settings=sorted(set(zip(d.h,d.k)));x=np.arange(len(settings));width=.32
    fig,ax=plt.subplots(figsize=(7.1,2.5))
    for i,(m,c) in enumerate([('Recursive Exact','#3C5488'),('Q-COST','#E64B35')]):
        g=d[d.display_method==m].set_index(['h','k']).loc[settings]
        ax.bar(x+(i-.5)*width,g.mean_seconds,width,color=c,edgecolor='#333333',lw=.45,zorder=3)
    ax.set(xticks=x,xticklabels=[f'{h}/{k}' for h,k in settings],xlabel='Planning configuration (H / K)',
      ylabel='Optimization time (s)',ylim=(0,4.8),xlim=(-.6,len(x)-.4))
    clean(ax)
    for at in [2.5,5.5]:ax.axvline(at,color='#D9D9D9',lw=.7,zorder=0)
    panel(fig,ax,'(a) Complete optimization time')
    lg=legend(fig,[Patch(facecolor=c,edgecolor='#333333',lw=.45,label=m) for m,c in [('Recursive Exact','#3C5488'),('Q-COST','#E64B35')]],cols=2)
    compact_layout(fig,[ax],[lg],plot_height_pt=120,legend_gap_pt=3)
    export(fig,'fig15_hybrid_h2_h4_candidate')

if __name__=='__main__':main()
