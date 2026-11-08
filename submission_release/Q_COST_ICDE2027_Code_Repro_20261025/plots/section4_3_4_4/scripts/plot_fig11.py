"""Original budget-curve plotting logic, now includes deterministic Beam width."""
from plot_style import *
def main():
    style();d=read('fig11_summary.csv');d=d[d.BudgetLabel.isin(['32','64','128','256','512'])].copy()
    d['budget']=d.BudgetLabel.astype(int)
    methods=['Original Analytic QMF','Random Search','Beam Search'];fig,axs=plt.subplots(2,2,figsize=(7.1,4.8))
    metrics=['OptimalConfiguration','OptimalRoot','ConfigurationGap','RootRegret']
    titles=['(a) Configuration optimality','(b) Root-action optimality','(c) Configuration regret','(d) Root-action regret']
    for ax,metric,title in zip(axs.flat,metrics,titles):
        for m in methods:
            g=d[(d.method==m)&(d.metric==metric)].sort_values('budget')
            ax.errorbar(g.budget,g['mean'],yerr=cierr(g),color=COLORS[m],marker=MARKERS[m],
              ls='--' if m=='Random Search' else '-.' if m=='Beam Search' else '-',lw=1.7,
              markersize=5.5,capsize=2,elinewidth=.9)
        ax.set_xscale('log',base=2);ax.set_xticks([32,64,128,256,512],['32','64','128','256','512'])
        ax.set(xlabel='Search budget',xlim=(27,605),ylabel='Optimality (%)' if metric.startswith('Optimal') else 'Regret (proxy cost)')
        if metric.startswith('Optimal'):
            ax.set_ylim(0,105);ax.set_yticks([0,25,50,75,100]);ax.axhline(100,color='#4D4D4D',lw=.9,ls=':')
        else:
            upper=d[d.metric==metric].ci_high.max();ax.set_ylim(-upper*.035,upper*1.07)
            ax.axhline(0,color='#4D4D4D',lw=.9,ls=':');ax.yaxis.set_major_locator(MaxNLocator(4))
        clean(ax);panel(fig,ax,title)
    h=method_handles(methods)+[Line2D([],[],color='#4D4D4D',ls=':',lw=.9,label='Exact references')]
    lg=legend(fig,h,cols=4,fontsize=10.8)
    compact_layout(fig,axs,[lg],plot_height_pt=104,col_gap_pt=9,row_gap_pt=6,legend_gap_pt=3)
    export(fig,'fig11_budgeted_search_quality')
if __name__=='__main__':main()
