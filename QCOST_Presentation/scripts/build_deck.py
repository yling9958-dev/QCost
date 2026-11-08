#!/usr/bin/env python3
"""22-slide editable ICDE-style Chinese presentation, with embedded source data."""
from pathlib import Path
import json
import math
import pandas as pd
import numpy as np
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_TICK_MARK, XL_MARKER_STYLE
from pptx.chart.data import CategoryChartData
from pptx.oxml.xmlchemy import OxmlElement
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data';ASSETS=ROOT/'assets'
FONT='Noto Sans CJK SC'
C={'navy':'223A5E','blue':'4C72B0','light':'AFC4DF','orange':'E76F51','text':'263238',
   'gray':'858585','pale':'F4F6F8','line':'D6DFE6','teal':'568C82','orange_pale':'FDF0EA',
   'blue_pale':'EDF3F8','white':'FFFFFF'}
METHOD_COLORS={'Q-COST':C['orange'],'CPU Analytic QMF':C['orange'],'QMF':C['orange'],
    'R4 Greedy':C['blue'],'Recursive Exact':C['teal'],'Recursive Exact H3':C['teal'],
    'Exact':C['teal'],'Random Search':C['gray'],'Random':C['gray'],'Beam Search':'8799B2','Beam':'8799B2',
    'BMTree':'4C72B0','LISA-V2':'91ABC6','Tsunami-CR':'6D8797','Flood-V2':'A68AB7','PostGIS GiST':'C4A36B',
    'Cost-H1':'7B87A5','Exhaustive':'536371','Exact Enumeration':'536371'}
METHOD_COLORS.update({'解析概率':C['blue'],'Aer测量':C['orange']})
DS=['GeoLife','Gowalla','NYC Taxi','Skewed 2D']
T={p.stem:pd.read_csv(p) for p in DATA.glob('T*.csv')}
SYS=T['T03_system_query'];RES=T['T04_system_resources']
HI=json.loads((DATA/'verified_highlights.json').read_text())
SPEED=pd.read_csv(DATA/'speedups.csv')
prs=Presentation();prs.slide_width=Inches(13.333333);prs.slide_height=Inches(7.5)
prs.core_properties.title='Q-COST：研究进展与实验性能汇报'
prs.core_properties.subject='数据库索引成本优化；ICDE研究进展；真实结果汇报'
prs.core_properties.author='[待填写]'
SLIDES=[];CHARTS=[];NATIVE_TABLES=[]

def color(s):return RGBColor.from_string(C.get(s,s).replace('#',''))

def box(slide,x,y,w,h,fill=None,line=None,radius=False,lw=1):
    shape=slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                                  Inches(x),Inches(y),Inches(w),Inches(h))
    if fill:shape.fill.solid();shape.fill.fore_color.rgb=color(fill)
    else:shape.fill.background()
    if line:shape.line.color.rgb=color(line);shape.line.width=Pt(lw)
    else:shape.line.fill.background()
    if radius:
        try:shape.adjustments[0]=.08
        except Exception:pass
    return shape

def text(slide,value,x,y,w,h,size=20,bold=False,fill='text',align='left',margin=.01):
    shape=slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h))
    tf=shape.text_frame;tf.clear();tf.word_wrap=True
    tf.margin_left=tf.margin_right=Inches(margin);tf.margin_top=tf.margin_bottom=Inches(.015)
    for i,line in enumerate(str(value).split('\n')):
        p=tf.paragraphs[0] if i==0 else tf.add_paragraph()
        p.text=line;p.font.name=FONT;p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=color(fill)
        p.alignment={'left':PP_ALIGN.LEFT,'right':PP_ALIGN.RIGHT,'center':PP_ALIGN.CENTER}[align]
        p.space_after=Pt(2);p.space_before=Pt(0);p.line_spacing=1.08
        for run in p.runs:
            ea=OxmlElement('a:ea');ea.set('typeface',FONT);run._r.get_or_add_rPr().append(ea)
    return shape

def line(slide,x1,y1,x2,y2,fill='line',width=1,arrow=False,dashed=False):
    s=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Inches(x1),Inches(y1),Inches(x2),Inches(y2))
    s.line.color.rgb=color(fill);s.line.width=Pt(width)
    if dashed:
        from pptx.enum.dml import MSO_LINE_DASH_STYLE
        s.line.dash_style=MSO_LINE_DASH_STYLE.DASH
    if arrow:
        e=OxmlElement('a:tailEnd');e.set('type','triangle');e.set('w','sm');e.set('len','sm')
        s._element.spPr.find('{http://schemas.openxmlformats.org/drawingml/2006/main}ln').append(e)
    return s

def badge(slide,label,x,y,w=1.5,fill='blue_pale',txt='navy'):
    box(slide,x,y,w,.34,fill=fill,radius=True)
    text(slide,label,x+.05,y+.025,w-.1,.27,12,True,txt,'center')

def make_slide(title,section,source='',takeaway=None,source_y=6.22):
    s=prs.slides.add_slide(prs.slide_layouts[6]);s.background.fill.solid();s.background.fill.fore_color.rgb=color('white')
    n=len(prs.slides)
    box(s,.43,.39,.045,.48,fill='orange')
    text(s,title,.61,.35,11.95,.62,28,True,'navy')
    text(s,section,.62,.10,11,.20,10.5,False,'gray')
    line(s,.48,1.10,12.85,1.10,width=.65)
    text(s,'Q-COST · 研究进展',.5,7.20,5,.2,9.5,False,'gray')
    text(s,f'{n:02d} / 22',11.8,7.18,1.0,.23,10,False,'gray','right')
    if source:text(s,source,.53,source_y,12.2,.40,11.3,False,'gray')
    if takeaway:
        box(s,.5,6.71,12.33,.37,fill='orange_pale',radius=True)
        text(s,takeaway,.66,6.735,12.0,.30,17.5,True,'navy')
    SLIDES.append({'number':n,'title':title,'section':section,'source':source,'takeaway':takeaway or ''})
    return s

def notes(slide,focus,speech,caveat,sources,seconds=35):
    number=len(prs.slides)
    message=f'【本页重点】\n{focus}\n\n【建议讲述：{seconds}秒】\n{speech}\n\n【数据口径】\n{caveat}\n\n【来源】\n{sources}'
    slide.notes_slide.notes_text_frame.text=message
    SLIDES[-1].update({'seconds':seconds,'focus':focus,'speech':speech,'caveat':caveat,'full_sources':sources})

def picture(slide,path,x,y,w,h):
    im=Image.open(path);iw,ih=im.size;ratio=min(w/iw,h/ih);pw=iw*ratio;ph=ih*ratio
    return slide.shapes.add_picture(str(path),Inches(x+(w-pw)/2),Inches(y+(h-ph)/2),width=Inches(pw),height=Inches(ph))

def cell_border(cell,side,fill=None,width=.6):
    tcPr=cell._tc.get_or_add_tcPr();tag='a:ln'+side
    for old in list(tcPr):
        if old.tag==OxmlElement(tag).tag:tcPr.remove(old)
    ln=OxmlElement(tag);ln.set('w',str(int(width*12700)))
    if fill:
        sf=OxmlElement('a:solidFill');cl=OxmlElement('a:srgbClr');cl.set('val',C.get(fill,fill));sf.append(cl);ln.append(sf)
    else:ln.append(OxmlElement('a:noFill'))
    tcPr.append(ln)

