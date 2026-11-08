"""Compact 28-pair plot; confirmed Flood aggregate uses ordinary Flood styling."""
from plot_style import *
from matplotlib.patches import Patch
import hashlib

def main():
    style();d=read('fullscale_results.csv')
    assert len(d)==28 and not d.duplicated(['dataset','method']).any()
    metrics=[('mean_ms','Mean latency (ms)','(a) Mean latency'),
             ('p95_ms','P95 latency (ms)','(b) P95 latency'),
             ('p99_ms','P99 latency (ms)','(c) P99 latency'),
             ('qps','Throughput (QPS)','(d) Query throughput')]
    assert np.isfinite(d[[m[0] for m in metrics]]).all().all()
    assert (d[[m[0] for m in metrics]]>0).all().all()
    target=d.method.eq('Flood') & d.dataset.eq('Skewed 2D') & d.point_count.eq(204986702)
    assert target.sum()==1
    assert np.allclose(d.loc[~target,'qps'],1000/d.loc[~target,'mean_ms'],rtol=1e-12)
    # Retain the confirmed six-decimal QPS; only this record allows rounding error.
    assert abs(float(d.loc[target,'qps'].iloc[0])-1000/float(d.loc[target,'mean_ms'].iloc[0]))<=0.5e-6
    # The explicit confirmation changes eligibility, never a measured value.
    accepted=d.copy();accepted['formal_plot_eligible']=True
    accepted['acceptance_basis']=np.where(d.status.eq('PASS'),'retained_raw_records','explicit_user_confirmation')
    accepted.to_csv(OUT/'data/fullscale_plot_accepted.csv',index=False)
    speed=[]
    for ds in DATASETS:
        group=d[d.dataset==ds];q=group[group.method=='Q-COST'].iloc[0]
        best=group[group.method!='Q-COST'].sort_values('mean_ms').iloc[0]
        speed.append(dict(dataset=ds,competitor=best.method,qcost_mean_ms=q.mean_ms,
            competitor_mean_ms=best.mean_ms,speedup=best.mean_ms/q.mean_ms,competing_methods=6))
    speed=pd.DataFrame(speed);speed.to_csv(OUT/'data/fig7_speedups_28_pairs.csv',index=False)
    limits={key:(10**np.floor(np.log10(d[key].min()))/2,d[key].max()*(8 if key=='mean_ms' else 1.8))
            for key,_,_ in metrics}
    fig,axs=plt.subplots(2,2,figsize=(7.1,4.5))
    fig.subplots_adjust(left=.085,right=.99,bottom=.1,top=.86,wspace=.25,hspace=.4)
    points=[];styles=[]
    for j,(ax,(metric,lab,title)) in enumerate(zip(axs.flat,metrics)):
        for mi,m in enumerate(METHODS):
            for di,ds in enumerate(DATASETS):
                r=d[(d.dataset==ds)&(d.method==m)].iloc[0]
                v=float(r[metric]);x=di+(mi-3)*.111;base=limits[metric][0]
                bar=ax.bar(x,v-base,bottom=base,width=.102,color=COLORS[m],edgecolor='#333333',
                           linewidth=.45,hatch=HATCHES[m],zorder=3)[0]
                points.append(dict(metric=metric,dataset=ds,method=m,value=v,x=x,baseline=base,source_file=r.source_file))
                styles.append(dict(metric=metric,dataset=ds,method=m,color=COLORS[m],hatch=HATCHES[m],
                                   alpha=bar.get_alpha(),edgecolor='#333333',linewidth=.45))
        ax.set(xticks=np.arange(4),xticklabels=DATASETS,xlim=(-.5,3.5),ylabel=lab)
        log_axis(ax,lim=limits[metric]);clean(ax)
        ax.yaxis.set_major_locator(LogLocator(base=10,numticks=12));ax.tick_params(axis='x',labelsize=10.3)
        panel(fig,ax,title)
    patches=[Patch(facecolor=COLORS[m],edgecolor='#333333',linewidth=.45,hatch=HATCHES[m],label=m) for m in METHODS]
    lg=fig.legend(handles=row_major(patches,4),loc='upper center',bbox_to_anchor=(.5,.995),ncol=4,
               frameon=False,fontsize=11,handlelength=1.35,handleheight=.9,columnspacing=1.3,
               handletextpad=.4,labelspacing=.35,borderaxespad=0,borderpad=0)
    compact_layout(fig,axs,[lg],plot_height_pt=110,col_gap_pt=5,row_gap_pt=5,legend_gap_pt=3)
    export(fig,'fig7_grouped_bar')
    pd.DataFrame(points).to_csv(OUT/'data/fig7_current_plotted_values.csv',index=False)
    pd.DataFrame(styles).to_csv(OUT/'reports/fig7_bar_style_audit.csv',index=False)
    (OUT/'reports/fig7_current_data_check.json').write_text(json.dumps(dict(
        accepted_pairs=28,bar_endpoints=112,source_csv='data/fullscale_results.csv',
        source_sha256=hashlib.sha256((OUT/'data/fullscale_results.csv').read_bytes()).hexdigest(),
        confirmed_flood_summary_included=True,flood_style_identical_across_datasets=True,
        speedup_competitors_per_dataset=6,limits={k:list(v) for k,v in limits.items()}),indent=2))

if __name__=='__main__':main()
