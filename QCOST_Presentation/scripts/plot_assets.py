#!/usr/bin/env python3
"""Presentation-size scientific assets, derived only from frozen CSV observations."""
from pathlib import Path
import os
ROOT=Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR']=str(ROOT/'validation/mpl_cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from fontTools.ttLib import TTCollection
from matplotlib.patches import Rectangle, ConnectionPatch
import pandas as pd
import numpy as np
import json

font_path=ROOT/'assets/NotoSansCJKSC-Regular.otf'
if not font_path.exists():
    fonts=TTCollection('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    font=next(f for f in fonts.fonts if f['name'].getDebugName(1)=='Noto Sans CJK SC')
    font.save(font_path)
font_manager.fontManager.addfont(str(font_path))

plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Noto Sans CJK SC','DejaVu Sans'],
    'font.size':15,'axes.labelsize':16,'xtick.labelsize':13,'ytick.labelsize':13,
    'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.8,
    'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','axes.unicode_minus':False})
BLUE='#4C72B0';ORANGE='#E76F51';TEAL='#568C82';DARK='#223A5E';GRAY='#858585'
POINT='#8296A6'
P=pd.read_csv(ROOT/'data/FIG2_SPATIAL_POINTS.csv')
L=pd.read_csv(ROOT/'data/FIG2_PARTITION_LINES.csv')
Q=pd.read_csv(ROOT/'data/FIG2_QUERIES.csv')
B=pd.read_csv(ROOT/'data/FIG2_BOUNDS.csv')
C=pd.read_csv(ROOT/'data/FIG2_CASE_CANDIDATES.csv')
assets=ROOT/'assets';assets.mkdir(exist_ok=True)

def save(fig,name):
    for ext in ['svg','pdf','png']:
        fig.savefig(assets/(name+'.'+ext),dpi=300,facecolor='white',bbox_inches='tight',pad_inches=.05)
    plt.close(fig)


def spatial(ax,configuration=None,color=BLUE,scope='full',queries=True):
    bounds=B[B.Scope.eq(scope)].iloc[0]
    ax.scatter(P.X,P.Y,s=1.3,color=POINT,alpha=.3,rasterized=False,linewidths=0)
    if configuration is not None:
        for row in L[L.Configuration.eq(configuration)].itertuples():
            ax.plot([row.X1,row.X2],[row.Y1,row.Y2],color=color,lw=2.5 if row.Depth==0 else 1.25,
                    ls='-' if row.Depth==0 else '--',zorder=3)
    if queries:
        for q in Q.itertuples():
            ax.add_patch(Rectangle((q.XMin,q.YMin),q.XMax-q.XMin,q.YMax-q.YMin,
                fill=False,edgecolor='#424D57',linestyle=':',lw=1.5,zorder=4))
    ax.set_xlim(bounds.XMin,bounds.XMax);ax.set_ylim(bounds.YMin,bounds.YMax)
    if scope=='full' and queries:
        # These real query windows partly extend beyond the node MBR. Show their
        # full extent instead of clipping them into almost invisible fragments.
        xmin=min(bounds.XMin,Q.XMin.min());xmax=max(bounds.XMax,Q.XMax.max())
        ymin=min(bounds.YMin,Q.YMin.min());ymax=max(bounds.YMax,Q.YMax.max())
        dx=(xmax-xmin)*.035;dy=(ymax-ymin)*.035
        ax.set_xlim(xmin-dx,xmax+dx);ax.set_ylim(ymin-dy,ymax+dy)
        for q in Q.itertuples():
            ax.annotate(f'Q{q.QueryID}',((q.XMin+q.XMax)/2,q.YMax),xytext=(0,5),
                textcoords='offset points',ha='center',fontsize=10,color='#424D57')
    ax.set_aspect('equal' if scope=='full' else 'auto')
    ax.set_xlabel('归一化坐标 x');ax.set_ylabel('归一化坐标 y')
    ax.tick_params(length=3)
    ax.xaxis.set_major_locator(plt.MaxNLocator(3));ax.yaxis.set_major_locator(plt.MaxNLocator(4))