def table(slide,headers,rows,x,y,w,h,widths=None,font=16,highlight=None,bold_cells=None,align_first=1):
    shape=slide.shapes.add_table(len(rows)+1,len(headers),Inches(x),Inches(y),Inches(w),Inches(h))
    tb=shape.table
    widths=widths or [1]*len(headers)
    for j,z in enumerate(widths):tb.columns[j].width=Inches(w*z/sum(widths))
    allrows=[headers]+rows
    highlight=highlight or [];bold_cells=bold_cells or set()
    for i,vals in enumerate(allrows):
        tb.rows[i].height=Inches(h/(len(rows)+1))
        for j,v in enumerate(vals):
            cell=tb.cell(i,j);cell.text=str(v);cell.margin_left=Inches(.065);cell.margin_right=Inches(.065)
            cell.margin_top=cell.margin_bottom=Inches(.015);cell.vertical_anchor=MSO_ANCHOR.MIDDLE
            bg='blue_pale' if i==0 else ('orange_pale' if i-1 in highlight else 'white')
            cell.fill.solid();cell.fill.fore_color.rgb=color(bg)
            for p in cell.text_frame.paragraphs:
                p.font.name=FONT;p.font.size=Pt(font if i else max(font,13));p.font.color.rgb=color('navy' if i==0 else 'text')
                p.font.bold=(i==0 or (i-1,j) in bold_cells)
                p.alignment=PP_ALIGN.LEFT if j<align_first else PP_ALIGN.RIGHT
                p.space_after=p.space_before=Pt(0);p.line_spacing=1.0
                for run in p.runs:
                    ea=OxmlElement('a:ea');ea.set('typeface',FONT);run._r.get_or_add_rPr().append(ea)
            for side in ['L','R','T','B']:cell_border(cell,side)
            if i==0:cell_border(cell,'T','navy',1.2);cell_border(cell,'B','navy',.7)
            elif i==len(rows):cell_border(cell,'B','navy',1.2)
    NATIVE_TABLES.append({'slide':len(prs.slides),'headers':headers,'rows':rows,'font':font})
    return tb

def legend(slide,names,x,y,w,font=14):
    lengths=[max(4,len(n)) for n in names];step=w/len(names)
    for i,name in enumerate(names):
        xx=x+i*step
        box(slide,xx,y+.075,.16,.12,fill=METHOD_COLORS.get(name,C['blue']))
        text(slide,name,xx+.23,y,step-.24,.30,font,False,'text')

def chart(slide,categories,series,x,y,w,h,kind='bar',ylabel=None,log=False,ymax=None,
          colors=None,legend_names=None,font=15,percent=False):
    cd=CategoryChartData();cd.categories=categories
    for name,values in series:cd.add_series(name,list(map(float,values)))
    chart_type=XL_CHART_TYPE.COLUMN_CLUSTERED if kind=='bar' else XL_CHART_TYPE.LINE_MARKERS
    ch=slide.shapes.add_chart(chart_type,Inches(x),Inches(y),Inches(w),Inches(h),cd).chart
    ch.has_legend=False;ch.has_title=False
    ch.font.name=FONT;ch.font.size=Pt(font)
    plot=ch.plots[0]
    if kind=='bar':plot.gap_width=60;plot.overlap=0
    for i,(s,(name,values)) in enumerate(zip(ch.series,series)):
        col=(colors[i] if colors else METHOD_COLORS.get(name,C['blue']))
        s.format.fill.solid();s.format.fill.fore_color.rgb=color(col)
        s.format.line.color.rgb=color(col);s.format.line.width=Pt(.55 if kind=='bar' else 2.1)
        if kind!='bar':
            s.marker.style=[XL_MARKER_STYLE.SQUARE,XL_MARKER_STYLE.TRIANGLE,XL_MARKER_STYLE.CIRCLE][i%3]
            s.marker.size=7;s.marker.format.fill.solid();s.marker.format.fill.fore_color.rgb=color(col)
            s.marker.format.line.color.rgb=color(col);s.smooth=False
    ca=ch.category_axis;va=ch.value_axis
    for ax in [ca,va]:
        ax.tick_labels.font.name=FONT;ax.tick_labels.font.size=Pt(font)
        ax.tick_labels.font.color.rgb=color('text');ax.format.line.color.rgb=color('gray')
        ax.format.line.width=Pt(.6);ax.major_tick_mark=XL_TICK_MARK.NONE;ax.minor_tick_mark=XL_TICK_MARK.NONE
    va.has_major_gridlines=True;va.major_gridlines.format.line.color.rgb=color('line');va.major_gridlines.format.line.width=Pt(.6)
    va.tick_labels.number_format='0.##' if log else ('0' if percent else '0.##')
    if log:
        scaling=va._element.find('{http://schemas.openxmlformats.org/drawingml/2006/chart}scaling')
        e=OxmlElement('c:logBase');e.set('val','10');scaling.insert(0,e);va.minimum_scale=.1;va.maximum_scale=1000
    else:va.minimum_scale=0
    if ymax is not None:va.maximum_scale=ymax
    if ylabel:
        va.has_title=True;tf=va.axis_title.text_frame;tf.text=ylabel
        for p in tf.paragraphs:p.font.name=FONT;p.font.size=Pt(font);p.font.color.rgb=color('text')
    if legend_names:legend(slide,legend_names,x+.35,y-.34,w-.5,font=min(font,14))
    CHARTS.append({'slide':len(prs.slides),'categories':list(categories),'series':[(n,list(map(float,v))) for n,v in series],
        'kind':kind,'ylabel':ylabel,'log':log,'ymax':ymax})
    return ch

def node(slide,label,x,y,r=.15,fill='blue_pale',stroke='blue',font=12):
    s=slide.shapes.add_shape(MSO_SHAPE.OVAL,Inches(x-r),Inches(y-r),Inches(2*r),Inches(2*r))
    s.fill.solid();s.fill.fore_color.rgb=color(fill);s.line.color.rgb=color(stroke);s.line.width=Pt(1)
    if label:text(slide,label,x-r,y-r+.02,2*r,2*r-.02,font,False,'navy','center')
    return s

def tree(slide,x,y,w,h,accent='blue',root_label='根',labels=True):
    coords=[(x+w/2,y),(x+w*.25,y+h*.45),(x+w*.75,y+h*.45),
            (x+w*.10,y+h),(x+w*.37,y+h),(x+w*.63,y+h),(x+w*.90,y+h)]
    for p,c in [(0,1),(0,2),(1,3),(1,4),(2,5),(2,6)]:line(slide,*coords[p],*coords[c],fill=accent,width=1.35)
    for i,(xx,yy) in enumerate(coords):node(slide,root_label if i==0 else '',xx,yy,.19 if i==0 else .14,fill='blue_pale',stroke=accent,font=11)
    if labels:text(slide,'叶节点 / 候选点',x,y+h+.24,w,.32,14,False,'gray','center')

def block(slide,title,sub,x,y,w,h,accent='blue',fill='blue_pale',size=20):
    box(slide,x,y,w,h,fill=fill,line=accent,radius=True,lw=1)
    text(slide,title,x+.12,y+.15,w-.24,.55,size,True,accent,'center')
    if sub:text(slide,sub,x+.13,y+.72,w-.26,h-.77,16,False,'text','center')

def small_value(points,ds,method,field):
    d=T['T07_20K' if points==20000 else 'T08_50K']
    return float(d[(d.Dataset==ds)&(d.Method==method)].iloc[0][field+' Mean'])

def official_rows():
    d=T['T13_official_budget'].set_index('方法')
    names=[('Random Search','Random'),('Beam Search','Beam'),('CPU Analytic QMF','QMF'),('Recursive Exact H3','Recursive Exact')]
    return [[short,f'{d.loc[m,"配置最优率(%)"]:.2f}%',f'{d.loc[m,"根最优率(%)"]:.2f}%',f'{d.loc[m,"Root Regret"]:.3f}'] for m,short in names]

# 01
s=make_slide('Q-COST：量子启发式联合子树成本优化','研究进展与实验性能汇报')
text(s,'面向工作负载感知的\n学习型空间索引',.65,1.55,8.0,1.40,34,True,'navy')
text(s,'Q-COST: Quantum-Inspired Cost Optimization of Spatial Trees\nfor Workload-Aware Learned Indexing',.68,3.22,8.45,.91,19,False,'text')
text(s,'研究进展与实验性能汇报',.68,4.45,8,.55,24,False,'blue')
text(s,'汇报人：[待填写]    单位：[待填写]',.68,5.48,8,.40,18,False,'gray')
text(s,HI['presentation_date'],.68,6.03,7,.38,18,False,'gray')
tree(s,9.05,2.27,3.30,2.20,accent='blue',labels=False)
box(s,9.05,5.2,3.3,.7,fill='orange_pale',radius=True)
text(s,'数据 → 成本 → 树结构',9.13,5.38,3.14,.34,18,True,'navy','center')
notes(s,'介绍研究问题与成果范围','今天汇报Q-COST目前的技术主线与实验证据。重点包括亿级数据上的系统查询表现、统一查询内核下的控制实验，以及联合子树优化和有限预算搜索的决策质量。最后介绍门级验证进展与下一步需要补齐的证据。','作者和单位未能从当前论文项目可靠确认，保留可编辑占位；日期按明天2026年10月16日设置。','data/verified_highlights.json；reference_review/STYLE_REVIEW_ZH.md',30)

