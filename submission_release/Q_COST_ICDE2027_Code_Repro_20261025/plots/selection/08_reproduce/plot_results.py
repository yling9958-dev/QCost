"""Four-panel selection diagnostics; all curves and uncertainty from measured nodes."""
from pathlib import Path
import os,json
R=Path(__file__).resolve().parents[1];os.environ.setdefault('MPLCONFIGDIR',str(R/'06_reports/mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np,pandas as pd
COLORS={'QF':'#E64B35','RF':'#8F8F8F'};LABELS={'QF':'QMF + Feedback','RF':'Random + Feedback'}
def main(checkpoint=None):
    data=R/'03_metrics';output=R/'05_figures';report=R/'06_reports'
    if checkpoint:
        data=data/('checkpoint_'+checkpoint.lower());output=output/('checkpoint_'+checkpoint.lower());output.mkdir(exist_ok=True);report=output
    summary=pd.read_csv(data/'QMF_SELECTION_METRICS.csv');cdf=pd.read_csv(data/'FIRST_OPTIMAL_DISTRIBUTION.csv')
    summary=summary[summary.Dataset.eq('Overall')]
    plt.rcParams.update({'font.family':'Times New Roman','font.size':15,'axes.labelsize':15,'xtick.labelsize':14,'ytick.labelsize':14,
        'legend.fontsize':14,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,
        'savefig.dpi':600,'lines.linewidth':1.6,'axes.axisbelow':True,'mathtext.fontset':'stix'})
    metric_b=summary[summary.Metric.eq('Normalized_Regret')&summary.Method.isin(COLORS)]
    common_regret_max=max(.01,float(metric_b.CI95_High.max())*1.08)
    layout=[]
    for cohort in ([checkpoint] if checkpoint else ['Original','Validation']):
        fig,axes=plt.subplots(2,2,figsize=(7.1,5.8));fig.subplots_adjust(left=.10,right=.966,bottom=.11,top=.87,wspace=.43,hspace=.65)
        for ax in axes.flat:ax.grid(axis='y',ls='--',lw=.5,color='#dddddd')
        for method in ['QF','RF']:
            for ax,metric in [(axes[0,0],'Optimal_Root'),(axes[0,1],'Normalized_Regret')]:
                g=summary[summary.Cohort.eq(cohort)&summary.Method.eq(method)&summary.Metric.eq(metric)].sort_values('Budget_Ratio')
                scale=100 if metric=='Optimal_Root' else 1.;x=g.Budget_Ratio.to_numpy();y=g.Mean.to_numpy()*scale
                ax.plot(x,y,marker='o' if method=='QF' else 's',color=COLORS[method],label=LABELS[method])
                ax.fill_between(x,g.CI95_Low.to_numpy()*scale,g.CI95_High.to_numpy()*scale,color=COLORS[method],alpha=.15,linewidth=0)
            ax=axes[1,0]
            for metric,ls,marker,threshold in [('Near_1pct','-','o','1%'),('Near_5pct','--','^','5%')]:
                g=summary[summary.Cohort.eq(cohort)&summary.Method.eq(method)&summary.Metric.eq(metric)].sort_values('Budget_Ratio');x=g.Budget_Ratio.to_numpy()
                ax.plot(x,100*g.Mean,ls=ls,marker=marker,color=COLORS[method],label=LABELS[method].split(' +')[0]+', '+threshold)
                ax.fill_between(x,100*g.CI95_Low.to_numpy(),100*g.CI95_High.to_numpy(),color=COLORS[method],alpha=.10,linewidth=0)
            g=cdf[cdf.Cohort.eq(cohort)&cdf.Method.eq(method)].sort_values('Time_Texact');ax=axes[1,1]
            ax.step(g.Time_Texact,100*g.Discovery,where='post',color=COLORS[method])
            ax.fill_between(g.Time_Texact.to_numpy(),100*g.CI95_Low.to_numpy(),100*g.CI95_High.to_numpy(),step='post',color=COLORS[method],alpha=.15,linewidth=0)
        for ax in [axes[0,0],axes[0,1],axes[1,0]]:
            ax.set_xlabel(r'Budget / $T_{\rm exact}$');ax.set_xticks([.25,.5,.75,1.]);ax.set_xlim(.22,1.03)
        axes[1,1].set_xlabel(r'Time / $T_{\rm exact}$');axes[1,1].set_xlim(0,1.);axes[1,1].set_xticks([0,.25,.5,.75,1.])
        axes[0,0].set_ylabel('Optimal root (%)');axes[0,1].set_ylabel('Normalized regret')
        axes[1,0].set_ylabel('Near-optimal (%)');axes[1,1].set_ylabel('Discovery (%)')
        for ax in [axes[0,0],axes[1,0],axes[1,1]]:ax.set_ylim(0,100);ax.set_yticks([0,25,50,75,100])
        axes[0,1].set_ylim(0,common_regret_max)
        titles=['(a) Root optimality','(b) Feasible-root regret','(c) Near-optimal roots','(d) First optimal root']
        for ax,title in zip(axes.flat,titles):ax.set_title(title,fontsize=14,pad=7)
        handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.99),ncol=2,frameon=False)
        axes[1,0].legend(loc='lower right',fontsize=12,frameon=True,facecolor='white',framealpha=.9,ncol=1)
        stem='qmf_selection_'+cohort.lower()
        fig.canvas.draw();renderer=fig.canvas.get_renderer();outside=[]
        for t in fig.findobj(matplotlib.text.Text):
            if t.get_visible() and t.get_text():
                b=t.get_window_extent(renderer)
                if b.x0<0 or b.y0<0 or b.x1>fig.bbox.width or b.y1>fig.bbox.height:outside.append(t.get_text())
        assert not outside,outside
        for ext in ['png','svg','pdf']:fig.savefig(output/f'{stem}.{ext}',dpi=600)
        layout.append(dict(Cohort=cohort,Outside_Text=outside,Size_Inches=list(fig.get_size_inches()),Axes_Limits=[list(a.get_ylim()) for a in axes.flat],Data='QMF_SELECTION_METRICS.csv and FIRST_OPTIMAL_DISTRIBUTION.csv',CI='pointwise node-cluster bootstrap 95%'))
        plt.close(fig)
    (report/'FIGURE_LAYOUT.json').write_text(json.dumps(layout,indent=2))
    print('Generated '+(', '.join(x['Cohort'] for x in layout))+' panels as 600dpi PNG, SVG, vector PDF; common axes')
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--checkpoint',choices=['Original','Validation']);main(parser.parse_args().checkpoint)
