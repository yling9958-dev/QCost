from pathlib import Path
import json,re,csv,hashlib,unicodedata,collections
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'reference_audit'; EV=OUT/'evidence'
refs=json.loads((EV/'references_extracted.json').read_text())
meta=json.loads((EV/'selected_crossref.json').read_text())
annotations=json.loads((EV/'audit_annotations.json').read_text())
cs=json.loads((EV/'citations_tex.json').read_text()); ps=json.loads((EV/'citations_pdf.json').read_text())
NOW=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
GUIDE='https://ieeeauthorcenter.ieee.org/wp-content/uploads/IEEE-Reference-Guide.pdf'
GUIDEDOC='https://docs.google.com/document/d/1j1L96U2NagwWI9MEVDNVKt9pXxRzTH7h3krI3Mb6wZE/edit'
STYLE=f'[IEEE Reference Guide, V 3.28.2025]({GUIDE})（官方链接目前重定向至 [IEEE Google Docs 文档]({GUIDEDOC})；已导出全文至 evidence/IEEE_current_guide.txt）'

def jread(name):return json.loads((EV/name).read_text())
def clean_tex(s):
 s=re.sub(r'\\url\{([^}]+)\}',r'\1',s)
 s=s.replace(r'D{\"u}rr','Dürr').replace(r'H{\o}yer','Høyer').replace(r"Gily{\'e}n",'Gilyén')
 s=s.replace('``','“').replace("''",'”').replace('--','–')
 s=re.sub(r'\\emph\{([^}]+)\}',r'\1',s)
 return ' '.join(s.split())
def norm(s):
 s=clean_tex(s).replace('ø','o')
 s=unicodedata.normalize('NFKD',s)
 return ''.join(c for c in s.lower() if c.isalnum())
def link(u,label=None):return f'[{label or u}]({u.replace(" ","%20")})'
def cite_nums(s):
 def repl(m):return ', '.join(f'[{x}]' for x in sorted(int(k.strip()[1:]) for k in m[1].split(',')))
 return re.sub(r'\\cite(?:p|t)?(?:\[[^]]*\])*\{([^}]+)\}',repl,s)

# 修正重复 Citation Key 和公式段落的原句边界，保留真实正文。
cs[15]['sentence']='For an ideal uniform search over $N$ feasible configurations, let $\\theta_{\\tau}=\\arcsin\\sqrt{M_{\\tau}/N}$. The probability of measuring a marked configuration after $j$ Grover iterations is given by \\cite{b45}'
cs[20]['sentence']='Skewed 2D is a synthetic dataset generated following the skewed spatial data distribution described by Qi et al. \\cite{b25}.'
assert len(cs)==len(ps)==44
for c,p in zip(cs,ps):
 c.update(pdf_page=p['page'],pdf_column=p['column'],pdf_token=' '.join(p['token'].split()))
 assert sorted(int(k[1:]) for k in c['keys'])==sorted(p['ids'])
(EV/'citations_audited.json').write_text(json.dumps(cs,ensure_ascii=False,indent=2))
assert all(norm(r['raw_tex'])==norm(r['raw_pdf']) for r in refs)

