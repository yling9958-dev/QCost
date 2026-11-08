from pathlib import Path
import re,json,csv,hashlib,collections
import pymupdf
P=Path(__file__).resolve().parent.parent; E=P/'evidence'; R=P.parent
refs=json.loads((E/'verified_records.json').read_text())
expected=[r['id'] for r in refs];keys=[r['key'] for r in refs]
results=[]
def check(name,condition):
 results.append({'check':name,'passed':bool(condition)})
 if not condition:raise AssertionError(name)
rows=list(csv.DictReader((P/'REFERENCE_AUDIT_TABLE.csv').open(encoding='utf-8-sig',newline='')))
check('CSV 49 条、编号及顺序完整',[int(x['Ref_ID']) for x in rows]==expected)
check('CSV 原 key 一致',[x['Citation_Key'] for x in rows]==keys)
check('CSV UTF-8 BOM',(P/'REFERENCE_AUDIT_TABLE.csv').read_bytes().startswith(b'\xef\xbb\xbf'))
required='Ref_ID Citation_Key Original_Reference Verified_Title Verified_Authors Verified_Venue Verified_Year Verified_Volume Verified_Issue Verified_Pages Verified_Article_Number Verified_DOI Official_URL Metadata_URL Verification_Status Problem_Level Problem_Description Recommended_Correction'.split()
check('CSV 必需字段齐全',set(required)<=set(rows[0]))
check('每条都有来源、核验结果及建议',all(x['Official_URL'] and x['Metadata_URL'] and x['Verification_Status'] and x['Recommended_Correction'] for x in rows))
details=(P/'REFERENCE_AUDIT_DETAILS.md').read_text();ct=(P/'CITATION_CONSISTENCY_REPORT.md').read_text();tx=(P/'CORRECTED_REFERENCES_SUGGESTED.tex').read_text()
check('DETAILS 覆盖每条且不重复',[int(x) for x in re.findall(r'^## \[(\d+)\]',details,re.M)]==expected)
for field in ['原始参考文献','官方核验结果','作者核查','标题核查','年份核查','会议或期刊核查','卷期核查','页码与文章编号核查','DOI 核查','真实研究内容与正文引用核查','问题等级','具体问题','推荐正确写法','核验来源 URL']:
 check('DETAILS 每条包含 '+field,details.count('**'+field)>=49)
check('引用报告有全部49条映射',[int(x) for x in re.findall(r'^\| \[(\d+)\] /',ct,re.M)]==expected)
check('引用报告有44组且不重漏',re.findall(r'^### (T\d{3})',ct,re.M)==[f'T{i:03}' for i in range(1,45)])
check('建议稿49个key原顺序保留',re.findall(r'\\bibitem\{([^}]+)\}',tx)==keys)
check('建议稿不包含覆盖原文件操作','write18' not in tx and 'includegraphics' not in tx)
check('待核实[27]完整保留原文',refs[26]['recommended_tex']==refs[26]['raw_tex'])
check('Article Number 已分离',[(rows[i-1]['Verified_Article_Number']) for i in [13,15,31,32,33]]==['14','17','63','253','187'])
check('官方优先解决RSMI期号冲突',rows[9]['Verified_Issue']=='11' and '12' in rows[9]['Version_Notes'])
check('补全R-tree完整页码',rows[0]['Verified_Pages']=='47-57')
check('保留有来源支持的年份',[(rows[i-1]['Verified_Year']) for i in [9,14,15,28,32,45]]==['2020','2020','2025','2022','2023','1998'])
check('原有五个 DOI 均保留且匹配',all(rows[i-1]['Original_DOI'].lower()==rows[i-1]['Verified_DOI'].lower() for i in [15,18,19,20,49]))
check('所有原书目数值字段与核实字段匹配',all(not row['Original_'+a] or row['Original_'+a].lower()==row['Verified_'+b].lower() for row in rows for a,b in [('Year','Year'),('Volume','Volume'),('Issue','Issue'),('Pages','Pages'),('Article_Number','Article_Number'),('DOI','DOI')]))
check('无重复 DOI',len([x['Verified_DOI'] for x in rows if x['Verified_DOI']])==len(set(x['Verified_DOI'].lower() for x in rows if x['Verified_DOI'])))
cs=json.loads((E/'citations_audited.json').read_text());ps=json.loads((E/'citations_pdf.json').read_text())
check('44组PDF/TeX引用集合对应',all(sorted(int(k[1:]) for k in c['keys'])==sorted(p['ids']) for c,p in zip(cs,ps)))
check('正文引用成员85次',sum(len(c['keys']) for c in cs)==85)
check('统计互斥且一致',dict(collections.Counter(x['Problem_Level'] for x in rows))=={'P3':32,'P1':1,'P2':15,'待核实':1})
check('原 PDF 和 TeX 哈希未改变',all(hashlib.sha256((R/n).read_bytes()).hexdigest()==v for n,v in json.loads((E/'input_sha256.json').read_text()).items()))
aux=(E/'compile_check/check.aux').read_text()
check('建议稿可独立编译且编号1至49',re.findall(r'\\bibcite\{([^}]+)\}\{(\d+)\}',aux)==[(k,str(i)) for i,k in zip(expected,keys)])
check('编译日志无LaTeX错误','! LaTeX Error' not in (E/'compile_check/check.log').read_text())
pdf=pymupdf.open(E/'compile_check/check.pdf');pt='\n'.join(p.get_text() for p in pdf)
check('编译产物含49条编号',re.findall(r'^\[(\d+)\]',pt,re.M)==[str(i) for i in expected])
checks={'checks':results,'all_passed':True,'five_deliverables':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in P.iterdir() if f.is_file()}}
(E/'validation_results.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
print('完整性复核通过：',len(results),'项；49 条参考文献、44 组正文引用、85 个引用成员。')
print('建议 LaTeX 编译通过（独立测试文档）；原始 PDF/TeX SHA-256 不变。')
