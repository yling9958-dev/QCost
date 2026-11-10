"""Original gate-validation data; actual transpiled depth, no quantum execution."""
from plot_style import *
from matplotlib.ticker import LogLocator,LogFormatterMathtext

def main():
    style();d=read('gate_validation_results.csv').sort_values(['N','j'])
    c=read('circuit_complexity.csv').query('bits==4').set_index(['N','j']).loc[list(zip(d.N,d.j))]
    labels=[f'{n}/{j}' for n,j in zip(d.N,d.j)];x=np.arange(len(d));width=.34
    fig,axs=plt.subplots(2,1,figsize=(7.1,4.6));a,b=axs
    a.bar(x-width/2,d.analytical_pct,width,color='#3C5488',edgecolor='#333333',linewidth=.45,label='Analytical',zorder=3)
    a.bar(x+width/2,d.aer_pct,width,color='#E64B35',edgecolor='#333333',linewidth=.45,label='Qiskit Aer',zorder=3)
    a.set(ylabel='Success probability (%)',ylim=(0,100),yticks=[0,25,50,75,100])
    # Connect only configurations from the same address space.
    for n,g in d.assign(position=x).groupby('N'):
        cc=c.loc[[(n,j) for j in g.j]]
        b.plot(g.position,cc.circuit_depth,color='#E64B35',marker='o',lw=1.7,ms=5.5,zorder=3)
    b.set(yscale='log',ylabel='Circuit depth',ylim=(1.5,float(c.circuit_depth.max())*1.4))
    b.yaxis.set_major_locator(LogLocator(base=10,numticks=6));b.yaxis.set_major_formatter(LogFormatterMathtext())
    b.minorticks_off()
    for ax in axs:
        ax.set(xticks=x,xticklabels=labels,xlim=(-.65,len(d)-.35),xlabel='Circuit configuration (N / j)')
        clean(ax)
        for n,g in d.assign(position=x).groupby('N'):
            if n!=64:ax.axvline(g.position.max()+.5,color='#D9D9D9',lw=.7,zorder=0)
    panel(fig,a,'(a) Success probability');panel(fig,b,'(b) Circuit depth')
    handles=[Patch(facecolor=co,edgecolor='#333333',lw=.45,label=l) for l,co in [('Analytical','#3C5488'),('Qiskit Aer','#E64B35')]]
    lg=legend(fig,handles,cols=2,fontsize=11)
    compact_layout(fig,axs.reshape(2,1),[lg],plot_height_pt=111,row_gap_pt=6,legend_gap_pt=3)
    export(fig,'fig14_gate_validation')

if __name__=='__main__':main()
