"""Two affine-equivalent displays of the same five-build paired observations."""
from plot_style import *
from scipy.stats import t
from matplotlib.ticker import MultipleLocator, FormatStrFormatter
from PIL import Image, ImageDraw, ImageFont

def statistics():
    pairs=read('workload_build_pairs.csv')
    baseline=pairs[pairs.method=='R4 Greedy'][['dataset','build_seed','area_class','mean_ms']].rename(columns={'mean_ms':'baseline_ms'})
    pairs=pairs.merge(baseline,on=['dataset','build_seed','area_class'],validate='many_to_one')
    assert len(pairs)==240 and not pairs.duplicated(['dataset','method','build_seed','area_class']).any()
    assert np.allclose(pairs.r4_mean_ms,pairs.baseline_ms,rtol=1e-12)
    pairs['paired_ratio']=pairs.mean_ms/pairs.baseline_ms
    pairs['reduction_pct']=100*(1-pairs.paired_ratio)
    assert np.allclose(pairs.paired_ratio,pairs.relative_latency,rtol=1e-12)
    rows=[]
    for (ds,m,a),g in pairs.groupby(['dataset','method','area_class'],sort=False):
        assert len(g)==5 and g.build_seed.nunique()==5
        x=g.paired_ratio.to_numpy();r=g.reduction_pct.to_numpy()
        mean=x.mean();half=t.ppf(.975,4)*x.std(ddof=1)/np.sqrt(5)
        red=r.mean();rh=t.ppf(.975,4)*r.std(ddof=1)/np.sqrt(5)
        assert np.isclose(red,100*(1-mean),atol=1e-12) and np.isclose(rh,100*half,atol=1e-12)
        rows.append(dict(dataset=ds,method=m,area_class=a,independent_builds=5,df=4,
            mean_relative_latency=mean,relative_ci_low=mean-half,relative_ci_high=mean+half,
            reduction_pct=red,reduction_ci_low=red-rh,reduction_ci_high=red+rh))
    s=pd.DataFrame(rows);old=read('workload_area_results.csv')
    joined=s.merge(old,on=['dataset','method','area_class'],validate='one_to_one',suffixes=('','_old'))
    assert len(joined)==48
    for a,b in [('mean_relative_latency','mean_relative_latency_old'),('relative_ci_low','ci95_low'),('relative_ci_high','ci95_high')]:
        assert np.allclose(joined[a],joined[b],rtol=1e-12,atol=1e-12)
    pairs.to_csv(OUT/'data/fig9_current_paired_builds.csv',index=False)
    s.to_csv(OUT/'data/fig9_current_statistics.csv',index=False)
    # Rounded outer bounds follow ALL measured CIs plus 4% of their span.
    lo=min(1,s.relative_ci_low.min());hi=max(1,s.relative_ci_high.max());pad=.04*(hi-lo)
    relative_bounds=(np.floor((lo-pad)/.02)*.02,np.ceil((hi+pad)/.02)*.02)
    reduction_bounds=(float(round(100*(1-relative_bounds[1]),8)),float(round(100*(1-relative_bounds[0]),8)))
    return s,relative_bounds,reduction_bounds

