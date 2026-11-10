"""Renderer-measured, point-based packing for the existing Section 4.2 plots."""
import json
from itertools import combinations
import numpy as np
from matplotlib.transforms import Bbox

TITLE_PT=14.5
PAD_INCHES=.02

def _pt(fig,b):
    k=72/fig.dpi
    return np.array([b.x0,b.y0,b.x1,b.y1])*k

def pack(fig, axes, legends, plot_height_pt, col_gap_pt=6, row_gap_pt=5,
         title_gap_pt=2, legend_gap_pt=3, shared_ylabel=None):
    """Pack using measured decorations, keeping the requested plot height.

    Margins are based on actual tick/label extents, not guessed fractions.
    Each figure supplies its own plot height and inter-panel gaps.
    """
    axes=np.asarray(axes,dtype=object)
    if axes.ndim==1: axes=axes.reshape(1,-1)
    rows,cols=axes.shape; W=fig.get_figwidth()*72
    margin=2.0;ylabel=None
    if shared_ylabel:
        ylabel=fig.text(0,.5,shared_ylabel,rotation=90,ha='center',va='center',fontsize=12)
        ylabel.set_gid('shared_ylabel')
    history=[]
    for iteration in range(12):
        fig.canvas.draw();ren=fig.canvas.get_renderer()
        left=np.zeros(cols);right=np.zeros(cols);above=np.zeros(rows);below=np.zeros(rows)
        for ri in range(rows):
            for ci in range(cols):
                a=axes[ri,ci];ab=_pt(fig,a.get_window_extent(ren));tb=_pt(fig,a.get_tightbbox(ren))
                left[ci]=max(left[ci],ab[0]-tb[0]);right[ci]=max(right[ci],tb[2]-ab[2])
                above[ri]=max(above[ri],tb[3]-ab[3]);below[ri]=max(below[ri],ab[1]-tb[1])
        titles=getattr(fig,'_panel_pairs',[])
        title_h=max((_pt(fig,t.get_window_extent(ren))[3]-_pt(fig,t.get_window_extent(ren))[1] for _,t in titles),default=0)
        legend_h=[_pt(fig,l.get_window_extent(ren))[3]-_pt(fig,l.get_window_extent(ren))[1] for l in legends]
        ylab_w=0 if ylabel is None else _pt(fig,ylabel.get_window_extent(ren))[2]-_pt(fig,ylabel.get_window_extent(ren))[0]+3
        plot_w=(W-2*margin-ylab_w-left.sum()-right.sum()-(cols-1)*col_gap_pt)/cols
        header=sum(legend_h)+max(0,len(legends)-1)*2+legend_gap_pt
        H=2*margin+header+sum(above+below+plot_height_pt+title_gap_pt+title_h)+(rows-1)*row_gap_pt
        old=np.array([fig.get_figheight()*72,*[p for a in axes.flat for p in a.get_position().bounds]])
        fig.set_size_inches(W/72,H/72,forward=True)
        cursor=H-margin
        for lg,lh in zip(legends,legend_h):
            lg.set_bbox_to_anchor((.5,cursor/H),transform=fig.transFigure)
            cursor-=lh+2
        cursor=H-margin-header
        positions={}
        for ri in range(rows):
            top=cursor-above[ri];bottom=top-plot_height_pt
            x=margin+ylab_w
            for ci in range(cols):
                x+=left[ci];a=axes[ri,ci]
                a.set_position([x/W,bottom/H,plot_w/W,plot_height_pt/H]);positions[a]=(x,bottom,plot_w)
                x+=plot_w+right[ci]+col_gap_pt
            for a,t in titles:
                if a in axes[ri,:]:
                    x,_,width=positions[a]
                    t.set_position(((x+width/2)/W,(bottom-below[ri]-title_gap_pt)/H))
                    t.set_ha('center');t.set_va('top');t.set_fontsize(TITLE_PT);t.set_fontweight('bold')
                    t.set_wrap(False)
            cursor=bottom-below[ri]-title_gap_pt-title_h-row_gap_pt
        if ylabel is not None:
            bot=min(a.get_position().y0 for a in axes.flat);top=max(a.get_position().y1 for a in axes.flat)
            ylabel.set_position(((margin+(ylab_w-3)/2)/W,(bot+top)/2))
        new=np.array([H,*[p for a in axes.flat for p in a.get_position().bounds]])
        delta=float(np.max(np.abs(new-old)))
        history.append(dict(iteration=iteration+1,height_pt=H,plot_width_pt=plot_w,
                            left_extents_pt=left.tolist(),right_extents_pt=right.tolist(),
                            upper_extents_pt=above.tolist(),lower_extents_pt=below.tolist(),
                            title_height_pt=title_h,legend_heights_pt=legend_h,change=delta))
        if delta<.02 and iteration>=2:break
    fig.canvas.draw()
    fig._compact_history=history
    fig._compact_params=dict(plot_height_pt=plot_height_pt,col_gap_pt=col_gap_pt,row_gap_pt=row_gap_pt,
        title_gap_pt=title_gap_pt,legend_gap_pt=legend_gap_pt,margin_pt=margin,pad_inches=PAD_INCHES)

