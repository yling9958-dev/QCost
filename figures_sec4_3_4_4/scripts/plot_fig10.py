"""Adapted original fig10: preserved controlled analytic-QMF cohort, honest name."""
from plot_style import *
def main():
    style();d=read('fig10_latency_summary.csv');r=read('fig10_root_summary.csv')
    methods=['R4 Greedy','Cost-H1','Original Recursive Exact','Original Analytic QMF']
    fig,axs=plt.subplots(1,2,figsize=(7.1,2.7));axs=np.asarray(axs).reshape(1,2)
    a,b=axs[0,:];width=.18
    for mi,m in enumerate(methods):
        g=d[d.method==m].set_index('dataset').loc[DATASETS]
        a.bar(np.arange(4)+(mi-1.5)*width,g['mean'],width=width*.94,color=COLORS[m],
          edgecolor='#333333',linewidth=.45,yerr=cierr(g),capsize=1.9,
          error_kw={'elinewidth':.85,'capthick':.85},zorder=3)
    a.set(xticks=np.arange(4),xticklabels=['GeoLife','Gowalla','NYC\nTaxi','Skewed\n2D'],
          ylabel='Mean query latency (ms)',ylim=(0,d.ci_high.max()*1.07),xlim=(-.5,3.5))
    a.tick_params(axis='x',labelsize=10.2);a.yaxis.set_major_locator(MultipleLocator(.01))
    a.yaxis.set_major_formatter(FormatStrFormatter('%.2f'))
    for mi,m in enumerate(methods):
        row=r[r.method==m].iloc[0]
        b.bar(mi,row.rate,width=.64,color=COLORS[m],edgecolor='#333333',linewidth=.45,zorder=3)
        b.annotate(f'{int(row.hits)}/{int(row.records)}',(mi,row.rate),xytext=(0,3),textcoords='offset points',
                   ha='center',va='bottom',fontsize=10.6)
    b.set(xticks=np.arange(4),xticklabels=['R4','H1','Exact','Analytic'],ylabel='Optimal-root rate (%)',ylim=(0,115),xlim=(-.5,3.5))
    b.set_yticks([0,25,50,75,100])
    for ax in [a,b]:clean(ax)
    panel(fig,a,'(a) Mean query latency');panel(fig,b,'(b) Root-action optimality')
    lg=legend(fig,method_handles(methods,'bar'),cols=4,fontsize=10.6)
    compact_layout(fig,axs,[lg],plot_height_pt=112,col_gap_pt=8,legend_gap_pt=4)
    export(fig,'fig10_decision_ablation')
if __name__=='__main__':main()