# 02
s=make_slide('为什么需要优化空间索引？','研究背景','真实点分布：GeoLife冻结20K样本；右侧为可编辑空间树示意。',
    '空间划分质量影响后续查询访问与候选扫描开销。')
text(s,'二维点数据与范围窗口',.65,1.35,5.7,.45,22,True,'navy')
picture(s,ASSETS/'real_points_queries.png',.6,1.9,5.35,3.95)
text(s,'空间划分 → 树结构 → 查询成本',6.6,1.35,6.0,.45,22,True,'navy')
tree(s,7.05,2.35,4.65,1.9,accent='blue')
line(s,5.97,3.65,6.75,3.65,fill='orange',width=2,arrow=True)
badge(s,'亿级二维数据',6.9,5.15,2.4);badge(s,'工作负载感知',9.6,5.15,2.4)
text(s,'访问叶节点 + 扫描候选点',7.05,5.66,5.0,.35,20,True,'orange','center')
notes(s,'从数据库范围查询解释成本来源','空间范围查询需要先通过索引定位相关区域，再过滤候选点。不同划分会改变查询相交的叶节点数量与扫描点数。Q-COST关注构建阶段的空间树决策，让工作负载参与结构选择。左图使用实际GeoLife样本与记录的查询窗口，右图解释树结构与访问成本的关系。','左图全20K实际点；查询窗口是既有案例选取，不代表随机测试工作负载整体。右图仅说明结构，不标性能数字。','data/FIG2_SPATIAL_POINTS.csv；FIG2_QUERIES.csv',30)

# 03
s=make_slide('局部最优划分未必产生最优子树','研究问题 · 真实GeoLife反例','GeoLife节点0，20K点；实线为根，虚线为后代，点线框为查询；两根均配最佳H3延续，成本为代理值。',
    '同一节点上，根动作结合后代成本评价，可得到不同的划分选择。')
text(s,'局部R4首选根',.65,1.30,5.7,.42,23,True,'blue','center')
text(s,'H3联合最优根',6.99,1.30,5.7,.42,23,True,'teal','center')
picture(s,ASSETS/'spatial_local.png',.43,1.85,6.10,3.65)
picture(s,ASSETS/'spatial_joint.png',6.80,1.85,6.10,3.65)
text(s,f'H3成本  {HI["local_case_cost"]:.2f}',.75,5.56,4.5,.5,24,True,'blue')
text(s,f'H3成本  {HI["joint_case_cost"]:.2f}',7.03,5.56,4.5,.5,24,True,'teal')
notes(s,'真实反例展示根动作与后代成本的关系','这个反例来自GeoLife的真实20K根节点。左侧固定R4最偏好的根动作，再为它选择最佳三层延续；右侧同时比较根动作与条件后代。两者使用同一批点和查询，完整H3成本分别为1813.09和1503.44。图中的粗线表示根划分，细虚线表示真实后代划分。','展示的是H3代理成本，不能解释为相同比例的查询延迟下降。两侧均为根条件最优延续，不把左侧称作整棵greedy构建树。局部放大来自相同预定义坐标区间。','data/FIG2_CASE_CANDIDATES.csv；FIG2_PARTITION_LINES.csv；FIG2_GEOMETRY_VALIDATION.csv',40)

# 04
s=make_slide('从单节点决策到联合子树优化','三个研究观察','40主节点；另3个reproduction节点仅用于43组最优成本一致性验证。',
    '研究主线：局部决策依赖 → 条件联合优化 → 预算化根动作选择。')
items=[('01  局部决策偏差','motivation_regret.png','7 / 21','可比较节点中局部根非最优','另19个局部根无法形成完整H3'),
       ('02  条件成本可递归','motivation_exact.png','43 / 43','精确最优成本一致','图中时间配对为40个主节点'),
       ('03  根动作更易命中','motivation_hits.png','95.08%','正式预算QMF根动作最优率','对应配置最优率为65.42%')]
for i,(title,asset,value,caption,note) in enumerate(items):
    x=.5+i*4.18
    text(s,title,x+.05,1.38,3.95,.43,20,True,'navy')
    picture(s,ASSETS/asset,x,2.0,3.98,2.35)
    text(s,value,x+.07,4.62,3.85,.65,36,True,'orange','center')
    text(s,caption,x+.03,5.28,3.98,.35,17,True,'text','center')
    text(s,note,x+.03,5.73,3.98,.33,13,False,'gray','center')
    if i<2:line(s,x+4.07,1.5,x+4.07,5.97,fill='line',width=.8)
notes(s,'用三个有数据支撑的观察串联方法','第一个观察是在21个可比较节点中，7个局部首选根并非H3最优；19个不可行根单独保留。第二个观察是43组节点上递归精确与完整枚举取得相同最优成本。第三个观察是正式预算下，QMF根动作命中率95.08%，明显高于其配置最优率65.42%。这些结果构成从联合建模到根动作提交的研究依据。','43包含3个补充节点；时间图只画40主节点。概率来自40节点×30种子，复用Motivation记录。不能将19不可行记录算为零遗憾。','data/FIG2_ALL40_FEASIBILITY.csv；FIG3_PAIRED_NODE_TIMES.csv；T13_official_budget.csv',35)

# 05
s=make_slide('Q-COST总体技术框架','方法总览 · 根据论文Figure 5重绘','共享工作负载目标；Recursive Exact与CPU QMF是两条可选优化路径。',
    '在构建阶段优化根决策，生成静态空间树；在线采用经典范围查询。')
badge(s,'离线构建',.65,1.40,1.5)
block(s,'输入','数据 D\n查询 Q',.65,2.12,1.60,1.70,accent='blue',size=20)
block(s,'候选生成','冻结R4评分\nTop-K合法动作',2.62,2.12,2.0,1.70,accent='blue',size=20)
block(s,'条件联合子树','祖先划分改变子集\nH层联合配置',5.0,2.12,2.30,1.70,accent='navy',size=20)
block(s,'两项式成本','叶节点访问\n候选点扫描',7.67,2.12,2.0,1.70,accent='blue',size=20)
for x1,x2 in [(2.25,2.62),(4.62,5.0),(7.3,7.67)]:line(s,x1,2.97,x2-.04,2.97,fill='navy',width=1.5,arrow=True)
block(s,'配置优化','Recursive Exact\n或 CPU Analytic QMF',10.05,2.12,2.55,1.70,accent='orange',fill='orange_pale',size=20)
line(s,9.67,2.97,10.01,2.97,fill='navy',width=1.5,arrow=True)
block(s,'只提交根动作','恢复root(z)\n生成左右子节点',8.72,4.43,2.55,1.45,accent='orange',fill='orange_pale',size=20)
line(s,11.32,3.85,11.32,4.10,fill='orange',width=1.5)
line(s,11.32,4.10,10.0,4.10,fill='orange',width=1.5)
line(s,10.,4.1,10.,4.42,fill='orange',width=1.5,arrow=True)
line(s,8.72,4.95,7.60,4.95,fill='blue',width=1.4)
line(s,7.60,4.95,7.60,4.12,fill='blue',width=1.4)
line(s,7.60,4.12,3.61,4.12,fill='blue',width=1.4)
line(s,3.61,4.12,3.61,3.84,fill='blue',width=1.4,arrow=True)
text(s,'子节点重新评分与规划',4.03,4.47,3.37,.35,17,True,'blue','center')
badge(s,'在线服务',.65,4.44,1.50)
text(s,'静态树 → C++ / PostgreSQL\n经典范围计数与候选过滤',.70,5.02,3.6,.83,18,True,'navy')
line(s,8.70,5.76,4.48,5.76,fill='navy',width=1.25,arrow=True)
text(s,'构建完成后保存静态树',4.64,5.87,3.86,.28,13,False,'navy','center')
notes(s,'将方法主线完整呈现且突出两条优化路线','输入包括空间数据和训练查询。冻结R4模型给出合法候选的Top-K排序，随后展开依赖祖先划分的有限深度子树。统一成本只含叶访问和候选扫描两项。配置可由递归精确或CPU解析QMF优化，构建器只提交选中配置的根动作，再对子节点重新规划。最终静态树由经典C++和PostgreSQL路径提供在线查询。','这是论文Figure5的中文演示重绘，未添加训练阶段。共享候选和成本不应包装成相对R4全新加入的功能。完整原Figure5保存在assets/reference。','assets/reference/FIG5_QCOST_PAPER.pdf；QMF冻结实现cost_oracle.py/index.py；data/T18_evidence.csv',40)