def make(s,relative_bounds,reduction_bounds,reduction):
    style();fig,axs=plt.subplots(2,2,figsize=(7.1,4.1))
    fig.subplots_adjust(left=.08,right=.99,bottom=.1,top=.88,wspace=.16,hspace=.45)
    methods=['Cost-H1','Recursive Exact','Q-COST'];labels=[]
    bounds=reduction_bounds if reduction else relative_bounds
    columns=('reduction_pct','reduction_ci_low','reduction_ci_high') if reduction else ('mean_relative_latency','relative_ci_low','relative_ci_high')
    for j,(ax,ds) in enumerate(zip(axs.flat,DATASETS)):
        ax.axhline(0 if reduction else 1,color=COLORS['R4 Greedy'],ls='--',lw=1.1,zorder=1)
        for mi,m in enumerate(methods):
            g=s[(s.dataset==ds)&(s.method==m)].set_index('area_class').loc[['S1','S2','S3']]
            y=g[columns[0]].to_numpy();low=g[columns[1]].to_numpy();high=g[columns[2]].to_numpy()
            x=np.arange(3)+(mi-1)*.065
            ax.errorbar(x,y,yerr=np.vstack([y-low,high-y]),fmt=MARKERS[m],linestyle='-',
                color=COLORS[m],lw=2 if m=='Q-COST' else 1.5,markeredgecolor='white',
                markeredgewidth=.4,markersize=5.5,elinewidth=.95,capsize=2.3,zorder=3+mi)
        ax.set(xticks=np.arange(3),xticklabels=['S1','S2','S3'],xlim=(-.23,2.23),ylim=bounds)
        ax.yaxis.set_major_locator(MultipleLocator(5 if reduction else .05))
        ax.yaxis.set_major_formatter(FormatStrFormatter('%.0f' if reduction else '%.2f'))
        if j%2:ax.tick_params(labelleft=False)
        clean(ax);panel(fig,ax,f'({chr(97+j)}) {ds}')
    h=[Line2D([],[],color=COLORS['R4 Greedy'],ls='--',lw=1.1,
              label='R4 Greedy' if reduction else 'R4 Greedy (reference)')]
    h += [Line2D([],[],color=COLORS[m],ls='-',marker=MARKERS[m],ms=5.5,
              lw=2 if m=='Q-COST' else 1.5,label=m) for m in methods]
    lg=fig.legend(handles=h,loc='upper center',bbox_to_anchor=(.5,.995),ncol=4,frameon=False,
               fontsize=12 if reduction else 10.6,handlelength=1.7,handletextpad=.35,columnspacing=1.1,borderaxespad=0,borderpad=0)
    compact_layout(fig,axs,[lg],plot_height_pt=96,col_gap_pt=12,row_gap_pt=5,legend_gap_pt=4,
                   shared_ylabel='Latency reduction (%)' if reduction else 'Relative mean query latency')
    if reduction:
        for ax,ds in zip(axs.flat,DATASETS):
            r=s[(s.dataset==ds)&(s.method=='Q-COST')&(s.area_class=='S3')].iloc[0]
            result=label_percentage(ax,2+.065,r.reduction_pct,r.reduction_ci_low,r.reduction_ci_high,
                                    f'{r.reduction_pct:+.1f}%',COLORS['Q-COST'])
            labels.append(dict(dataset=ds,**result))
    name='fig9_latency_reduction' if reduction else 'fig9_relative_latency_zoom'
    export(fig,name)
    (OUT/'reports'/f'{name}_data_check.json').write_text(json.dumps(dict(
        source_pairs='data/workload_build_pairs.csv',shared_ylim=list(bounds),
        ci_method='paired build-level Student t, n=5, df=4',
        raw_relative_ci_extent=[float(s.relative_ci_low.min()),float(s.relative_ci_high.max())],
        reduction_ci_bound_reversal_correct=True,all_error_bars_inside_bounds=True,
        qcost_s3_labels=labels),indent=2))

def comparison():
    images=[Image.open(OUT/'figures'/f'{n}.png').convert('RGB') for n in ['fig9_latency_reduction','fig9_relative_latency_zoom']]
    w=max(im.width for im in images);h=max(im.height for im in images)
    canvas=Image.new('RGB',(2*w+60,h+125),'white');draw=ImageDraw.Draw(canvas)
    font=ImageFont.truetype(font_manager.findfont(font_manager.FontProperties(family=FONT,weight='bold')),72)
    for i,(im,label) in enumerate(zip(images,['A. Latency reduction (%)','B. Zoomed relative latency'])):
        canvas.paste(im,(i*(w+60),125));draw.text((i*(w+60)+40,20),label,font=font,fill='#333333')
    canvas.save(OUT/'figures/fig9_comparison.png',dpi=(600,600))

def main():
    s,relative,reduction=statistics();make(s,relative,reduction,True);make(s,relative,reduction,False);comparison()

if __name__=='__main__':main()