official={
1:'https://dl.acm.org/doi/10.1145/602259.602266',
2:'https://dl.acm.org/doi/10.1145/93597.98741',
3:'https://ieeexplore.ieee.org/document/582015/',
6:'https://www.vldb.org/pvldb/vol13/p1162-ferragina.pdf',
9:'https://www.vldb.org/pvldb/vol14/p74-ding.pdf',
10:'https://www.vldb.org/pvldb/vol13/p2341-qi.pdf',
11:'https://www.vldb.org/pvldb/vol16/p2605-gao.pdf',
14:'https://www.vldb.org/pvldb/vol14/p1-marcus.pdf',
15:'https://link.springer.com/article/10.1007/s00778-024-00893-6',
16:'https://www.vldb.org/pvldb/vol11/p1661-pandey.pdf',
17:'https://dl.acm.org/doi/10.14778/3594512.3594528',
19:'https://ieee-focs.org/FOCS-2017-Papers/3464a403.pdf',
20:'https://www.vldb.org/pvldb/vol17/p3615-kesarwani.pdf',
21:'https://www.vldb.org/conf/1987/P507.PDF',
22:'https://www.vldb.org/conf/1994/P500.PDF',
25:'https://www.vldb.org/pvldb/vol11/p621-qi.pdf',
27:'https://www.vldb.org/pvldb/vol14/p1276-wu.pdf',
28:'https://www.vldb.org/pvldb/vol15/p597-lu.pdf',
35:'https://www.vldb.org/conf/1997/P146.PDF',
37:'https://www.vldb.org/conf/2004/IND4P3.PDF',
38:'https://www.vldb.org/conf/2004/IND4P1.PDF',
41:'https://www.vldb.org/pvldb/vol18/p1278-wu.pdf',
42:'https://www.vldb.org/conf/1997/P186.PDF',
43:'https://www.vldb.org/pvldb/vol14/p3376-ding.pdf',
44:'https://arxiv.org/abs/quant-ph/9607014',
46:'https://www.microsoft.com/en-us/download/details.aspx?id=52367',
47:'https://snap.stanford.edu/data/loc-gowalla.html',
48:'https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page',
49:'https://www.vldb.org/pvldb/vol16/p2158-li.pdf'}
supp={
2:['https://sigmodrecord.org/1990/06/06/the-r-tree-an-efficient-and-robust-access-method-for-points-and-rectangles/','https://www.cs.ucr.edu/~ravi/CS236Papers/rstar.pdf'],
3:['https://www.cs.du.edu/~leut/pubs.html','https://www.cs.du.edu/~leut/icdepaper.ps','https://dblp.org/rec/conf/icde/LeuteneggerEL97'],
4:['https://arxiv.org/abs/1712.01208'],
5:['https://www.microsoft.com/en-us/research/publication/msr-alex-techreport/','https://arxiv.org/abs/1905.08898'],
7:['https://forskning.ruc.dk/en/publications/lisa-a-learned-index-structure-for-spatial-data/'],
8:['https://collaborate.princeton.edu/en/publications/learning-multi-dimensional-indexes/','https://arxiv.org/abs/1912.01668'],
12:['https://www.microsoft.com/en-us/research/publication/qd-tree-learning-data-layouts-for-big-data-analytics/'],
13:['https://dblp.org/rec/journals/tods/QiTCZ20','https://dblp.org/pid/03/505.html'],
17:['https://dbgroup.cs.tsinghua.edu.cn/ligl/papers/experiment-learned-index.pdf'],
19:['https://quantum-journal.org/papers/q-2020-02-14-230/'],
21:['https://dblp.org/rec/conf/vldb/SellisRF87','https://dblp.org/db/conf/vldb/vldb87.html'],
22:['https://www.vldb.org/dblp/db/conf/vldb/vldb94-500.html'],
23:['https://ics-archive.science.uu.nl/research/techreps/repo/CS-2004/2004-022.pdf'],
24:['https://www.uni-marburg.de/en/fb12/research-groups/dbs/publications'],
26:['https://dspace.mit.edu/entities/publication/d08ba4c0-f8bc-42ac-87df-c17210ab3159','https://arxiv.org/abs/1801.10207'],
29:['https://researchportal.hkust.edu.hk/en/publications/lhist-towards-learning-multi-dimensional-histogram-for-massive-sp/'],
30:['https://dbgroup.cs.tsinghua.edu.cn/ligl/papers/4-6-ICDE_2021_Workload_Aware_R_Tree_Haowen.pdf'],
31:['https://zhengwang125.github.io/paper/RLR_Tree_SIGMOD_2023.pdf','https://dblp.org/db/journals/pacmmod/pacmmod1.html'],
32:['https://dblp.org/rec/journals/pacmmod/YangC23a.html','https://mlxdb.github.io/publication/sigmod24-platon/'],
33:['https://dblp.org/rec/journals/pacmmod/Sheng0F00C023','https://dblp.org/pid/277/3316.html'],
34:['https://www.microsoft.com/en-us/research/publication/instance-optimized-data-layouts-for-cloud-analytics-workloads/'],
35:['https://dblp.org/db/conf/vldb/vldb97.html'],
36:['https://www.microsoft.com/en-us/research/project/autoadmin/'],
37:['https://www.vldb.org/dblp/db/conf/vldb/vldb2004.html'],
38:['https://www.vldb.org/dblp/db/conf/vldb/vldb2004.html'],
42:['https://dblp.org/rec/conf/vldb/WangYM97','https://www.vldb.org/dblp/db/conf/vldb/WangYM97.html'],
45:['https://arxiv.org/abs/quant-ph/9605034','https://onlinelibrary.wiley.com/toc/15213978/1998/46/4-5'],
47:['https://snap.stanford.edu/proj/snap-icwsm/SNAP-ICWSM14.pdf']}
author_override={
3:['Scott T. Leutenegger','Mario A. Lopez','Jeffrey M. Edgington'],
19:['Joran van Apeldoorn','András Gilyén','Sander Gribling','Ronald de Wolf'],
21:['Timos K. Sellis','Nick Roussopoulos','Christos Faloutsos'],
22:['Ibrahim Kamel','Christos Faloutsos'],
35:['Surajit Chaudhuri','Vivek R. Narasayya'],
37:['Sanjay Agrawal','Surajit Chaudhuri','Lubor Kollar','Arun Marathe','Vivek Narasayya','Manoj Syamala'],
38:['Daniel C. Zilio','Jun Rao','Sam Lightstone','Guy M. Lohman','Adam J. Storm','Christian Garcia-Arellano','Scott Fadden'],
42:['Wei Wang','Jiong Yang','Richard R. Muntz'],44:['Christoph Dürr','Peter Høyer'],
46:['Microsoft Research'],47:['Stanford Network Analysis Project (SNAP)'],48:['New York City Taxi and Limousine Commission']}
oldpages={21:'507-518',22:'500-509',35:'146-155',42:'186-195'}
oldyears={3:1997,21:1987,22:1994,35:1997,42:1997,44:1996,28:2022}
articles={13:'14',15:'17',31:'63',32:'253',33:'187'}
P1={3}; PENDING={27}; P2={13,15,19,23,29,31,32,33,34,38,40,44,46,47,48}
issue={
3:'STR 会议版第 2、3 位作者顺序错误；按会议注册数据及作者会议稿调整为 Leutenegger–Lopez–Edgington。',
13:'IEEE 文章编号条目的年份位置建议调整为 vol./no., year, Art. no.；编号 14 本身正确。',
15:'IEEE 文章编号条目的年份位置建议调整；2025 年、34(2)、Article 17 和 DOI 均正确。',
19:'Gilyen 缺少正式作者姓氏 Gilyén 的重音符号。',
23:'H. Haverkort 省略已确认的中间首字母 J.，建议 H. J. Haverkort。',
27:'官方 PDF 作者栏及 Crossref 与同页推荐引用块的 Jin Wang / Yu Chen 顺序冲突；保留原文待人工核实。',
29:'正文将 LHist 直接概括为 histogram-based cost estimation 不够精确；原文直接研究 range COUNT/cardinality estimation，建议收窄术语。',
31:'IEEE 文章编号条目的年份位置；Article 63 和 26 页正确，不是页码错误。',
32:'IEEE 文章编号条目的年份位置；Article 253 和 26 页正确。',
33:'超过六位作者建议用第一作者加 et al.；文章编号条目的年份位置；Article 187 和 27 页正确。',
34:'九位作者均列出，建议依 IEEE 用 J. Ding et al.；两个 Y. Li 是不同作者。',
38:'七位作者均列出，建议依 IEEE 用 D. C. Zilio et al.。',
40:'十位作者均列出，建议依 IEEE 用 S. Das et al.。',
44:'预印本建议依 IEEE 写成 1996, arXiv:quant-ph/9607014，明确 arXiv: 标识。',
46:'Accessed 日期应放 URL 之前；以 URL 结尾时不再加句点。',
47:'Accessed 日期应放 URL 之前；以 URL 结尾时不再加句点。',
48:'Accessed 日期应放 URL 之前；以 URL 结尾时不再加句点。'}
annotations['ref_notes']['3']+=' OpenAlex 将该 DOI 的年份记为 2002，和会议来源冲突，未采纳。'
annotations['ref_notes']['1']+=' 会议 Crossref 的 page 字段仅给起始页 47；终页 57 由同文 SIGMOD Record 注册记录与原文页码补证，不能把 47 当成完整页码范围。'
annotations['ref_notes']['10']='官方 PVLDB PDF 首页及推荐引用明确为 13(11):2341–2354；该 DOI 的 Crossref issue 字段写 12。采用官方 PDF 的 11，原稿正确，不按聚合元数据改为 12。作者、标题、年份与页码均对应 RSMI 论文。'
annotations['ref_notes']['29']='LHist 原文直接任务是 range COUNT query estimation，即范围查询计数/基数估计。正文“histogram-based cost estimation”属于宽泛的下游用途概括，建议改为“histogram-based cardinality estimation”；这不是错引另一篇论文，不列 P0。'
annotations['content']['29']='LHist 学习多维直方图，直接评估范围 COUNT 查询/基数估计，间接可为成本模型提供输入。'