# 06
s=make_slide('联合考虑根划分与后代配置','条件联合子树规划 · 根据论文Figure 6重绘','固定一次规划的查询上下文；终端叶成本可加，候选集合依赖条件区域。',
    '祖先划分改变后代数据子集，因此后续候选与最优代价也随之改变。')
box(s,.65,1.55,2.1,2.75,fill='pale',line='line',radius=True)
text(s,'当前区域 S',.76,1.74,1.88,.4,21,True,'navy','center')
tree(s,.95,2.60,1.48,.75,labels=False)
for y,rootlabel,accent in [(1.63,'根动作 a₁','blue'),(3.68,'根动作 a₂','teal')]:
    block(s,rootlabel,'合法候选 Top-K',3.35,y,2.03,1.38,accent=accent,size=21)
    line(s,2.78,2.92,3.30,y+.68,fill=accent,width=1.4,arrow=True)
    for k,yy in enumerate([y-.02,y+.82]):
        box(s,6.12,yy,2.35,.63,fill='blue_pale',line=accent,radius=True)
        text(s,('左子集 S_L(a)' if k==0 else '右子集 S_R(a)'),6.20,yy+.13,2.19,.33,17,True,accent,'center')
        line(s,5.40,y+.66,6.06,yy+.31,fill=accent,width=1.2,arrow=True)
        line(s,8.49,yy+.31,9.15,y+.68,fill=accent,width=1.2,arrow=True)
    block(s,'条件最优成本','Fₕ₋₁(SL) + Fₕ₋₁(SR)',9.20,y,3.27,1.38,accent=accent,size=20)
text(s,'Fₕ(S) = minₐ [ Fₕ₋₁(SL(a)) + Fₕ₋₁(SR(a)) ]',1.03,5.42,11.4,.48,23,True,'navy','center')
text(s,'a ∈ Aₖ(S)；F₀(S) = g(S)，g为终端叶的工作负载成本',1.06,5.93,11.32,.30,16,False,'gray','center')
notes(s,'解释条件依赖与最优子结构','同一个当前区域可以采取不同根划分，各自得到不同的左右子集。子节点的Top-K动作需要在对应条件数据上重新计算，因此不能把后代动作独立于祖先固定。对固定根动作和同一规划查询上下文，两项叶代价可以相加，递归精确由此求每一侧最优，再比较根动作。','递推适用于当前条件可加成本与合法性约束，不是任意空间索引目标。状态S包含条件数据、区域及固定查询上下文；图为方法结构，不含人为设置性能值。','assets/reference/FIG6_PAPER.pdf；data/T17_sensitivity.csv',35)

# 07
s=make_slide('两种联合配置优化机制','优化路线对照','当前CPU QMF先物化完整配置成本表；预算控制搜索选择，不消除经典预计算。',
    'Recursive Exact提供精确最优；QMF研究有限预算下的配置与根动作质量。')
text(s,'Recursive Exact',.8,1.35,5.3,.45,25,True,'teal','center')
text(s,'QMF-Inspired预算搜索',7.0,1.35,5.5,.45,25,True,'orange','center')
left=['按根动作生成条件子问题','递归求左右子树最优','合并成本并恢复最优根']
right=['完整配置成本表 + 初始候选','阈值更新 + BBHT式预算采样','返回已找到的最低成本配置']
for x,seq,accent in [(.9,left,'teal'),(7.1,right,'orange')]:
    for i,label in enumerate(seq):
        y=2.08+i*1.05
        box(s,x,y,5.15,.70,fill='pale',line=accent,radius=True)
        text(s,label,x+.12,y+.16,4.91,.38,20,True,accent,'center')
        if i<2:line(s,x+2.57,y+.74,x+2.57,y+.99,fill=accent,width=1.6,arrow=True)
line(s,6.65,1.5,6.65,5.25,fill='line',width=.8)
text(s,'精确最优 · 利用条件可加结构',.9,5.32,5.15,.40,18,True,'teal','center')
text(s,'有限预算 · 不保证全局最优',7.1,5.32,5.15,.40,18,True,'orange','center')
text(s,'共同目标：C(z) = λleaf · Cleaf(z) + λscan · Cscan(z)',.8,5.82,11.8,.36,21,True,'navy','center')
notes(s,'坦诚比较两条优化路线与实现边界','这两条路线共享候选空间和两项式工作负载成本。递归精确利用条件可加性，能够得到精确解。CPU解析QMF从完整成本表出发，通过阈值更新和预算化搜索选择配置，是量子最小值搜索思想的经典解析实现。当前证据更适合讨论其有限预算决策质量，同时保留递归精确作为强基线。','当前CPU QMF并非QPU、门级线路或O(sqrtN)端到端CPU算法；抽象oracle数量与经典运行时间分开。共享R4候选机制不是相对R4新增的独立贡献。','data/T13_official_budget.csv；T14_phase_costs.csv；既有search.py与cost_oracle.py审计',40)

# 08
s=make_slide('四个亿级空间数据集','实验设置','范围计数：预热300；性能3,000条×5轮；完成组合均通过1,000/1,000正确性检查。',
    '21个完成系统组合提供逐查询证据；失败和缺失组合保留真实状态。')
sizes=['181M','183M','181M','204.99M']
for i,(ds,n) in enumerate(zip(DS,sizes)):
    x=.55+i*3.18;box(s,x,1.37,3.0,1.22,fill='blue_pale',radius=True)
    text(s,ds,x+.12,1.53,2.76,.34,18,True,'navy','center');text(s,n,x+.12,1.96,2.76,.44,28,True,'orange','center')
rows=[['Q-COST','4/4'],['BMTree','4/4'],['LISA-V2','4/4'],['Tsunami-CR','4/4'],['Flood-V2','3/4'],['PostGIS GiST','2/4']]
table(s,['方法','完成数据集'],rows,.65,3.02,5.22,2.74,[3.4,1.6],font=17,highlight=[0])
text(s,'评价指标',6.55,3.06,5.7,.4,22,True,'navy')
text(s,'Mean / P95 / P99 / QPS\nBuild Time / Index Size / Peak Memory',6.55,3.74,5.7,1.0,21,False,'text')
text(s,'同内核控制：20K与50K\n4方法 × 4数据集 × 5构建种子',6.55,5.07,5.7,.82,20,True,'blue')
notes(s,'明确数据规模、指标和完成范围','正式系统实验覆盖四个亿级二维数据集。Q-COST、BMTree、LISA-V2和Tsunami-CR完成了全部四组，Flood和GiST分别完成三组与两组。每个完成索引使用300条预热、3000条性能查询重复五轮，并通过1000条正确性检查。另有160次统一内核的小规模构建，用于更严格地比较构建策略。','Skewed实际204,986,702点，卡片按百万四舍五入。LMSFC部分复现与Boost超时在附录F。QPS由单查询均值换算，不代表并发吞吐量。','data/T01_protocol.csv；T02_status.csv；A05_formal_sources.csv',30)

# 09
s=make_slide('Q-COST在亿级数据上展现较强的查询性能','核心结果一 · 系统级查询比较','系统级prepared range-count；差异包含索引结构与查询内核贡献。加速比由Excel原始精度重算。',
    f'相对BMTree，四个亿级数据集的平均范围计数查询加速为{HI["speedup_min"]:.1f}–{HI["speedup_max"]:.1f}倍。')