def _texts(fig):
    items=[]
    for ai,a in enumerate(fig.axes):
        for label in [a.xaxis.label,a.yaxis.label,a.title]:
            if label.get_visible() and label.get_text():items.append((f'axes{ai}:label',label))
        for axis in ['x','y']:
            locs=getattr(a,'get_'+axis+'ticks')();labels=getattr(a,'get_'+axis+'ticklabels')()
            low,high=sorted(getattr(a,'get_'+axis+'lim')())
            for v,label in zip(locs,labels):
                if low<=v<=high and label.get_visible() and label.get_text():items.append((f'axes{ai}:{axis}tick',label))
        items.extend((f'axes{ai}:annotation',t) for t in a.texts if t.get_visible() and t.get_text())
    items.extend(('figure:'+str(t.get_gid()),t) for t in fig.texts if t.get_visible() and t.get_text())
    return items

def _obstacles(ax):
    """Conservative pixel bounds of real data-line segments and error-bar caps."""
    fig=ax.figure;obs=[]
    for line in ax.lines:
        if not line.get_visible():continue
        points=line.get_transform().transform(line.get_xydata())
        if str(line.get_linestyle()).lower() not in ['none','']:
            for p,q in zip(points[:-1],points[1:]):
                obs.append(Bbox.from_extents(*np.minimum(p,q),*np.maximum(p,q)).padded(1))
        marker=line.get_marker()
        if marker not in [None,'None','none','', ' ']:
            half=line.get_markersize()*fig.dpi/72/2+1
            for p in points:obs.append(Bbox.from_extents(p[0]-half,p[1]-half,p[0]+half,p[1]+half))
    for col in ax.collections:
        if hasattr(col,'get_segments'):
            for s in col.get_segments():
                p=col.get_transform().transform(s)
                if len(p):obs.append(Bbox.from_extents(p[:,0].min(),p[:,1].min(),p[:,0].max(),p[:,1].max()).padded(1))
    return obs

def label_percentage(ax,x,y,low,high,label,color):
    """Place optional S3 text only when it clears actual curves and CIs."""
    fig=ax.figure;fig.canvas.draw();ren=fig.canvas.get_renderer();ab=ax.get_window_extent(ren)
    obs=_obstacles(ax)
    candidates=[((x,high),(0,4),'center','bottom'),((x,low),(0,-4),'center','top'),
                ((x,y),(-30,8),'center','bottom'),((x,y),(-30,-8),'center','top'),
                ((x,y),(-40,12),'center','bottom'),((x,y),(-40,-12),'center','top'),
                ((x,y),(-30,-18),'center','top'),((x,y),(-30,18),'center','bottom')]
    for anchor,offset,ha,va in candidates:
        t=ax.annotate(label,anchor,xytext=offset,textcoords='offset points',ha=ha,va=va,
                      color=color,fontsize=10.5,fontweight='bold',annotation_clip=False)
        t.set_gid('qcost_s3_percentage');fig.canvas.draw();bb=t.get_window_extent(ren)
        inside=bb.x0>=ab.x0+1 and bb.x1<=ab.x1-1 and bb.y0>=ab.y0+1 and bb.y1<=ab.y1-1
        hit=any(bb.padded(1).overlaps(ob) for ob in obs)
        if inside and not hit:
            return dict(text=label,placed=True,anchor=list(anchor),offset_points=list(offset))
        t.remove()
    return dict(text=label,placed=False,reason='No collision-free location within measured axes')