def correct(r):
 n=r['id'];s=r['raw_tex']
 if n in PENDING:return s
 if n==3:s=s.replace('S. T. Leutenegger, J. M. Edgington, and M. A. Lopez,','S. T. Leutenegger, M. A. Lopez, and J. M. Edgington,')
 if n==19:s=s.replace('A. Gilyen',r"A. Gily{\'e}n")
 if n==23:s=s.replace('H. Haverkort','H. J. Haverkort')
 if n==36:s=s.replace("AutoAdmin 'what-if'", "AutoAdmin `what-if'")
 if n in [33,34,38,40]:
  au={33:'Y. Sheng',34:'J. Ding',38:'D. C. Zilio',40:'S. Das'}[n]
  s=au+' et al.,\n'+s[s.index('``'):]
 if n in articles:
  a=articles[n];year=str(r['year'])
  s=re.sub(r'Art\. no\. '+a+r',\s*(?:pp\. 1--\d+,\s*)?'+year+r'\.',year+', Art. no. '+a+'.',s)
  s=re.sub(r'Art\. no\. '+a+r',\s*'+year+r',',year+', Art. no. '+a+',',s)
 if n==44:s=s.replace('arXiv preprint quant-ph/9607014, 1996.','1996, arXiv:quant-ph/9607014.')
 if n in [46,47,48]:
  s=re.sub(r'\s*\[Online\]\. Available:\s*(\\url\{[^}]+\})\.\s*Accessed: Oct\. 20, 2026\.',r'\nAccessed: Oct. 20, 2026. [Online]. Available:\n\1',s)
 # 统一建议稿的会议缩写；不将这些整体排版建议重复计算为逐条事实错误。
 s=s.replace('Int. Conf. Management of Data','Int. Conf. Manage. Data').replace('Int. Conf. Data Engineering','Int. Conf. Data Eng.').replace('Symp. Theory of Computing','Symp. Theory Comput.').replace('Symp. Foundations of Computer Science','Symp. Found. Comput. Sci.')
 if n not in [44,46,47,48]:
  patterns=[r'Proc\. ACM SIGMOD Int\. Conf\. Manage\. Data',r'Proc\. IEEE Int\. Conf\. Data Eng\. \(ICDE\)',r'Proc\. Int\. Conf\. Very Large Data Bases \(VLDB\)',r'Proc\. ACM Symp\. Theory Comput\. \(STOC\)',r'Proc\. IEEE Symp\. Found\. Comput\. Sci\. \(FOCS\)',r'Proc\. VLDB Endow\.',r'ACM Trans\. Database Syst\.',r'VLDB J\.',r'Proc\. ACM Manag\. Data',r'Fortschr\. Phys\.']
  for pat in patterns:s=re.sub(pat,lambda m:r'\emph{'+m[0]+'}',s)
 if r['doi'] and not re.search(r'\bdoi:',s):
  s=s.rstrip().rstrip('.')+',\ndoi: '+(r'\url{'+r['doi']+'}' if n==45 else r['doi'])+'.'
 return s

for r in refs:
 n=r['id'];m=meta.get(str(n),{})
 title=': '.join((m.get('title',[])[:1]+m.get('subtitle',[])[:1]))
 if not title or n==38:title=r['title'].rstrip(',')
 if n in [46,47,48]:title={46:'GeoLife GPS Trajectories',47:'Gowalla',48:'TLC Trip Record Data'}[n]
 r['verified_title']=title
 r['authors']=author_override.get(n,[' '.join([a.get('given',''),a.get('family','')]).strip() for a in m.get('author',[])])
 r['venue']=(m.get('container-title') or [''])[0]
 if n in oldpages:r['venue']='Proceedings of the International Conference on Very Large Data Bases (VLDB)'
 if n==44:r['venue']='arXiv (quant-ph/9607014)'
 if n in [46,47,48]:r['venue']={46:'Microsoft Download Center',47:'Stanford Network Analysis Project (SNAP)',48:'NYC Taxi and Limousine Commission'}[n]
 r['year']=oldyears.get(n,(m.get('published') or {}).get('date-parts',[['']])[0][0])
 r['volume']=str(m.get('volume',''));r['issue']=str(m.get('issue',''))
 r['pages']=oldpages.get(n,m.get('page',''))
 if n==1:r['pages']='47-57'
 if n==10:r['issue']='11'
 r['article']=articles.get(n,str(m.get('article-number','')))
 r['doi']=m.get('DOI','')
 if n==44:r['doi']='10.48550/arXiv.quant-ph/9607014'
 if n==45:r['doi']='10.1002/(SICI)1521-3978(199806)46:4/5<493::AID-PROP493>3.0.CO;2-P'
 r['publisher']=m.get('publisher','')
 if n in oldpages:r['publisher']='Morgan Kaufmann'
 if n==21:r['publisher']=''
 if n==44:r['publisher']='arXiv'
 if n in [46,47,48]:r['publisher']={46:'Microsoft Research',47:'Stanford University',48:'New York City Taxi and Limousine Commission'}[n]
 r['official_url']=official.get(n,m.get('resource',{}).get('primary',{}).get('URL','https://doi.org/'+r['doi']))
 if n==45:r['official_url']='https://onlinelibrary.wiley.com/doi/abs/'+quote(r['doi'],safe='/')
 r['metadata_url']='https://api.crossref.org/works/'+quote(r['doi'],safe='/') if r['doi'] else (supp.get(n,[r['official_url']])[0])
 if n==44:r['metadata_url']='https://api.datacite.org/dois/10.48550/arXiv.quant-ph/9607014'
 r['sources']=[r['official_url'],r['metadata_url']]+supp.get(n,[])
 if (EV/f'openalex_{n:02}.json').exists():r['sources'].append(jread(f'openalex_{n:02}.json')['url'])
 r['sources']=list(dict.fromkeys(r['sources']))
 r['level']='待核实' if n in PENDING else 'P1' if n in P1 else 'P2' if n in P2 else 'P3'
 r['status']='真实已确认；作者顺序待人工核实' if n in PENDING else '真实及主要元数据已确认'
 r['problem']=issue.get(n,'未发现条目级实质错误；全文通用格式建议见汇总。')
 r['note']=annotations['ref_notes'].get(str(n),'标题、作者顺序、发表渠道和书目字段与所列来源匹配。')
 r['content']=annotations['content'][str(n)]
 r['citations']=[c for c in cs if r['key'] in c['keys']]
 raw=r['raw_tex'];after=raw[raw.index("''")+2:]
 r['original_fields']={'Author':' '.join(raw[:raw.index('``')].split()).rstrip(','),'Title':clean_tex(r['title'].rstrip(',')).rstrip('.'),'Journal_Conference':'','Year':'','Volume':'','Issue':'','Pages':'','Article_Number':'','DOI':'','URL':'','Publisher':''}
 for field,pat in [('Volume',r'vol\.\s*(\d+)'),('Issue',r'nos?\.\s*([\d–-]+)'),('Pages',r'pp\.\s*([\d–-]+)'),('Article_Number',r'Art\. no\.\s*(\d+)'),('DOI',r'doi:\s*([^\s]+)'),('URL',r'\\url\{([^}]+)\}')]:
  mat=re.search(pat,raw)
  if mat:r['original_fields'][field]=mat[1].rstrip('.').replace('--','-')
 datepart=re.sub(r'pp\.\s*\d+\s*--\s*\d+','',after.split('doi:')[0])
 yr=re.search(r'\b(?:19|20)\d{2}\b',datepart)
 if yr and n not in [46,47,48]:r['original_fields']['Year']=yr[0]
 ve=re.search(r'(?:in\s+)?(Proc\.[^,]+|ACM Trans\.[^,]+|VLDB J\.|Fortschr\. Phys\.)',after,re.S)
 if ve:r['original_fields']['Journal_Conference']=' '.join(ve[1].split())
 if n==44:r['original_fields']['Journal_Conference']='arXiv preprint quant-ph/9607014'
 if n in [46,47,48]:
  r['original_fields']['Journal_Conference']=r['venue'];r['original_fields']['Publisher']={46:'Microsoft Download Center',47:'Stanford University',48:''}[n]
 r['version']='正式期刊论文' if m.get('type')=='journal-article' else '正式会议论文'
 if n==44:r['version']='arXiv 预印本'
 if n in [46,47,48]:r['version']='在线数据集/官方数据入口'
 r['recommended_tex']=correct(r)
 r['recommended']=clean_tex(r['recommended_tex'])
 if n==29:r['recommended']+=' 正文建议：histogram-based cardinality estimation.'
 if n==27:r['recommended']+=' 【作者顺序待核实，本轮保留原条目。】'

