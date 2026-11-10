from pathlib import Path
import os
OUT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(OUT/'reports/mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import LogLocator, LogFormatterMathtext, NullLocator
from matplotlib import font_manager
import pandas as pd
import numpy as np
import json

DATASETS=['GeoLife','Gowalla','NYC Taxi','Skewed 2D']
METHODS=['Q-COST','BMTree','LISA','Tsunami','Flood','PostGIS GiST','LMSFC']
COLORS=dict(zip(METHODS,['#E64B35','#3C5488','#00A087','#F39B35','#7E6148','#8F8F8F','#4DBBD5']))
MARKERS=dict(zip(METHODS,['o','s','^','D','v','P','X']))
CORE=['R4 Greedy','Cost-H1','Recursive Exact','Q-COST']
COLORS.update({'R4 Greedy':'#8F8F8F','Cost-H1':'#3C5488','Recursive Exact':'#00A087'})
MARKERS.update({'R4 Greedy':'s','Cost-H1':'^','Recursive Exact':'D'})
DSMARKERS=['o','s','^','D']
HATCHES=dict(zip(METHODS,['','//','','','\\\\','..','']))
LINESTYLES=dict(zip(METHODS,['-','--','-.',':','--','-.',':']))
FONT=font_manager.FontProperties(family=['Times New Roman','Liberation Serif','DejaVu Serif']).get_name()

def style(single=False):
    plt.rcParams.update({'font.family':FONT,'font.size':10.5 if single else 11.5,
        'axes.labelsize':11 if single else 12,'xtick.labelsize':10 if single else 11,
        'ytick.labelsize':10 if single else 11,'legend.fontsize':10 if single else 10.8,
        'axes.linewidth':.8,'axes.edgecolor':'#4D4D4D','text.color':'#333333',
        'axes.labelcolor':'#333333','xtick.color':'#333333','ytick.color':'#333333',
        'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','savefig.dpi':600,
        'figure.facecolor':'white','axes.facecolor':'white','lines.linewidth':1.6,
        'lines.markersize':5,'mathtext.fontset':'stix','hatch.linewidth':.45,
        'path.simplify':False})

def clean(ax,axis='y'):
    ax.spines[['top','right']].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis=axis,color='#D9D9D9',linestyle='--',linewidth=.6)
    ax.tick_params(width=.7,length=3,pad=2)

def log_axis(ax,axis='y',lim=None):
    getattr(ax,'set_'+axis+'scale')('log')
    a=getattr(ax,axis+'axis')
    a.set_major_locator(LogLocator(base=10,numticks=6))
    a.set_major_formatter(LogFormatterMathtext(base=10))
    a.set_minor_locator(NullLocator())
    if lim is not None: getattr(ax,'set_'+axis+'lim')(*lim)

def panel(fig,ax,text,y=0,size=14.5):
    box=ax.get_position()
    title=fig.text((box.x0+box.x1)/2,y,text,ha='center',va='top',weight='bold',fontsize=14.5,wrap=False)
    title.set_gid('panel_title')
    if not hasattr(fig,'_panel_pairs'):fig._panel_pairs=[]
    fig._panel_pairs.append((ax,title))
    return title

def handles(methods,marker=True):
    return [Line2D([],[],linestyle='none',marker=MARKERS[m] if marker else 'o',
        color=COLORS[m],markeredgecolor='#333333',markeredgewidth=.4,markersize=5.6,label=m) for m in methods]

def legend(fig,methods,y,cols=4,fontsize=None):
    return fig.legend(handles=row_major(handles(methods),cols),loc='lower center',bbox_to_anchor=(.5,y),ncol=cols,
                      frameon=False,columnspacing=1.2,handletextpad=.35,handlelength=1,
                      borderaxespad=0,labelspacing=.45,fontsize=fontsize)

def row_major(items,cols):
    return [items[i] for c in range(cols) for i in range(c,len(items),cols)]

def read(name): return pd.read_csv(OUT/'data'/name)

def export_legacy(fig,name):
    # Exact canvas size, no bbox_inches='tight' rescaling.
    fig.canvas.draw()
    for ext in ['pdf','svg','png']:
        fig.savefig(OUT/'figures'/f'{name}.{ext}',dpi=600,facecolor='white')
    # Export backends can leave text transforms at their export DPI; redraw
    # before measuring extents in the original canvas coordinate system.
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    rect=fig.bbox
    checks=[]
    for ax in fig.axes:
        texts=[ax.xaxis.label,ax.yaxis.label]
        for axis,locs,labels,limits in [('x',ax.get_xticks(),ax.get_xticklabels(),sorted(ax.get_xlim())),
                                      ('y',ax.get_yticks(),ax.get_yticklabels(),sorted(ax.get_ylim()))]:
            texts += [txt for loc,txt in zip(locs,labels) if limits[0]<=loc<=limits[1]]
        for text in texts:
            if not text.get_visible() or not text.get_text():continue
            b=text.get_window_extent(renderer)
            checks.append({'text':text.get_text(),'font_pt':text.get_fontsize(),
                           'inside_canvas':bool(b.x0>=rect.x0-1 and b.y0>=rect.y0-1 and b.x1<=rect.x1+1 and b.y1<=rect.y1+1)})
    for text in fig.texts:
        b=text.get_window_extent(renderer);checks.append({'text':text.get_text(),'font_pt':text.get_fontsize(),
            'inside_canvas':bool(b.x0>=rect.x0-1 and b.y0>=rect.y0-1 and b.x1<=rect.x1+1 and b.y1<=rect.y1+1)})
    overlaps=[]
    for lg in fig.legends:
        lb=lg.get_window_extent(renderer)
        checks.append({'text':'SHARED LEGEND','inside_canvas':bool(lb.x0>=0 and lb.y0>=0 and lb.x1<=rect.x1 and lb.y1<=rect.y1)})
        for txt in fig.texts:
            if lb.overlaps(txt.get_window_extent(renderer)): overlaps.append(txt.get_text())
    (OUT/'reports'/f'{name}_layout.json').write_text(json.dumps({'size_inches':list(fig.get_size_inches()),'font':FONT,'texts':checks,'legend_title_overlaps':overlaps},indent=2))
    plt.close(fig)

def export(fig,name):
    from layout_tools import export_checked
    export_checked(fig,name,OUT)
    plt.close(fig)

from layout_tools import pack as compact_layout, label_percentage
