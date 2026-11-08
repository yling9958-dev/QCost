"""Phase4 actual deadline outputs and matched work ablations, not discovery CDFs."""
from plot_style import *
def main():
    style();budget=read('fig13_budget_summary.csv');times=read('current_wallclock_summary.csv');work=read('fig13_work_summary.csv')
    methods=['Original Recursive Exact','Cached Anytime Recursive','Hybrid-BestFirst','Hybrid-QMF-NoFeedback','Hybrid-QMF']
    fig,axs=plt.subplots(2,2,figsize=(7.1,5));a,b,c,d=axs.flat
    for m in methods:
        g=budget[(budget.method==m)&(budget.metric=='root_optimal')].sort_values('budget_ratio')
        a.errorbar(g.budget_ratio,g['mean']*100,yerr=cierr(g)*100,color=COLORS[m],marker=MARKERS[m],
                    ls='--' if m=='Original Recursive Exact' else '-',lw=1.7,elinewidth=.8,capsize=1.8,markersize=5)
    a.set(xlabel='Normalized time budget',ylabel='Optimal-root rate (%)',ylim=(-3,105),xlim=(.19,1.57),
          xticks=[.25,.5,.75,1,1.5],xticklabels=['0.25','0.50','0.75','1.00','1.50'],yticks=[0,25,50,75,100])
    g=times[times.metric=='total_optimizer_time'].set_index('method').loc[methods]
    b.bar(np.arange(5),g['mean'],yerr=cierr(g),width=.65,color=[COLORS[m] for m in methods],edgecolor='#333333',linewidth=.45,
             capsize=2,error_kw={'elinewidth':.9},zorder=3)
    b.set(xticks=np.arange(5),xticklabels=['Original\nExact','Cached\nAnytime','Hybrid\nBestFirst','No\nfeedback','Hybrid\nQMF'],
          ylabel='Optimization time (s)',ylim=(0,g.ci_high.max()*1.08))
    b.tick_params(axis='x',labelsize=9.8);b.yaxis.set_major_locator(MultipleLocator(.1))
    metrics=['work_exact_completed','work_terminal_work','total_optimizer_time'];xt=['Exact\nstates','Terminal\ncost calls','Wall-clock\ntime']
    for ax,part,ms in [(c,'cache',['Anytime Recursive (cache off)','Cached Anytime Recursive']),
                       (d,'feedback',['Hybrid-QMF-NoFeedback','Hybrid-QMF'])]:
        for i,m in enumerate(ms):
            q=work[(work.panel==part)&(work.method==m)].set_index('metric').loc[metrics]
            ax.bar(np.arange(3)+(i-.5)*.30,q['mean'],width=.28,yerr=cierr(q),color=COLORS[m],edgecolor='#333333',
                   linewidth=.45,capsize=2,error_kw={'elinewidth':.9},zorder=3)
        hi=work[(work.panel==part)&work.method.isin(ms)].ci_high.max()
        ax.set(xticks=np.arange(3),xticklabels=xt,ylabel='Ratio to cache off' if part=='cache' else 'Ratio to no feedback',ylim=(0,hi*1.07))
        ax.axhline(1,color='#4D4D4D',ls=':',lw=.9,zorder=2);ax.yaxis.set_major_locator(MultipleLocator(.25));ax.tick_params(axis='x',labelsize=10.4)
    titles=['(a) Budgeted root optimality','(b) Optimization time','(c) Cache reuse','(d) Feedback effects']
    for ax,title in zip(axs.flat,titles):clean(ax);panel(fig,ax,title)
    h=method_handles(methods+['Anytime Recursive (cache off)'])
    lg=legend(fig,h,cols=3,fontsize=10.5)
    compact_layout(fig,axs,[lg],plot_height_pt=116,col_gap_pt=10,row_gap_pt=6,legend_gap_pt=3)
    export(fig,'fig13_hybrid_effectiveness')
if __name__=='__main__':main()