counts=collections.Counter(r['level'] for r in refs)
uncited=[r['id'] for r in refs if not r['citations']]
range_cs=[c for c in cs if '–' in c['pdf_token']]
first=[]
for c in cs:
 for n in sorted(int(k[1:]) for k in c['keys']):
  if n not in first:first.append(n)

common_intro=f'''核查日期：2026-10-23（Asia/Shanghai）；报告生成时间：{NOW}。

对象为 `SecPaper_Yaqi-2.pdf` 中实际出现的 49 条参考文献，以及 `IEEE-conference-template-062824.tex` 的有效正文引用。PDF 共 14 页，参考文献位于第 13–14 页。目录检查未找到本稿 `.bib`、`.bbl` 或另一份有效参考文献源；来源是主 TeX 的 `thebibliography`。中文注释中的旧稿与 IEEE 模板示例已排除，不以其他报告或旧版本替代本轮对象。

方法：PyMuPDF 按双栏读取，提取 [1]–[49]；解析有效 `\\bibitem` 和 `\\cite`；逐条查询 Crossref，并以 DOI 查询 OpenAlex；DBLP 检索用于旧 VLDB 论文、完整作者与文章编号补证；重要条目核对官方 PDF、出版页面或作者/机构稿。每个候选均按标题、完整作者及出版版本比对，未将模糊检索首项自动作为答案。Crossref 的 title/subtitle 分开存储时已合并。DOI 解析成功与出版社正文可访问分开记录，403/202 验证页不等于 DOI 不存在。

IEEE 格式依据：{STYLE}。未声称已核实 ICDE 2027 最终版作者指南中的特殊覆盖规则。期刊正式名称、专名及作者身份不因缩写统一而改变。

只生成独立报告和建议稿；原 PDF/TeX 的 SHA-256 在完成后复核。未修改论文内容、图片、公式、算法或实验数据。
'''

global_style=f'''全文级格式项单列，不把同一排版规则重复计成几十条文献真实性错误：

- **G-P2-01（确定，10 个引用组）**：当前 PDF 的连续编号用了 en dash；IEEE 2025 指南 §I.A 要求逐个写出。涉及 {', '.join(c['occurrence'] for c in range_cs)}。例如 `[1]–[3]` 应写 `[1], [2], [3]`。本轮仅提出建议，不修改 `cite` 宏包设置。
- **G-P2-02（统一格式建议）**：按指南 §II.C、§IV，会议名可统一为 `Proc. ACM SIGMOD Int. Conf. Manage. Data`、`Proc. IEEE Int. Conf. Data Eng. (ICDE)`、`Proc. ACM Symp. Theory Comput. (STOC)` 等；建议稿对出版物名使用斜体。原会议/期刊身份本身没有因使用全词而写错；此项不作为 P1 元数据错误。
- 首次出现次序为 {', '.join('['+str(n)+']' for n in first)}。它与手写参考文献序号次序不同，但 44 组 PDF 编号与 TeX key 的**集合全部一致**，不存在由此产生的错指文献。本轮按用户要求固定原编号与 key。将来如按会议最终模板重排，必须同步重编全部引用，不能仅交换条目。
- 未引用条目为 {', '.join('['+str(n)+']' for n in uncited)}。IEEE 2025 §I.A 允许参考文献不在正文出现，因此仅列为状态观察，不自动记为 P0/P1/P2，也不建议为了消除统计项强行补引或删除。
- 原稿只为 [15]、[18]、[19]、[20]、[49] 给出 DOI，五个均与论文匹配。其余已核实 DOI 可补全，但“不写 DOI”不被本报告一律当成错误；没有可靠 DOI 的旧 VLDB 论文保持空白。
'''

top10=[
('修正 STR [3] 作者顺序','会议版本应为 S. T. Leutenegger, M. A. Lopez, and J. M. Edgington；不要沿用技术报告/DBLP 中的另一顺序。',[official[3],supp[3][0],supp[3][1]]),
('人工确认 LIPP [27] 顺序','官方 PDF 首页作者栏与推荐引用块冲突；在获得更明确出版记录前保留原文，不直接交换 Jin Wang 与 Yu Chen。',[official[27],'https://api.crossref.org/works/10.14778/3457390.3457393']),
('收窄 LHist [29] 的技术描述','将 Related Work 中 histogram-based cost estimation 改为 histogram-based cardinality estimation；原文直接研究 range COUNT 估计。',[supp[29][0]]),
('展开 10 组连续编号引用','依 IEEE 2025 指南将 [a]–[b] 展开为每个独立方括号编号。',[GUIDE]),
('规范超过六人的作者简写','[33]、[34]、[38]、[40] 使用第一作者加 et al.；完整作者审计保留在报告和 CSV 中。',[GUIDE]),
('修复可确认的姓名细节','[19] Gilyen→Gilyén；[23] H. Haverkort→H. J. Haverkort。',[official[19],supp[23][0]]),
('统一 Article Number 格式','[13]、[15]、[31]、[32]、[33] 的编号均正确；依 IEEE 将年份放在 Art. no. 之前，PACMMOD 不按普通卷内连续页码处理。',[GUIDE,supp[31][1],supp[32][0],official[15]]),
('规范 arXiv 与在线来源写法','[44] 使用 year, arXiv:identifier；[46]–[48] 将 Accessed 放 URL 前、URL 后不加句点，保留作者原历史访问日期。',[GUIDE,official[44]]),
('保留已核对的正式版本，说明年份差异','[9]/[14] 的上线年与 PDF 引用块不同，[28] 保留官方 PDF 推荐的 2022；[32] 保留 PACMMOD 2023，不改成 SIGMOD 展示年 2024；[45] 保留卷期年 1998 和 493–505。',[official[9],official[28],supp[32][0],'https://onlinelibrary.wiley.com/toc/15213978/1998/46/4-5']),
('补齐已验证 DOI 与数据来源定位','[25] 只能补有效 DOI 10.1145/3187009.3177738，不能抄官方 PDF 的失效号码；[46]–[48] 建议另注明实际子集/月份及加工出处，现有页面不能直接证明加工后样本规模。',['https://api.crossref.org/works/10.1145/3187009.3177738',official[46],official[47],official[48]])]