methods=['Q-COST','BMTree','LISA-V2','Tsunami-CR']
series=[(m,[float(SYS[(SYS['数据集']==ds)&(SYS['方法']==m)]['Mean(ms)'].iloc[0]) for ds in DS]) for m in methods]
legend(s,methods,.77,1.35,7.00,13)
chart(s,DS,series,.45,1.82,7.45,4.12,ylabel='Mean / ms（对数轴）',log=True,font=14)
rows=[[r.Dataset,f'{r._1:.4f}',f'{r.BMTree_ms:.4f}',f'{r.Speedup:.1f}×'] for r in SPEED.itertuples(index=False)]
table(s,['数据集','Q-COST\n(ms)','BMTree\n(ms)','加速比'],rows,8.02,1.97,4.75,2.75,[1.6,1.05,1.1,1.0],font=15,
      bold_cells={(i,3) for i in range(4)})
text(s,'已完成组合中的\n最低平均查询延迟',8.28,5.05,4.30,.9,24,True,'orange','center')
notes(s,'重点展示亿级系统上的已验证优势','这是本次汇报最主要的系统结果。四个完成数据集上，Q-COST的平均范围计数延迟分别为0.8636、1.3646、0.1601和6.4236毫秒。与BMTree相比，重新计算的加速为34.1、37.6、220.8和10.3倍。左图使用对数轴完整展示数量级差异，右表保留原始均值。','这些是完整系统对比，包括索引结构、整子树count shortcut和候选过滤等实现差异，不能将倍数完全归因于QMF。Mean可能大于P95，长尾可造成该现象。','data/T03_system_query.csv；speedups.csv；00_audit原系统协议',50)

# 10
s=make_slide('与多种空间索引方法的性能比较','核心结果二 · 多基线直接数值','GeoLife与Gowalla拥有六种方法完整查询记录；其余数据集见附录A。QPS=1000/Mean_ms。',
    '相同冻结查询上，Q-COST同时取得较低Mean与P95；比较对象保持实际实现身份。')
for i,ds in enumerate(['GeoLife','Gowalla']):
    x=.55+i*6.36;text(s,ds,x+.02,1.40,6.0,.42,23,True,'navy')
    g=SYS[SYS['数据集']==ds].set_index('方法')
    order=['Q-COST','BMTree','LISA-V2','Tsunami-CR','Flood-V2','PostGIS GiST']
    rows=[[m,f'{g.loc[m,"Mean(ms)"]:.4f}',f'{g.loc[m,"P95(ms)"]:.4f}',f'{g.loc[m,"QPS"]:.2f}'] for m in order]
    table(s,['方法','Mean(ms)','P95(ms)','QPS'],rows,x,2.04,6.0,3.55,[2.1,1.3,1.3,1.15],font=16,highlight=[0],
          bold_cells={(0,j) for j in range(1,4)})
notes(s,'用完整六方法表支持系统结果','这页选择六种实现都有完成记录的GeoLife和Gowalla。橙色行是Q-COST，同时给出Mean、P95和从平均延迟换算的QPS。所有数值来自逐查询计时汇总，而不是从论文或图片估计。NYC和Skewed的完成方法较少，完整七指标和缺失状态放在附录，避免把缺失当作零。','QPS是单查询效率指标。LISA-V2与Tsunami-CR保持当前实现命名，不能默认为作者原始完整系统。所有完整系统差异仍包含内核贡献。','data/T03_system_query.csv；T02_status.csv',35)

# 11
s=make_slide('统一查询内核下的构建性能','核心结果三 · 控制构建策略','50K点；同模型、查询与C++/PostgreSQL内核；每格为5次构建均值。全部COUNT与ID集合验证通过。',
    '现有小规模控制实验中，查询延迟差异较小，联合规划构建开销明显增加。')
methods=['R4 Greedy','Recursive Exact','Q-COST'];legend(s,methods,.91,1.28,11.4,14)
chart(s,DS,[(m,[small_value(50000,ds,m,'Build Time (s)') for ds in DS]) for m in methods],
      .55,1.68,12.2,2.06,ylabel='构建时间 / s',ymax=16,font=14)
text(s,'构建时间 / s',.65,3.90,5.9,.32,18,True,'navy')
text(s,'平均查询延迟 / ms',6.98,3.90,5.8,.32,18,True,'navy')
for field,x,digits in [('Build Time (s)',.65,3),('Mean (ms)',6.98,5)]:
    rows=[[ds]+[f'{small_value(50000,ds,m,field):.{digits}f}' for m in methods] for ds in DS]
    table(s,['数据集','R4','Exact','Q-COST'],rows,x,4.32,5.68,1.72,[1.4,1,1,1.15],font=15,
          bold_cells={(i,1+int(np.argmin([small_value(50000,ds,m,field) for m in methods]))) for i,ds in enumerate(DS)})
notes(s,'解释控制实验与系统对比的区别','为隔离构建策略，我们使用相同R4模型和相同C++查询内核进行50K实验。构建时间中，R4只需约0.6至0.9秒，Recursive Exact约8至11秒，Q-COST约10至14秒。查询均值则集中在0.027至0.031毫秒，差异相对有限。因此当前证据支持系统级优势，但不能把小规模同内核结果描述为显著查询加速。','五个独立构建种子，先统计每个固定索引再取均值；标准差见附带Excel。所有变体root-only，未隔离replanning的独立收益。','data/T08_50K.csv；T07_20K.csv；A04_build_raw.csv',45)

# 12
s=make_slide('QMF提高有限预算下的根动作选择质量','核心结果四 · 正式预算','40节点×30种子；QMF/Random逐节点B=ceil(2√N)；Beam预算机制不同；Exact不受该预算限制。',
    'QMF获得较高的根动作选择质量；Recursive Exact保持100%精确最优参考。')
d=T['T13_official_budget'].set_index('方法');names=['Random Search','Beam Search','CPU Analytic QMF','Recursive Exact H3']
series=[('配置最优率',[d.loc[n,'配置最优率(%)'] for n in names]),('根动作最优率',[d.loc[n,'根最优率(%)'] for n in names])]
chart(s,['Random','Beam','QMF','Exact'],series,.45,1.82,6.38,3.55,ylabel='最优命中率 / %',ymax=100,
      colors=[C['light'],C['orange']],font=15,percent=True)
box(s,.97,1.43,.16,.12,fill='light');text(s,'配置最优率',1.23,1.35,2.2,.30,14)
box(s,3.79,1.43,.16,.12,fill='orange');text(s,'根动作最优率',4.06,1.35,2.4,.30,14)
table(s,['方法','配置最优','根最优','根Regret'],official_rows(),7.0,1.65,5.78,2.74,[1.9,1.3,1.3,1.2],font=15,
      highlight=[2],bold_cells={(3,j) for j in [1,2,3]})
text(s,f'+{HI["configuration_gain_pp"]:.2f}个百分点',7.15,4.70,5.4,.43,25,True,'orange','center')
text(s,'QMF相对Random的配置最优率提升',7.1,5.17,5.5,.34,16,False,'text','center')
text(s,f'根最优率 +{HI["root_gain_pp"]:.2f}个百分点  ·  Root Regret −{HI["root_regret_reduction_pct"]:.1f}%',.86,5.78,11.6,.36,19,True,'navy','center')
notes(s,'区分完整配置命中与根动作命中','正式预算下，QMF完整配置最优率65.42%，根动作最优率95.08%。相比Random，分别提高18.50和5.75个百分点，平均根遗憾降低70.6%。这说明部分未找到全局最优配置的搜索仍能选到最优根动作。右表同时保留Recursive Exact的100%结果，避免把预算策略的质量优势误解为超过精确求解。','QMF/Random每节点30种子，Beam确定性每节点1条；预算的物理计数不等价。精确路线不受预算限制。Regret为代理成本；40节点复用Motivation数据。','data/T13_official_budget.csv；verified_highlights.json',45)