# Exact same 20,000 points, query windows, bounds, and seven H3 lines in both views.
for label,rank,color in [('local',0,BLUE),('joint',3,TEAL)]:
    config=int(C[C.Rank.eq(rank)].iloc[0].Configuration)
    fig=plt.figure(figsize=(5.5,3.9));ax=fig.add_axes([.11,.17,.43,.77]);spatial(ax,config,color)
    zoom=fig.add_axes([.70,.23,.25,.62]);spatial(zoom,config,color,scope='10-to-90-point-percentile zoom',queries=False)
    zoom.set_xlabel('x',labelpad=1);zoom.set_ylabel('')
    zoom.set_zorder(3)
    zoom.tick_params(labelsize=10);zoom.xaxis.set_major_formatter(plt.FormatStrFormatter('%.3f'))
    zoom.set_title('同一区域放大',fontsize=13)
    for tick in zoom.get_yticklabels():
        tick.set_bbox(dict(facecolor='white',edgecolor='none',pad=.2))
    b=B.iloc[1]
    ax.add_patch(Rectangle((b.XMin,b.YMin),b.XMax-b.XMin,b.YMax-b.YMin,fill=False,ec=DARK,lw=1.1))
    for y,corner in [(b.YMin,(0,0)),(b.YMax,(0,1))]:
        fig.add_artist(ConnectionPatch((b.XMax,y),corner,coordsA=ax.transData,coordsB=zoom.transAxes,
            color='#AAB3BB',lw=.8,ls='--',clip_on=False,zorder=2))
    save(fig,'spatial_'+label)

fig,ax=plt.subplots(figsize=(5.8,4.0));spatial(ax,None)
save(fig,'real_points_queries')

nodes=pd.read_csv(ROOT/'data/FIG2_COMPARABLE_NODES.csv')
fig,ax=plt.subplots(figsize=(4.5,2.5))
optimal=nodes.RootRegret.eq(0)
ax.scatter(nodes.loc[optimal,'EvaluatedNode'],nodes.loc[optimal,'RootRegret'],marker='s',s=35,c=TEAL)
ax.scatter(nodes.loc[~optimal,'EvaluatedNode'],nodes.loc[~optimal,'RootRegret'],marker='^',s=40,c=ORANGE)
ax.axhline(0,color='#BBC2C9',ls='--',lw=1);ax.set_ylim(bottom=-max(nodes.RootRegret)*.04)
ax.set_xlabel('预定顺序的21个可比较节点',fontsize=12);ax.set_ylabel('根动作成本遗憾',fontsize=12)
ax.tick_params(labelsize=11);fig.tight_layout();save(fig,'motivation_regret')

paired=pd.read_csv(ROOT/'data/FIG3_PAIRED_NODE_TIMES.csv')
main=paired[paired.Primary]
fig,ax=plt.subplots(figsize=(4.5,2.5))
ax.scatter(main.Enumeration_s,main.Recursive_s,c=TEAL,marker='s',s=26)
m=max(main.Enumeration_s.max(),main.Recursive_s.max())*1.05
ax.plot([0,m],[0,m],ls='--',color='#ABB3BB',lw=1);ax.set_xlim(0,m);ax.set_ylim(0,m)
ax.set_xlabel('完整枚举 / s',fontsize=12);ax.set_ylabel('递归精确 / s',fontsize=12);ax.tick_params(labelsize=11)
fig.tight_layout();save(fig,'motivation_exact')

data=pd.read_csv(ROOT/'data/T12_fixed_budget.csv')
fig,ax=plt.subplots(figsize=(4.5,2.5))
q=data[data['方法'].eq('CPU Analytic QMF')].sort_values('预算标签')
for field,color,marker,label in [('配置最优率(%)',BLUE,'^','配置最优'),('根最优率(%)',ORANGE,'s','根动作最优')]:
    ax.plot(q['预算标签'],q[field],marker=marker,color=color,lw=2,label=label)
ax.set_ylim(0,105);ax.set_xscale('log',base=2);ax.set_xticks(q['预算标签']);ax.set_xticklabels(q['预算标签'])
ax.set_xlabel('名义预算',fontsize=12);ax.set_ylabel('最优率 / %',fontsize=12);ax.tick_params(labelsize=11)
ax.legend(fontsize=10,loc='lower right',frameon=False);fig.tight_layout();save(fig,'motivation_hits')
print('Generated 6 scientific assets in PNG, SVG, and vector PDF; no synthetic observations.')
