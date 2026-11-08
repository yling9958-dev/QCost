"""Section 4.2 typography, renderer packing and export; revised method identity."""
from pathlib import Path
import os,json
OUT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(OUT/'07_reports/mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator,MultipleLocator,FormatStrFormatter
from matplotlib import font_manager
import pandas as pd
import numpy as np
from layout_tools import pack as compact_layout,export_checked
FONT=font_manager.FontProperties(family=['Times New Roman','Liberation Serif','DejaVu Serif']).get_name()
DATASETS=['GeoLife','Gowalla','NYC Taxi','Skewed 2D']
COLORS={'R4 Greedy':'#8F8F8F','Cost-H1':'#8491B4','Original Recursive Exact':'#3C5488',
 'Original Analytic QMF':'#7E6148','Exact Enumeration':'#4D4D4D',
 'Cached Anytime Recursive':'#00A087','Hybrid-QMF':'#E64B35','Hybrid-BestFirst':'#4DBBD5',
 'Hybrid-QMF-NoFeedback':'#F39B35','Random Search':'#8F8F8F','Beam Search':'#8491B4',
 'Anytime Recursive (cache off)':'#4D4D4D'}
MARKERS={'Original Analytic QMF':'o','Random Search':'s','Beam Search':'^',
 'Original Recursive Exact':'s','Cached Anytime Recursive':'D','Hybrid-BestFirst':'^',
 'Hybrid-QMF':'o','Hybrid-QMF-NoFeedback':'v','Anytime Recursive (cache off)':'P'}
SHORT={'Original Recursive Exact':'Recursive Exact','Original Analytic QMF':'Analytic QMF',
 'Cached Anytime Recursive':'Cached Anytime','Hybrid-QMF-NoFeedback':'Hybrid-QMF, no feedback',
 'Anytime Recursive (cache off)':'Recursive, cache off'}
def style():
    plt.rcParams.update({'font.family':FONT,'font.size':11.5,'axes.labelsize':12,
      'xtick.labelsize':11,'ytick.labelsize':11,'legend.fontsize':11,
      'axes.linewidth':.8,'axes.edgecolor':'#4D4D4D','text.color':'#333333',
      'axes.labelcolor':'#333333','xtick.color':'#333333','ytick.color':'#333333',
      'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','savefig.dpi':600,
      'figure.facecolor':'white','axes.facecolor':'white','lines.linewidth':1.6,
      'lines.markersize':5.5,'hatch.linewidth':.45,'mathtext.fontset':'stix','path.simplify':False})
def clean(a,axis='y'):
    a.spines[['top','right']].set_visible(False);a.set_axisbelow(True)
    a.grid(axis=axis,color='#D9D9D9',ls='--',lw=.6);a.tick_params(width=.7,length=3,pad=2)
def panel(fig,ax,label):
    t=fig.text(.5,0,label,fontsize=14.5,weight='bold',ha='center',va='top',wrap=False)
    t.set_gid('panel_title')
    if not hasattr(fig,'_panel_pairs'):fig._panel_pairs=[]
    fig._panel_pairs.append((ax,t));return t
def row_major(items,cols):return [items[i] for c in range(cols) for i in range(c,len(items),cols)]
def legend(fig,items,cols=3,fontsize=11):
    return fig.legend(handles=row_major(items,cols),loc='upper center',bbox_to_anchor=(.5,.995),
        ncol=cols,frameon=False,fontsize=fontsize,handlelength=1.45,handletextpad=.35,
        columnspacing=1.1,labelspacing=.3,borderaxespad=0,borderpad=0)
def method_handles(methods,kind='line'):
    if kind=='bar':return [Patch(facecolor=COLORS[m],edgecolor='#333333',linewidth=.45,label=SHORT.get(m,m)) for m in methods]
    return [Line2D([],[],color=COLORS[m],marker=MARKERS.get(m,'o'),lw=1.7,label=SHORT.get(m,m)) for m in methods]
def read(name):return pd.read_csv(OUT/'02_plot_data'/name,float_precision='round_trip')
def axis_limits(key):return json.loads((OUT/'02_plot_data/ORIGINAL_AXIS_LIMITS.json').read_text())[key]
def export(fig,stem):
    report=[dict(xlim=list(a.get_xlim()),ylim=list(a.get_ylim()),bars=[list(c.datavalues) for c in a.containers if hasattr(c,'datavalues')]) for a in fig.axes]
    (OUT/'07_reports'/f'{stem}_rendered_values.json').write_text(json.dumps(report,indent=2))
    export_checked(fig,stem,OUT);plt.close(fig)
def cierr(g):return np.vstack([g['mean'].to_numpy()-g.ci_low.to_numpy(),g.ci_high.to_numpy()-g['mean'].to_numpy()])

COLORS['Recursive Exact']=COLORS['Original Recursive Exact']