# 13
s=make_slide('搜索预算增加，根动作质量持续改善','核心结果五 · 预算质量曲线','复用第三章40节点；随机方法每节点30种子；仅连接实际预算点。预算按N截断。',
    '预算512时，QMF根动作最优率达到99.67%；完整配置与根动作指标分别统计。')
b=T['T12_fixed_budget'];budgets=[32,64,128,256,512]
def vals(method,field):return [float(b[(b['方法']==method)&(b['预算标签']==v)][field].iloc[0]) for v in budgets]
legend(s,['CPU Analytic QMF','Random Search'],.85,1.31,6.7,14)
for y,field,caption in [(1.84,'配置最优率(%)','配置最优率 / %'),(4.00,'根最优率(%)','根动作最优率 / %')]:
    text(s,caption,.91,y-.10,6.0,.30,16,True,'navy')
    chart(s,[str(v) for v in budgets],[(m,vals(m,field)) for m in ['CPU Analytic QMF','Random Search']],
          .55,y+.20,7.18,1.72,kind='line',ylabel=None,ymax=100,font=14,percent=True)
text(s,'名义搜索预算',2.30,5.95,3.5,.28,13,False,'gray','center')
rows=[[str(v),f'{vals("CPU Analytic QMF","根最优率(%)")[i]:.2f}%',f'{vals("Random Search","根最优率(%)")[i]:.2f}%'] for i,v in enumerate(budgets)]
table(s,['预算','QMF根最优','Random根最优'],rows,8.0,1.85,4.75,3.03,[.85,1.9,1.9],font=16,
      bold_cells={(i,1) for i in range(5)})
text(s,'99.67%',8.22,5.13,4.25,.60,38,True,'orange','center')
text(s,'预算512 · 根动作最优率',8.12,5.79,4.45,.31,16,False,'text','center')
notes(s,'展示已测预算区间内质量变化','从32到512的五个真实预算点上，QMF配置最优率由52.08%提高到94.75%，根动作最优率由87.25%提高到99.67%。Random的根命中率同期由82.42%提高到94.33%。图中的线只连接已测点，不做平滑或补点。这里关注的是搜索质量随预算的变化。','这些记录复用第三章40节点，不是新增独立样本。QMF采用经典完整成本表；更高根命中率不代表端到端量子加速。实际预算受N限制，相同有效预算可能复用同一记录。','data/T12_fixed_budget.csv；A02_budget_CI.csv',35)

# 14
s=make_slide('联合规划深度影响局部成本优化质量','核心结果六 · H/K敏感性','25个共同可行节点；各节点H=1、K=4为基准；热力图与表格均为真实局部精确优化结果。',
    'H=3、K=4使平均局部代理成本下降48.481%，同时增加局部优化时间。')
sen=T['T17_sensitivity']
text(s,'平均代理成本降幅 / %',.8,1.39,6.3,.40,21,True,'navy','center')
text(s,'候选宽度 K',2.54,1.98,3.0,.32,17,False,'text','center')
for j,k in enumerate([2,3,4]):text(s,str(k),1.85+j*1.65,2.40,1.5,.30,18,True,'navy','center')
for i,h in enumerate([1,2,3]):
    text(s,f'H={h}',.67,2.99+i*.90,1.05,.45,18,True,'navy','center')
    for j,k in enumerate([2,3,4]):
        value=float(sen.query('H==@h and K==@k').Improvement_pct.iloc[0]);t=(value+3)/53
        start=np.array([237,243,248]);end=np.array([76,114,176]);rgb=(start*(1-t)+end*t).astype(int)
        fill=''.join(f'{z:02X}' for z in rgb)
        box(s,1.85+j*1.65,2.85+i*.90,1.50,.74,fill=fill,line='orange' if (h,k)==(3,4) else 'white',lw=2 if (h,k)==(3,4) else 1)
        text(s,f'{value:.2f}',1.85+j*1.65,3.03+i*.90,1.5,.38,22,True,'white' if value>28 else 'navy','center')
text(s,'单元格：相对各节点H1/K4的成本变化',.90,5.69,6.1,.35,15,False,'gray','center')
rows=[[str(h),'4',f'{float(sen.query("H==@h and K==4").Improvement_pct.iloc[0]):.3f}%',
       f'{float(sen.query("H==@h and K==4").Total_s.iloc[0]):.6f}'] for h in [1,2,3]]
table(s,['H','K','成本降幅','时间(s)'],rows,7.48,2.10,5.15,2.10,[.45,.45,1.5,1.5],font=18,highlight=[2])
text(s,'48.481%',7.73,4.68,4.65,.70,38,True,'orange','center')
text(s,'局部代理成本改善\n不是实际查询延迟降幅',7.73,5.42,4.65,.70,18,True,'navy','center')
notes(s,'展示联合规划的局部目标价值及代价','为了保持人口一致，敏感性分析取九种H/K设置都可行的25个节点。固定K等于4时，H从1增加到2和3，平均代理成本降幅分别是34.432%和48.481%，对应局部优化时间约0.008、0.062和0.401秒。更深规划确实改善了当前成本目标，同时带来更高计算开销。','降幅是各节点相对自身H1/K4的百分比后再平均。15个节点因至少一种组合不可行而不进入配对均值，不是按性能筛选。不能把代理成本改善解释成查询延迟改善。','data/T17_sensitivity.csv',35)

# 15
s=make_slide('小规模门级实验验证搜索概率模型','门级量子搜索验证 · Qiskit Aer','固定4位成本、单标记态；每个条件5种子×2048 shots。理想Aer门级模拟。',
    '门级测量与同问题解析概率吻合，支持量子线路的功能正确性验证。')
g=T['T16_gate_validation'];chosen=g.loc[g.groupby('N').j.idxmax()].sort_values('N')
legend(s,['解析概率','Aer测量'],.99,1.40,6.32,14)
chart(s,[str(n) for n in chosen.N],[('解析概率',chosen.Theory),('Aer测量',chosen.Measured)],
      .5,1.88,6.55,3.90,kind='line',ylabel='成功概率 / %',ymax=100,colors=[C['blue'],C['orange']],font=15,percent=True)
text(s,'候选规模 N（各点j见右表）',1.35,5.84,4.95,.33,15,False,'gray','center')
rows=[[str(int(r.N)),str(int(r.j)),f'{r.Theory:.3f}%',f'{r.Measured:.3f}%'] for r in chosen.itertuples()]
table(s,['N','j','解析概率','实测概率'],rows,7.5,1.90,5.25,2.88,[.55,.45,1.65,1.65],font=17)
text(s,f'{HI["gate_max_abs_error_pp"]:.3f} 个百分点',7.70,5.01,4.85,.55,28,True,'orange','center')
text(s,'全部13个N/j条件的最大概率偏差',7.58,5.61,5.08,.35,15,False,'text','center')
notes(s,'说明真实门级实验验证了什么','这里使用真实Qiskit Aer执行量子门并测量。选取N等于4、8、16、32和64的已测迭代条件，实测概率与解析值接近。全部13个N/j组合中的最大偏差约0.488个百分点。每个条件包含五个种子、共10240次测量，固定4位成本和单标记态，证明了线路中的相位标记、扩散和测量行为。','不是8位成本实验；不是QPU硬件；不是完整16384配置H3，也不是整套最小值搜索成功率。左图各N的j不同，仅用于解析/实测配对，不声称同j规模趋势。Wilson区间保存在附带Excel。','data/T16_gate_validation.csv；原stage4/8/16/32/stage64_aer结果',35)

# 16
s=make_slide('研究成果与后续工作','主汇报总结','当前证据分别来自完整系统、有限预算局部搜索与代理成本敏感性；适用范围保持区分。',
    '感谢聆听')
cards=[(f'{HI["speedup_min"]:.1f}–{HI["speedup_max"]:.1f}×','亿级系统范围计数加速','相对BMTree；包含查询内核贡献'),
       (f'{HI["qmf_root_hit_pct"]:.2f}%','QMF最优根动作率','40节点×30种子；正式逐节点预算'),
       (f'{HI["HK34_cost_reduction_pct"]:.3f}%','平均局部代理成本改善','25配对节点；H3/K4相对H1/K4')]