def export_checked(fig,name,out):
    fig.canvas.draw();ren=fig.canvas.get_renderer();items=_texts(fig)
    boxes=[(kind,t,_pt(fig,t.get_window_extent(ren))) for kind,t in items]
    pairs=[]
    for (ka,ta,ba),(kb,tb,bb) in combinations(boxes,2):
        ix=min(ba[2],bb[2])-max(ba[0],bb[0]);iy=min(ba[3],bb[3])-max(ba[1],bb[1])
        if ix>.25 and iy>.25:pairs.append(dict(a=ta.get_text(),b=tb.get_text(),width_pt=ix,height_pt=iy))
    title_checks=[]
    for a,t in getattr(fig,'_panel_pairs',[]):
        ab=_pt(fig,a.get_window_extent(ren));tb=_pt(fig,t.get_window_extent(ren))
        db=_pt(fig,a.get_tightbbox(ren))
        title_checks.append(dict(text=t.get_text(),font_pt=t.get_fontsize(),weight=t.get_fontweight(),
            single_line='\n' not in t.get_text(),center_error_pt=abs((ab[0]+ab[2]-tb[0]-tb[2])/2),
            below_axes=bool(tb[3]<ab[1]),gap_below_axis_decorations_pt=float(db[1]-tb[3]),bbox_pt=tb.tolist()))
    legend_conflicts=[];legends=[]
    for lg in fig.legends:
        lb=_pt(fig,lg.get_window_extent(ren));legends.append(lb.tolist())
        for ai,a in enumerate(fig.axes):
            ab=_pt(fig,a.get_tightbbox(ren))
            if min(lb[2],ab[2])-max(lb[0],ab[0])>.25 and min(lb[3],ab[3])-max(lb[1],ab[1])>.25:
                legend_conflicts.append(f'legend overlaps axes {ai}')
    captions=[t.get_text() for t in fig.texts if t.get_gid() not in ['panel_title','shared_ylabel']]
    # All display text must be on the canvas before applying the final tight crop.
    W,H=fig.get_size_inches()*72
    outside=[t.get_text() for _,t,b in boxes if min(b[0],b[1])<-.3 or b[2]>W+.3 or b[3]>H+.3]
    for b in legends:
        if min(b[0],b[1])<-.3 or b[2]>W+.3 or b[3]>H+.3:outside.append('SHARED LEGEND')
    assert all(c['font_pt']==14.5 and c['weight']=='bold' and c['single_line'] and c['center_error_pt']<.1 and c['below_axes'] for c in title_checks)
    annotation_conflicts=[]
    for ai,a in enumerate(fig.axes):
        for t in a.texts:
            if not t.get_visible():continue
            tb=t.get_window_extent(ren)
            # Bar-height labels and speedups must clear every actual bar rectangle.
            for p in a.patches:
                if tb.overlaps(p.get_window_extent(ren)):
                    annotation_conflicts.append(dict(axes=ai,text=t.get_text(),kind='bar_rectangle'))
            if t.get_gid()=='qcost_s3_percentage':
                if any(tb.padded(1).overlaps(ob) for ob in _obstacles(a)):
                    annotation_conflicts.append(dict(axes=ai,text=t.get_text(),kind='line_or_errorbar'))
    report=dict(font='Times New Roman',canvas_inches=list(fig.get_size_inches()),title_checks=title_checks,
        text_overlaps=pairs,legend_conflicts=legend_conflicts,outside_canvas=outside,
        annotation_data_conflicts=annotation_conflicts,
        extra_figure_captions=captions,legend_boxes_pt=legends,
        text_boxes=[dict(kind=k,text=t.get_text(),font_pt=t.get_fontsize(),bbox_pt=b.tolist()) for k,t,b in boxes],
        layout_iterations=getattr(fig,'_compact_history',[]),layout_parameters=getattr(fig,'_compact_params',{}))
    (out/'07_reports'/f'{name}_compact_layout.json').write_text(json.dumps(report,indent=2))
    assert not pairs and not legend_conflicts and not outside and not captions and not annotation_conflicts,(name,pairs,legend_conflicts,outside,captions,annotation_conflicts)
    tight=fig.get_tightbbox(ren)
    report['exported_inches']=[tight.width+2*PAD_INCHES,tight.height+2*PAD_INCHES]
    for ext in ['pdf','svg','png']:
        fig.savefig(out/'03_figures'/f'{name}.{ext}',dpi=600,facecolor='white',bbox_inches='tight',pad_inches=PAD_INCHES)
    (out/'07_reports'/f'{name}_compact_layout.json').write_text(json.dumps(report,indent=2))