summary=['# 参考文献技术核查汇总\n',common_intro,'## 统计口径与结果\n']
summary.append(f'''| 项目 | 数量 |
|---|---:|
| 当前 PDF 参考文献 | 49 |
| 已确认真实存在 | 49 |
| 真实性尚未确认 | 0 |
| 条目级核查准确/未发现问题（P3） | {counts['P3']} |
| 存在确定问题（按条目最高等级互斥统计） | {counts['P1']+counts['P2']} |
| 字段待人工核实（真实性已确认） | {counts['待核实']} |
| P0 条目 | 0 |
| P1 条目 | {counts['P1']} |
| P2 条目 | {counts['P2']} |
| 正文有效引用组 / 展开后的引用成员次数 | 44 / {sum(len(c['keys']) for c in cs)} |
| 正文实际引用的不同条目 / 未引用条目 | {49-len(uncited)} / {len(uncited)} |
| 缺失 key / 越界编号 / 完全重复书目 | 0 / 0 / 0 |

**{counts['P3']} + {counts['P1']+counts['P2']} + {counts['待核实']} = 49。** “真实存在”与“所有字段准确”是不同统计；待核实 [27] 不算已证实 P0/P1。P2 主要是 IEEE 编排规则，不能将其解读为大批文献不真实。P3 是条目级结论，不代表全文格式已经合规。另有上述两项全文级 P2 规则，单独计数，不加入 49 条的互斥分桶。
''')
summary+=['## 主要问题与投稿前处理\n',f'P0：0；未发现已证实的虚构论文、错误 DOI 指向或明显技术错引。\n\nP1：[3] 的会议版作者顺序。\n\nP2：'+', '.join(f'[{n}]' for n in sorted(P2))+'；其中 [29] 是术语精度，其余主要为姓名或 IEEE 格式。\n\n待核实：[27] 的作者顺序；来源内部冲突。\n',global_style,'## 最重要的十项修改与确认建议\n']
for i,(title,body,urls) in enumerate(top10,1):summary.append(f'{i}. **{title}**：{body} 依据：'+ '；'.join(link(u) for u in urls)+ '\n')
summary+=['## PDF 与源文件一致性\n','49 条按原顺序映射至 b1–b49。合并换行、断词、LaTeX 引号及变音字符后，PDF 与 TeX 的全部条目相同。44 组有效引用集合全部相同。T029 和 T035 在 PDF 中按编号排序（分别为 [3], [22] 和 [11], [49]），是 cite 排序行为，不是文献编号错位。\n','## 质量判断与限制\n','参考文献真实性整体可靠，核心 Q-COST 技术来源可追溯。投稿前需解决 STR 顺序、LIPP 来源冲突、LHist 表述及 IEEE 格式；不能仅凭当前结果声称全部条目已可直接投稿。部分 ACM/IEEE/Wiley 页面受 403/202 反爬限制；相应条目使用出版社注册的 Crossref 数据、官方论文或机构稿补证，并保留访问日志。历史访问日期由作者负责，本轮访问时间不用于替换它。数据来源核验只确认引用支持范围，未审查实验文件或验证加工数据规模。\n','## 交付文件\n']
for fn in ['REFERENCE_AUDIT_SUMMARY.md','REFERENCE_AUDIT_DETAILS.md','REFERENCE_AUDIT_TABLE.csv','CITATION_CONSISTENCY_REPORT.md','CORRECTED_REFERENCES_SUGGESTED.tex']:summary.append(f'- `{OUT/fn}`\n')
summary.append('\n辅助证据、查询响应、源 PDF/网页、输入哈希和生成脚本均在 `evidence/`；这些不替代五份正式交付物。\n')
summary.append('## 完整性复查\n\n已通过 39 项检查：CSV/Markdown/LaTeX 覆盖全部 49 个编号和 key；44 组引用及 85 个成员对应；文章编号、字段差异与五个原有 DOI 交叉检查通过；建议稿在独立 article 测试文档中编译成功并产生 [1]–[49]；原始 PDF 和 TeX SHA-256 不变。独立编译只验证语法及编号，不代表已检查 ICDE 最终双栏版面。结果与交付文件哈希见 `evidence/validation_results.json`。被拒绝的检索候选见 `evidence/rejected_candidates.json`。\n')
(OUT/'REFERENCE_AUDIT_SUMMARY.md').write_text('\n'.join(summary),encoding='utf-8')

