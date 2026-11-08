from plot_style import *
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator, ScalarFormatter

def main():
    style();b=read('construction_results.csv');b=b[b.included_in_fig8a].set_index('dataset').loc[DATASETS]
    d=read('storage_results.csv');d=d[d.included]
    fig,axs=plt.subplots(1,2,figsize=(7.1,3.0))
    fig.subplots_adjust(left=.078,right=.992,bottom=.23,top=.695,wspace=.31)
    ax=axs[0];x=np.arange(4)
    ax.bar(x,b.construction_hours,width=.57,color=COLORS['Q-COST'],edgecolor='#333333',linewidth=.55,zorder=3)
    for xx,y in enumerate(b.construction_hours):
        ax.annotate(f'{y:.2f} h',(xx,y),xytext=(0,2.5),textcoords='offset points',ha='center',va='bottom',fontsize=11)
    ax.set(xticks=x,xticklabels=DATASETS,xlabel='Dataset',ylabel='Construction time (h)',ylim=(0,4.65),yticks=[0,1,2,3,4],xlim=(-.6,3.6))
    ax.tick_params(axis='x',labelsize=10.3)
    clean(ax)
    ax=axs[1]
    for di,ds in enumerate(DATASETS):
        for m in METHODS:
            row=d[(d.dataset==ds)&(d.method==m)]
            if row.empty: continue
            r=row.iloc[0]
            ax.scatter(r.state_gib,r.mean_ms,s=53,c=COLORS[m],marker=DSMARKERS[di],
                       edgecolor='#333333',linewidth=.5,zorder=4)
    log_axis(ax,axis='x',lim=(1.7,40));log_axis(ax,lim=(.08,4e4))
    ax.xaxis.set_major_locator(FixedLocator([2,4,8,16,32]));ax.xaxis.set_major_formatter(ScalarFormatter())
    ax.set(xlabel='Persisted index state (GiB)',ylabel='Mean query latency (ms)');clean(ax)
    panel(fig,axs[0],'(a) Construction time',.075)
    panel(fig,axs[1],'(b) Storage versus latency',.075)
    included=[m for m in METHODS if m in set(d.method)]
    h=[Patch(facecolor=COLORS[m],edgecolor='#333333',linewidth=.4,label=m) for m in included]
    methods_legend=fig.legend(handles=h,loc='upper center',bbox_to_anchor=(.5,.995),ncol=6,frameon=False,
               fontsize=10.4,handlelength=1.15,handletextpad=.35,columnspacing=1.0,labelspacing=.35,borderaxespad=0,borderpad=0)
    h=[Line2D([],[],marker=DSMARKERS[i],linestyle='',color='#555555',ms=5.7,label=ds) for i,ds in enumerate(DATASETS)]
    datasets_legend=fig.legend(handles=h,loc='upper center',bbox_to_anchor=(.5,.825),ncol=4,frameon=False,
               fontsize=10.8,handlelength=1.1,handletextpad=.35,columnspacing=1.45,borderaxespad=0,borderpad=0)
    compact_layout(fig,axs,[methods_legend,datasets_legend],plot_height_pt=112,col_gap_pt=7,legend_gap_pt=4)
    export(fig,'fig8_construction_storage')

if __name__=='__main__':main()