for i,(value,title,scope) in enumerate(cards):
    y=1.42+i*1.52;box(s,.65,y,6.40,1.25,fill='orange_pale',radius=True)
    text(s,value,.88,y+.18,3.4,.54,32,True,'orange')
    text(s,title,4.05,y+.20,2.74,.66,18,True,'navy')
    text(s,scope,.90,y+.88,5.90,.29,13,False,'gray')
text(s,'下一步：补齐因果证据与规模证据',7.65,1.50,5.0,.75,23,True,'navy')
nexts=['统一查询内核的大规模验证','Root-only / Full Commit配对消融','利用结构化优化降低构建开销','扩展QMF参数与独立测试节点']
for i,t in enumerate(nexts):
    node(s,'',7.80,2.77+i*.78,.065,fill='orange',stroke='orange')
    text(s,t,8.03,2.57+i*.78,4.75,.60,20,False,'text')
notes(s,'用三个有明确范围的数字结束主汇报','目前最有把握的成果有三类：亿级完整系统的低范围计数延迟；有限预算下较高的根动作命中率；更深联合规划对局部代理成本的改善。与此同时，Recursive Exact是当前非常有竞争力的精确路线。下一步优先补统一内核的大规模实验和提交机制的配对消融，并继续降低构建开销与扩充独立搜索样本。','三个数字来自不同实验层次，不能串成一个端到端因果结论。主汇报结束，后续六页按导师提问选择展示。','data/verified_highlights.json；T18_evidence.csv',30)

# 17 appendix A: all completed system pairs, seven real metrics, editable.
s=make_slide('附录A｜亿级系统七指标完整记录','附录 · 21个完成系统组合','资源列为历史实测口径：构建边界/RSS不同；GiST存储仅索引关系；Flood大小缺失。全部正确性1000/1000。',source_y=6.70)
rows=[];highlight=[]
short={'Recursive Exact':'Exact','PostGIS GiST':'GiST','Tsunami-CR':'Tsunami-CR','Flood-V2':'Flood-V2'}
for ds in DS:
    for m in ['Q-COST','BMTree','LISA-V2','Tsunami-CR','Flood-V2','PostGIS GiST']:
        a=SYS[(SYS['数据集']==ds)&(SYS['方法']==m)]
        if a.empty:continue
        a=a.iloc[0];r=RES[(RES['数据集']==ds)&(RES['方法']==m)].iloc[0]
        if m=='Q-COST':highlight.append(len(rows))
        rows.append([ds,short.get(m,m),f'{r["记录构建(s)"]:.1f}',
            '—' if pd.isna(r['存储(MiB)']) else f'{r["存储(MiB)"]:.1f}',f'{a["Mean(ms)"]:.4f}',
            f'{a["P95(ms)"]:.3f}',f'{a["P99(ms)"]:.3f}',f'{a["QPS"]:.2f}',f'{r["记录峰值(MiB)"]:.1f}'])
table(s,['数据集','方法','构建(s)*','大小(MiB)*','Mean(ms)','P95(ms)','P99(ms)','QPS','峰值(MiB)*'],
      rows,.45,1.38,12.45,5.20,[1.20,1.35,1.02,1.13,1.05,1.08,1.18,.92,1.15],font=12.3,highlight=highlight,align_first=2)
notes(s,'提供系统七指标完整备查表','这一页列出了21个完成组合的七项指标。查询列遵循同一冻结输入和prepared COUNT协议。构建和内存保留原记录，但不同方法边界和进程统计不一致；GiST只记录索引关系大小，而原生保存状态包含点数据。需要比较资源时，应回到统一内核或重新定义统一边界的实验。','仅此完整备查表使用12.3pt；所有文字和数字为原生可编辑表格。失败组合无数值，见附录F。不得直接据资源列宣称构建或内存优劣。','data/T03_system_query.csv；T04_system_resources.csv',45)

# 18 Appendix B: 16 rows, all seven metrics, paired 20K/50K compact units.
s=make_slide('附录B｜20K / 50K统一内核完整结果','附录 · 160次独立构建','单元格为20K / 50K的5构建均值；时延单位μs，QPS单位千次/s；SD与完整精度见附带Excel。')
rows=[];high=[]
for ds in DS:
    for m,label in [('R4 Greedy','R4'),('Cost-H1','Cost-H1'),('Recursive Exact','Exact'),('Q-COST','Q-COST')]:
        if m=='Q-COST':high.append(len(rows))
        def pair(field,mult=1,precision=1):return '/'.join(f'{small_value(n,ds,m,field)*mult:.{precision}f}' for n in [20000,50000])
        rows.append([ds,label,pair('Build Time (s)',precision=2),pair('Index Size (MiB)',1024,1),
            pair('Mean (ms)',1000,2),pair('P95 (ms)',1000,2),pair('P99 (ms)',1000,2),
            pair('QPS',.001,2),pair('Peak Memory (MiB)',1,1)])
table(s,['数据集','方法','构建(s)','大小(KiB)','Mean(μs)','P95(μs)','P99(μs)','QPS(k/s)','峰值(MiB)'],
      rows,.45,1.52,12.45,4.35,[1.20,.95,1.18,1.26,1.26,1.26,1.26,1.26,1.35],font=12.5,highlight=high,align_first=2)
text(s,'全部160次构建均通过COUNT与完整ID集合验证；每个固定索引单独统计时延后再跨构建平均。',.60,5.95,12.0,.34,14,True,'navy')
notes(s,'提供两种规模、四种方法的全部七指标','为在一页内保留完整结果，每个单元格左侧是20K，右侧是50K，均为五次构建平均。时延换算为微秒，存储换算为KiB，QPS按千次每秒表示。所有方法通过COUNT和ID集合验证。这样既可检查构建代价，也能看到同内核查询差异有限以及索引大小接近。','换算只改变单位，不改数值；这不是把不同索引时延混合。跨构建QPS是各索引QPS的平均，因此不必等于平均Mean的倒数。完整SD、median/min/max在Excel。','data/T07_20K.csv；T08_50K.csv；A04_build_raw.csv',45)

# 19 appendix C
s=make_slide('附录C｜搜索质量与真实CPU计算开销','附录 · 40节点正式设置','QMF/Random正式预算随节点变化；Beam宽度不同口径；精确方法不受预算限制。阶段和计入经典预计算。',
    '当前设置下，Recursive Exact取得精确最优，并具有较低的局部CPU优化耗时。')
rows=[]
for m,label in [('Random Search','Random'),('Beam Search','Beam'),('CPU Analytic QMF','CPU QMF'),
                ('Recursive Exact H3','Recursive Exact'),('Exact Enumeration','Exhaustive')]:
    r=T['T13_official_budget'].set_index('方法').loc[m]
    rows.append([label,f'{r["配置最优率(%)"]:.2f}%',f'{r["根最优率(%)"]:.2f}%',f'{r["Root Regret"]:.3f}',
                 f'{r["选择耗时(ms)"]:.4f}',f'{r["阶段和(s)"]:.6f}'])
table(s,['方法','配置最优率','根最优率','Root Regret','选择(ms)','阶段总和(s)'],rows,.65,1.60,12.0,3.13,
      [2.2,1.6,1.6,1.5,1.6,1.9],font=18,highlight=[2],bold_cells={(3,j) for j in [1,2,3,5]})
ratio=1-T['T13_official_budget'].set_index('方法').loc['Recursive Exact H3','阶段和(s)']/T['T13_official_budget'].set_index('方法').loc['CPU Analytic QMF','阶段和(s)']
text(s,f'{100*ratio:.2f}%',.92,5.12,3.0,.60,34,True,'teal')
text(s,'Recursive Exact相对CPU QMF的平均局部时间降低\n精确解与可加结构，是必须保留的经典基线',3.6,5.08,8.6,.90,20,True,'navy')
notes(s,'直接回答QMF与精确经典算法谁更高效','当前CPU实现中，QMF的平均阶段总和约0.425秒，递归精确约0.355秒，后者低约16.38%，并且取得精确最优。QMF本身选择阶段耗时约2.37毫秒，绝大部分时间来自先前经典准备。这个结果说明QMF的独立价值应首先围绕预算质量和未来oracle设计研究，不能声称当前CPU端到端加速。','阶段总和由已测准备与选择相加；不是40节点每个种子全部fresh重跑。Exhaustive选择是已物化成本表argmin，预计算仍计入总和。','data/T13_official_budget.csv；T15_fresh_pipeline.csv',45)