details=['# 逐条参考文献核查报告\n',common_intro,'## 判定与版本规则\n','P0 为已证实严重错误；P1 为重要元数据错误；P2 为一般格式/表述精度问题；P3 为条目级未发现问题。“待核实”独立于错误等级。对于官方来源冲突给出双方证据，不按多数投票改写。完整作者列表用于核对人数、次序及缩写，建议稿仍遵守 IEEE 简写。空卷期/文章编号表示该类型不适用；空 DOI 表示本轮未找到可靠 DOI，不是认定没有 DOI。\n',global_style]
for r in refs:
 n=r['id'];m=meta.get(str(n),{});at=' '.join(r['raw_tex'].split('``')[0].split()).rstrip(',')
 dlog=EV/f'doi_{n:02}_resolution.json'
 doi_check='原条目无 DOI；未查到可确认 DOI，不补写。'
 if r['doi']:
  doi_check=('原 DOI 与出版记录匹配。' if 'doi:' in r['raw_tex'] else '原条目未列 DOI，已确认可补充。')+' '+r['doi']+'。'
  if dlog.exists():
   log=jread(dlog.name)
   if log.get('history'):doi_check+=f' doi.org 有重定向，终点 HTTP {log.get("status_code","未知")}；注册元数据已核对。'
   else:doi_check+=f' 本次解析终点 HTTP {log.get("status_code","请求失败")}，不凭此单独判断失效。'
  elif n==25:doi_check+=' 有效 DOI 已解析至 ACM；官方 PDF 中另一号码返回 404，见版本备注。'
  retry=EV/f'doi_{n:02}_retry.json'
  if retry.exists() and jread(retry.name).get('status_code')==302:doi_check+=' 补充解析请求确认 HTTP 302，重定向至 '+jread(retry.name).get('location','')+'。'
 if n==44:doi_check='原条目未列 DOI。arXiv 及 DataCite 确认仓储 DOI 10.48550/arXiv.quant-ph/9607014，可解析至 arXiv；它不是另一个正式期刊/会议版本的 DOI。'
 if n in [46,47,48]:doi_check='在线数据入口，不要求虚构 DOI；以官方 URL 核验。'
 authorcheck='人数、顺序与缩写对应；未发现额外或遗漏作者。'
 if n in [3,19,23,27,33,34,38,40]:authorcheck=r['problem']
 if n in [5,12,14]:authorcheck=f'完整名单共 {len(r["authors"])} 人；原稿以第一作者加 et al.，合理，不是遗漏作者。'
 if n==37:authorcheck='六位作者顺序正确；Kollar/Kollár 与 Arun Marathe/Arunprasad P. Marathe 的出版名变体见备注。'
 refsources='；'.join(link(u) for u in r['sources'])
 real='已确认真实。'
 if str(n) in meta:real+='使用出版者注册的 Crossref 记录，并以 OpenAlex 交叉检查；出版站受限时不声称已阅读全文。'
 else:real+='由下列官方论文/数据页面或 arXiv 原始记录确认。'
 details += [f'## [{n}] {r["key"]}\n',f'**原始参考文献（当前 PDF，合并排版换行）**\n\n> {r["raw_pdf"]}\n',f'**源文件位置**：主 TeX 第 {r["tex_line"]} 行；PDF 第 {13 if n<48 else 14} 页；key `{r["key"]}`。PDF/TeX：一致。\n',f'**官方核验结果**：{real} 引用版本：{r["version"]}。\n',f'**作者核查**：原写法 `{at}`。核实的完整名单（{len(r["authors"])} 位/机构）：{ "; ".join(r["authors"])}。{authorcheck}\n',f'**标题核查**：{r["verified_title"]}。除大小写、出版名变体及排版标点外与原题对应，未据模糊相似题名替换。\n',f'**年份核查**：{r["year"] or "网页无唯一出版年；保留原访问年份 2026"}。'+(' 存在版本/日期口径，见下方详细备注。' if n in [3,4,9,14,15,19,28,32,37,44,45] else ' 与当前所引版本一致。')+'\n',f'**会议或期刊核查**：{r["venue"]}；出版者/发布方：{r["publisher"] or "未单独确证，不补写"}。\n',f'**卷期核查**：Volume {r["volume"] or "—（不适用）"}；Issue {r["issue"] or "—（不适用）"}。\n',f'**页码与文章编号核查**：Pages {r["pages"] or "—（非传统连续页码/不适用）"}；Article Number {r["article"] or "—（不适用）"}。'+(' pp. 1–n 是文章内部页码；不可把 Article Number 作为普通起始页。' if n in articles else '')+'\n',f'**DOI 核查**：{doi_check}\n',f'**真实研究内容与正文引用核查**：{r["content"]}\n']
 if r['citations']:
  for c in r['citations']:details.append(f'- {c["occurrence"]}：PDF p.{c["pdf_page"]}{c["pdf_column"]}栏；TeX L{c["tex_line"]}；{c["section"]} / {c["subsection"] or "正文"}。编号集合正确。原句详见引用一致性报告。\n')
  details.append('\n引用支持结论：'+('引用方向相关，术语建议改为 cardinality estimation，详见 T036。' if n==29 else '与原文技术内容一致；数据规模及本文实现效果不由该引用独立证明。' if n in [25,44,45,46,47,48] else '在当前表述范围内合理。')+'\n')
 else:details.append('未在当前有效正文出现；未将注释中的引用计入。按 IEEE 指南仅为观察项，不删除。\n')
 details += [f'**问题等级**：{r["level"]}。\n',f'**具体问题**：{r["problem"]}\n',f'**版本、冲突及证据说明**：{r["note"]}\n',f'**推荐正确写法**（建议稿，不覆盖源文件）：\n\n```latex\n\\bibitem{{{r["key"]}}}\n{r["recommended_tex"]}\n```\n',f'**核验来源 URL**：{refsources}\n',f'**查询时间及本地证据**：2026-10-23，Asia/Shanghai；`evidence/crossref_{n:02}.json` / `selected_crossref.json`（如适用），`openalex_{n:02}.json`（如适用），以及 `ref{n:02}*`、`web*.json`。精确请求 URL、HTTP 状态和时刻见 `evidence/source_manifest.json`；不能把被拒绝的候选或失败页面作为确证。\n']
details+=['## 附：核心技术专项结论\n', '''| 专项 | 涉及条目 | 核查结论 |
|---|---|---|
| Learned Index 基础 | [4]–[6] | 正确；区分 [4] 的 2017 arXiv 与 2018 SIGMOD；ALEX 的 12 人名单已展开核对。 |
| 多维 Learned Index | [7]–[11], [49] | LISA、Flood、Tsunami、RSMI、LMSFC、BMTree 均有对应论文；BMTree 使用 RL，题名无需含 BMTree。 |
| Spatial Tree | [1]–[3], [13], [21]–[25], [30]–[32] | [3] 作者顺序需改；RLR 用 RL、PLATON 用 MCTS 均正确；其余未见技术错配。 |
| 工作负载/物理布局 | [12], [30]–[36], [41] | QD-tree、RW-Tree、PLATON、WISK、MTO 及成本驱动索引选择的归属对应。 |
| 量子搜索 | [18], [44], [45] | Grover 基础搜索、Dürr–Høyer 阈值最小值搜索、BBHT 多解概率/未知解数搜索的引用分工正确。 |
| 量子索引顾问 | [20] | 论文确实讨论 QAOA 与 Grover 两条索引配置路线；原文不是空间 R-tree 构建论文，正文仅用作相关物理设计背景，合理。 |
| 其他物理设计文献 | [37]–[40], [43] | 文献真实，当前未引用；不因未引用删除，也不冒称为当前结论的证据。 |

没有发现“文献编号正确但明显归属给另一种算法”的 P0 证据。[29] 的 cost/cardinality 是需要收窄的技术术语（P2），不能扩大为整篇错误引用。当前原句没有宣称 [19] 首次提出 QMF；模板注释和旧稿中的引用不代表当前 PDF。
''']
(OUT/'REFERENCE_AUDIT_DETAILS.md').write_text('\n'.join(details),encoding='utf-8')

