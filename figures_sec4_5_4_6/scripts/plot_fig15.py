"""Keep the historical 25-node quality/time and 40-node feasibility populations."""
from plot_style import *
from matplotlib.ticker import LogLocator,LogFormatterMathtext

def main():
    style();d=read('parameter_sensitivity.csv')
    fig,axs=plt.subplots(1,3,figsize=(7.1,2.8))
    colors={2:'#4D4D4D',3:'#E64B35',4:'#3C5488'};markers={2:'o',3:'^',4:'s'};lines={2:':',3:'--',4:'-'}
    for k in [2,3,4]:
        g=d[d.K==k].sort_values('H')
        for a,col in zip(axs[:2],['cost_reduction_pct','optimization_seconds']):
            a.plot(g.H,g[col],c=colors[k],marker=markers[k],ls=lines[k],lw=1.7,ms=5.5,zorder=3)
        axs[2].bar(g.H+(k-3)*.24,g.feasible_nodes,width=.22,color=colors[k],edgecolor='#333333',lw=.45,zorder=3)
    a,b,c=axs
    a.set(ylabel='Cost reduction (%)',ylim=(-7,59),yticks=[0,20,40])
    a.axhline(0,color='#B0B0B0',ls='--',lw=.8,zorder=1)
    a.annotate('48.48%',(3,float(d.query('H==3 and K==4').cost_reduction_pct.iloc[0])),
        xytext=(-1,5),textcoords='offset points',ha='right',va='bottom',fontsize=10.5,color='#3C5488')
    b.set(ylabel='Optimization time (s)',yscale='log',ylim=(.005,.7))
    b.yaxis.set_major_locator(LogLocator(base=10,numticks=3));b.yaxis.set_major_formatter(LogFormatterMathtext());b.minorticks_off()
    c.set(ylabel='Feasible nodes',ylim=(0,40),yticks=[0,10,20,30,40])
    for k in [2,3,4]:
        v=int(d.query('H==3 and K==@k').feasible_nodes.iloc[0]);x=3+(k-3)*.24
        c.annotate(f'{v}',(x,v),xytext=(0,2),textcoords='offset points',ha='center',va='bottom',fontsize=10,annotation_clip=False)
    for ax in axs:ax.set(xlabel='Planning horizon H',xticks=[1,2,3],xlim=(.6,3.5));clean(ax)
    for ax,title in zip(axs,['(a) Cost reduction','(b) Optimization time','(c) Feasible nodes']):panel(fig,ax,title)
    lg=legend(fig,[Line2D([],[],c=colors[k],marker=markers[k],ls=lines[k],label=f'K = {k}') for k in [2,3,4]],cols=3,fontsize=11)
    compact_layout(fig,axs,[lg],plot_height_pt=121,col_gap_pt=8,legend_gap_pt=3)
    export(fig,'fig15_parameter_sensitivity')

if __name__=='__main__':main()