# 20 appendix D
s=make_slide('附录D｜局部优化时间分解','附录 · 经典准备占主要开销','计时单位：秒。QMF排序包含在搜索/选择内；Beam额外项为部分配置trie构建。',
    '优先减少候选评分、条件展开与成本计算，才能实质降低当前CPU构建开销。')
p=T['T14_phase_costs'];rows=[]
for r in p.itertuples(index=False,name=None):rows.append([{'QMF-Inspired (CPU)':'CPU QMF'}.get(r[0],r[0])]+[f'{v:.6f}' for v in r[1:]])
table(s,['方法','R4评分','条件展开','成本评价','搜索/选择','其他实测','合计'],rows,.60,1.55,12.12,3.15,
      [2.05,1.45,1.45,1.45,1.45,1.45,1.45],font=16,highlight=[2])
q=p[p.Method.eq('QMF-Inspired (CPU)')].iloc[0];share=100*q['Search / selection']/q.Total_s
text(s,f'{share:.2f}%',.95,5.05,3.5,.72,42,True,'orange')
text(s,'QMF选择阶段占其阶段总和的比例',4.00,5.15,8.25,.45,23,True,'navy')
text(s,'经典完整成本表已经付费，搜索调用数不能替代端到端时间。',4.00,5.73,8.25,.32,17,False,'gray')
notes(s,'定位当前构建开销的主要来源','分解表显示，各路线的R4评分都在0.249秒左右。递归精确主要减少了条件展开和成本评价，成本评价从完整枚举约0.043秒降到约0.0028秒。CPU QMF选择阶段仅占总和约0.56%。因此近期工程和算法优化应优先关注条件状态组织、评分复用与可加成本评价，而不是只压缩选择控制器。','排序已嵌套计入选择，不重复相加。精确方法各阶段来自同一代表试验；Beam Other是真实trie构建，不是推算残差。','data/T14_phase_costs.csv',40)

# 21 appendix E
s=make_slide('附录E｜H–K完整敏感性与可行性','附录 · 配对局部代理目标','成本与时间：25个共同可行节点；可行数分母：40个主节点。上界K^(2^H−1)不是实际节点配置数。',
    '更宽、更深的规划改善当前局部目标，但可行性与计算成本需同时报告。')
rows=[[str(int(r.H)),str(int(r.K)),f'{int(r.TheoreticalMax):,}',f'{int(r.Feasible_of_40)}/40',
       f'{r.Improvement_pct:.3f}%',f'{r.Total_s:.6f}'] for r in sen.itertuples()]
table(s,['H','K','配置数理论上界','可行节点','代理成本降幅','优化时间(s)'],rows,.85,1.60,11.65,4.26,
      [.6,.6,2.35,1.7,2.35,2.15],font=18,highlight=[8],bold_cells={(8,4)})
notes(s,'补充全部九种H/K组合与不可行情况','这里列出全部九种组合。H3/K2仅25个节点可行，H3/K3为36个，H3/K4为40个。因此主图采用九种组合的25节点交集计算配对成本变化。配置数上界从2增加到16384，实际合法配置受数据和最小叶约束影响。H1小K的负改善也保留，表示相对H1/K4更差。','成本是当前叶访问与扫描代理目标。共同可行节点由合法性筛选，不能称为全部40节点平均。理论配置数不可代替实测时间。','data/T17_sensitivity.csv',35)

# 22 appendix F
s=make_slide('附录F｜实验完整性与下一步补充证据','附录 · 保留失败状态与统计边界','177项历史来源SHA复核一致；本PPT从现有Excel读取，不重跑亿级实验。')
status=T['T02_status'];rows=[]
for r in status.itertuples(index=False,name=None):
    rows.append([r[0]]+[{'完成':'完成','部分复现/有数值':'部分复现','失败/超时':'失败/超时','安全停止':'安全停止','超时':'超时','跳过':'跳过'}.get(v,v) for v in r[1:5]])
table(s,['方法','GeoLife','Gowalla','NYC','Skewed'],rows,.55,1.52,7.18,3.86,[2.45,1.25,1.25,1.25,1.25],font=15,highlight=[0],align_first=1)
text(s,'最优先补充',8.25,1.52,4.40,.42,23,True,'navy')
gaps=['Full Commit / Replanning\n配对消融','统一内核100K / 500K / 1M','统一构建与存储计量边界','独立搜索节点与更大H/K']
for i,t in enumerate(gaps):
    text(s,f'{i+1:02d}',8.25,2.23+i*.85,.55,.40,20,True,'orange')
    text(s,t,8.90,2.23+i*.85,3.85,.65,18,False,'text')
text(s,'LMSFC只作部分复现补充；Boost超时不作零值。缺失实验明确保留，不影响已有真实结果的使用。',.65,5.80,12,.41,17,True,'navy')
notes(s,'完整交代未完成实验与证据补齐顺序','最后这张备查页展示所有方法的完成状态。LMSFC有数值但仍是部分复现，Boost四组超时，Flood和GiST各有缺失组合。后续优先补提交机制配对消融，以及统一内核的100K到1M规模实验，再统一跨方法构建与存储口径。这样可以将当前系统优势、局部优化机制与最终索引效果更严密地连接起来。','未运行与失败不能写0；当前没有QPU或端到端量子加速证据。旧100K/500K/1M实验协议不同，不与20K/50K混接。本输出目录是用户明确授权的新增PPT目录，其余原项目文件只读。','data/T02_status.csv；T06_incomplete.csv；T18_evidence.csv；validation/prior_integrity.csv',40)

assert len(prs.slides)==22
# PowerPoint's default Office theme adds shadows to some native shapes.
# Explicitly clear theme effects so the rendered slides stay flat and white.
for slide in prs.slides:
    for elem in slide._element.iter():
        if elem.tag.endswith('}effectRef'):
            elem.set('idx','0')
    for shape in slide.shapes:
        sppr=shape._element.find('{http://schemas.openxmlformats.org/presentationml/2006/main}spPr')
        if sppr is not None:
            for old in list(sppr):
                if old.tag.endswith('}effectLst') or old.tag.endswith('}effectDag'):
                    sppr.remove(old)
            sppr.append(OxmlElement('a:effectLst'))
out=ROOT/'Q-COST_ICDE_Research_Progress_CN.pptx'
prs.save(out)
(ROOT/'data/native_chart_data.json').write_text(json.dumps(CHARTS,ensure_ascii=False,indent=2))
(ROOT/'data/native_table_data.json').write_text(json.dumps(NATIVE_TABLES,ensure_ascii=False,indent=2))
(ROOT/'notes/slide_manifest.json').write_text(json.dumps(SLIDES,ensure_ascii=False,indent=2))
lines=['# Q-COST逐页讲述稿与数据口径','主汇报建议8–10分钟；附录按提问选择。']
for info in SLIDES:
    lines += [f'## {info["number"]:02d}　{info["title"]}',f'建议时长：{info["seconds"]}秒。',
              '讲述重点：'+info['focus'],info['speech'],'口径：'+info['caveat'],'来源：'+info['full_sources']]
(ROOT/'notes/SPEAKER_NOTES_ZH.md').write_text('\n\n'.join(lines)+'\n')
summary=['|页|内容|建议时长|','|---|---|---|']
summary += [f'|{x["number"]}|{x["title"]}|{x["seconds"]}秒|' for x in SLIDES]
(ROOT/'notes/SLIDE_OUTLINE_ZH.md').write_text('\n'.join(summary)+'\n')
print(json.dumps({'pptx':str(out),'slides':len(prs.slides),'editable_charts':len(CHARTS),'editable_tables':len(NATIVE_TABLES),
    'main_seconds':sum(x['seconds'] for x in SLIDES[:16])},ensure_ascii=False,indent=2))