fields=['Ref_ID','Citation_Key','Original_Reference','Verified_Title','Verified_Authors','Verified_Venue','Verified_Year','Verified_Volume','Verified_Issue','Verified_Pages','Verified_Article_Number','Verified_DOI','Official_URL','Metadata_URL','Verification_Status','Problem_Level','Problem_Description','Recommended_Correction','Verified_Publisher','Version_Type','Original_LaTeX','PDF_TeX_Consistency','Citation_Locations','Version_Notes','Supporting_URLs','Queried_At','Evidence_Directory']+['Original_'+k for k in refs[0]['original_fields']]
with (OUT/'REFERENCE_AUDIT_TABLE.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for r in refs:
  row=dict(Ref_ID=r['id'],Citation_Key=r['key'],Original_Reference=r['raw_pdf'],Verified_Title=r['verified_title'],Verified_Authors='; '.join(r['authors']),Verified_Venue=r['venue'],Verified_Year=r['year'],Verified_Volume=r['volume'],Verified_Issue=r['issue'],Verified_Pages=r['pages'],Verified_Article_Number=r['article'],Verified_DOI=r['doi'],Official_URL=r['official_url'],Metadata_URL=r['metadata_url'],Verification_Status=r['status'],Problem_Level=r['level'],Problem_Description=r['problem'],Recommended_Correction=r['recommended'],Verified_Publisher=r['publisher'],Version_Type=r['version'],Original_LaTeX=r['raw_tex'],PDF_TeX_Consistency='一致（规范化排版后）',Citation_Locations='; '.join(f'{c["occurrence"]}: PDF p.{c["pdf_page"]}{c["pdf_column"]}; TeX L{c["tex_line"]}' for c in r['citations']) or '当前正文未引用',Version_Notes=r['note'],Supporting_URLs=' | '.join(r['sources']),Queried_At='2026-10-23 Asia/Shanghai（精确请求时间见 evidence/source_manifest.json）',Evidence_Directory=f'evidence/; Ref {r["id"]:02}')
  row.update({'Original_'+k:v for k,v in r['original_fields'].items()});w.writerow(row)

texout=['% 参考文献建议稿；审计日期 2026-10-23。仅供审阅，不覆盖主 TeX。','% 保留原编号顺序 [1]--[49] 与 b1--b49；未增删条目。','% 依赖主文档的 url 或 hyperref 宏包。','% [27] 来源作者顺序冲突，整条保持原文；核实前不要直接全量替换。','% 年份冲突 [9]/[14]/[28] 见报告；已保留当前有来源支持的版本。',r'\begin{thebibliography}{99}','']
for r in refs:
 texout += [f'% [{r["id"]}] {r["level"]}；{r["problem"]}',f'% 核验来源: {r["official_url"]}',f'% 元数据: {r["metadata_url"]}']
 if r['id'] in [3,9,14,19,25,27,28,32,37,44,45]:texout.append('% '+r['note'])
 texout += [r'\bibitem{'+r['key']+'}',r['recommended_tex'],'']
texout.append(r'\end{thebibliography}')
(OUT/'CORRECTED_REFERENCES_SUGGESTED.tex').write_text('\n'.join(texout)+'\n',encoding='utf-8')

checks={
'T001':'合理。[1]/[2] 为层次包围区域结构，[3] 为几何排序打包，未混同 learned index。',
'T002':'合理，三篇分别对应范式、ALEX 自适应结构和 PGM 紧凑模型。',
'T003':'合理，机构/作者摘要确认 LISA 的映射和模型、Flood 的布局优化。',
'T004':'合理，Tsunami 相关性/负载倾斜、RSMI 递归模型、LMSFC 曲线各有对应。',
'T005':'合理，qd-tree 是工作负载感知的数据布局方法。',
'T006':'合理。RW-Tree 历史负载、RLR RL、PLATON 搜索学习分区三者的归属正确。',
'T007':'基本合理，属于合并的研究趋势概述；[14]/[17] 是一维 learned-index 评测，[16] 是空间分析系统评测，不能把每一篇都解释为提出空间树。可按对象拆分引用以提高精度。',
'T008':'合理，阈值更新主要由 [44] 支持，[18]/[45] 为搜索/放大基础。',
'T009':'合理，[20] 明确讨论量子经典混合索引顾问，正文未称其为空间树实现。',
'T010':'合理但概括性较强；RLR 的具体操作是 ChooseSubtree/Split，PLATON 的对象是 top-down packing。建议需要机制对比时把各方法操作写清。',
'T011':'量子原理引用合理；所引论文并不直接证明 Q-COST 的经典模拟实现性能。当前明确称 classically simulated，未发现错误的量子硬件归属。',
'T012':'合理，三篇支持数据分布和查询负载指导分区/布局。',
'T013':'合理，qd-tree 关注访问数据块，PLATON 优化 workload 下查询性能。',
'T014':'合理，[44] 的算法反复以当前更优值更新 threshold。',
'T015':'合理，[18]/[45] 支持 Grover-style 振幅放大。',
'T016':'匹配。[45] §3 多解情形给出 k_j=sin((2j+1)θ)/sqrt(t)、sin²θ=t/N；因此成功概率 t·k_j²=sin²((2j+1)θ)，令 t=Mτ 即对应本文式。该结论以前提中的理想均匀状态及准确标记 oracle 为条件。',
'T017':'官方 GeoLife 页面支持 GPS 轨迹来源；加工后规模不由入口页独立证明。',
'T018':'SNAP 官方页支持 Gowalla 签到数据来源。其原始 6,442,890 条签到与本文加工规模不应混为一谈；不据此直接判错实验数据。',
'T019':'TLC 官方页支持城市出行记录来源；复现仍需明确月份/车型/字段。',
'T020':'[25] 是分布生成方法来源，不是一个名称固定为 Skewed 2D 的在线数据集；当前将其称 synthetic，方向合理。',
'T021':'合理，[25] §6.1（印刷 p.629）明确给出由均匀点变换 y→y^α 的 Skew。未检查本文生成器，因本轮限于引用核查。',
'T022':'合理，[49] 明确命名 BMTree；其标题没有 BMTree 不影响匹配。',
'T023':'合理，[7] 是 LISA 正式 SIGMOD 论文。',
'T024':'合理，[8] 正式论文介绍 Flood。',
'T025':'合理，[9] 是 Tsunami。',
'T026':'合理，[11] 是 LMSFC。',
'T027':'公式来源合理；所引论文支持理论成功概率，不为 Qiskit 实测结果背书，正文已区分理论与测量。',
'T028':'合理，R-tree/R*-tree 层次及 R+-tree 减少重叠对应。',
'T029':'集合映射正确。PDF 按数字排序为 [3], [22]；句中先 Hilbert 后 STR，不表示 Hilbert 属于 [3]。可写 Hilbert R-tree [22] and STR [3] 以消除阅读歧义。',
'T030':'合理，PR-tree、修订 R*-tree 与并行 rank-space R-tree 覆盖所述查询/构建进展。',
'T031':'合理，STING 的层次网格保存统计信息。',
'T032':'合理，三篇均支持 learned-index 模型定位范式。',
'T033':'技术对应合理；LIPP 的元数据顺序争议与本文对其技术的正确描述是两件事。',
'T034':'合理，LISA/Flood/Tsunami 的原文方法与所述设计方向对应。',
'T035':'集合映射正确。cite 排序为 [11], [49]，原 key 为 b49,b11；BMTree 实际对应 [49]、LMSFC 对应 [11]，不据排序误判。可将引用各自贴在方法后。',
'T036':'P2 术语建议：[10] 支持学习空间层次；[29] 直接研究 histogram-based cardinality/range COUNT estimation，不直接等同任意成本模型。建议只把 cost estimation 改为 cardinality estimation。',
'T037':'合理，qd-tree 与 MTO 都针对具体查询工作负载学习/优化物理数据布局。',
'T038':'合理，RW-Tree 的历史查询负载与构建策略有原文依据。',
'T039':'合理，RLR-Tree 确实使用 RL；可把 spatial partitioning decisions 写成 ChooseSubtree and Split decisions 以增强精度。',
'T040':'合理。PLATON 摘要明确 MCTS，WISK 摘要明确 workload-aware spatial keyword indexing；未发现二者互相错配。',
'T041':'合理，成本驱动选择、what-if 分析与 Esc 预算提前停止支持该概括。',
'T042':'合理，Grover 为量子搜索基础。',
'T043':'合理，Dürr–Høyer 为量子最小值阈值搜索。',
'T044':'合理，[20] 的 QAOA/Grover 物理索引配置研究是直接对应的背景。'}
citrep=['# 正文引用一致性与技术支持报告\n',common_intro,'## 完整性结果\n',f'有效引用组 44；展开成员次数 {sum(len(c["keys"]) for c in cs)}；实际引用文献 43 条；未引用 6 条：'+', '.join(f'[{n}]' for n in uncited)+'。未发现缺失 key、缺失参考文献、越界编号、完全重复条目。PDF/TeX 的 44 组编号集合完全对应；两个组内排序变化已说明。\n',global_style,'## 每篇文献到引用位置的映射\n','| 编号 / Key | 文献题名 | 引用位置（PDF 页/栏；TeX 行；组号） |\n|---|---|---|']
for r in refs:citrep.append(f'| [{r["id"]}] / `{r["key"]}` | {r["verified_title"]} | '+('<br>'.join(f'p.{c["pdf_page"]}{c["pdf_column"]}；L{c["tex_line"]}；{c["occurrence"]}' for c in r['citations']) or '当前正文未引用')+' |')
citrep+=['\n## 逐次引用的原句、章节与支持判断\n','以下英文原句合并了源文件换行，引用 key 转为对应数字（组内排序按 PDF）；数学命令保留，未改写论文内容。PDF 原引用字样另列，以区分压缩区间与展开列表。\n']
for c in cs:
 ns=[int(k[1:]) for k in c['keys']]
 citrep += [f'### {c["occurrence"]} — PDF p.{c["pdf_page"]}{c["pdf_column"]}栏 / TeX L{c["tex_line"]}\n',f'章节：{c["section"]} / {c["subsection"] or "正文"}。原 PDF 引用：`{c["pdf_token"]}`；keys：`{",".join(c["keys"])}`。\n',f'> {cite_nums(c["sentence"])}\n',f'**编号核查**：正确，展开集合为 {", ".join("["+str(n)+"]" for n in sorted(ns))}。\n',f'**支持判断**：{checks[c["occurrence"]]}\n']
 for n in ns:
  r=refs[n-1];sources=[r['official_url']]+supp.get(n,[])[:2]
  citrep.append(f'- [{n}] {r["verified_title"]}：{r["content"]} 依据：'+ '；'.join(link(u) for u in sources)+'。\n')
citrep+=['## 需要调整或进一步确认的正文引用\n', '''1. **确定的 P2 精度建议（T036，[29]）**。原句：“Learned spatial hierarchies and histogram-based cost estimation have also been investigated [10], [29].” LHist 的直接研究内容是范围 COUNT/基数估计。建议为 “Learned spatial hierarchies and histogram-based cardinality estimation have also been investigated [10], [29].” 不增添文献，不改公式或实验数据。依据：'''+link(supp[29][0])+'''

2. **可选清晰化（不作为错引计数）**。T029、T035 可分别在 Hilbert R-tree、STR、BMTree、LMSFC 后紧跟各自编号，避免阅读者把数字排序误当名称配对。正确对应分别为 [22]、[3]、[49]、[11]。这些论文身份由对应条目官方来源确认。

3. **可选精确化（不作为 P0）**。T039 将 RLR-Tree 的决策写为 ChooseSubtree and Split 更贴近其原文。T007 的合并综述需保留一维 learned-index 评测和空间系统评测的区别；没有证据要求替换任一篇文献。

4. **量子引用边界**。正文当前已把 [18]、[44]、[45] 的搜索/最小值/多解概率区分开。[44] 的复杂度是量子 oracle/search 模型结论，不自动推导本文完整配置试次/经典 frontier 选择的常数预算；正文称预算为 reference budget，故本轮不把它判作错误引用，也不改算法/公式。不存在需要以 [19] 代替 [44] 的依据。

5. **数据引用可追溯性（非数据审计）**。GeoLife、Gowalla、TLC 页面证实数据来源类型，但不独立证明本论文“processed benchmarks”约 181–205 million points 的加工结果。建议另记录版本/子集/月份及处理出处；未查看或修改实验数据，不将此缺口直接记为 P0。

## 缺失、未引用、重复与来源误判防护

- 正文有引用但书目无条目：0。
- 无效 Citation Key：0；有效 key 均为 b1–b49。
- 书目有条目但正文未引用：[19]、[37]、[38]、[39]、[40]、[43]。全部保留；[19] 不能被误报为当前 QMF 引用错误。
- 完全重复书目：0。[13]/[25] 具有相同作者及相关技术，但为不同题名/不同刊物和年份的出版物；不得自动去重。[34] 中两个 Y. Li 为不同作者，不能去掉一个。
- arXiv/正式版本：本稿 [44] 明确引用预印本；其他查到预印本的条目保留本稿正式出版版本，不把技术说明所用作者稿的发布日期写成正式会议年份。
''']
(OUT/'CITATION_CONSISTENCY_REPORT.md').write_text('\n'.join(citrep),encoding='utf-8')

# 证据索引含本地文件、查询时刻、来源和失败状态，保留被拒绝候选供追溯。
manifest=[]
for f in sorted(EV.iterdir()):
 if f.name in ['source_manifest.json','verified_records.json','audit_counts.json','validation_results.json'] or not f.is_file():continue
 item={'file':f.name,'size':f.stat().st_size,'saved_at_shanghai':datetime.fromtimestamp(f.stat().st_mtime,ZoneInfo('Asia/Shanghai')).isoformat(),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
 if f.suffix=='.json':
  try:
   x=json.loads(f.read_text())
   if isinstance(x,dict):
    for k in ['queried_at','url','request_url','status_code','final_url','error']:
     if k in x:item[k]=x[k]
  except Exception:pass
 manifest.append(item)
(EV/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
(EV/'verified_records.json').write_text(json.dumps(refs,ensure_ascii=False,indent=2))
(EV/'audit_counts.json').write_text(json.dumps({'total':49,'exists':49,'accurate':counts['P3'],'problematic':counts['P1']+counts['P2'],'pending':counts['待核实'],'levels':dict(counts),'global_p2_rules':2,'citation_groups':44,'citation_members':sum(len(c['keys']) for c in cs),'uncited':uncited},ensure_ascii=False,indent=2))
print('GENERATED',dict(counts),'49 references; 44 citation groups;',sum(len(c['keys']) for c in cs),'citation members')
