"""Add measurement definitions to a new immutable final report version."""
from pathlib import Path
import json
from docx import Document
RUN=Path(__file__).resolve().parents[1]
report=RUN/'report'
text=(report/'QMF_ALGORITHM_FEASIBILITY_REPORT_ZH_FINAL.md').read_text()
notes=(report/'MEASUREMENT_NOTES.md').read_text()
text+='\n\n'+notes.replace('# 测量口径补充','## 测量口径补充',1)
md=report/'QMF_ALGORITHM_FEASIBILITY_REPORT_ZH_FINAL_v2.md'
with md.open('x') as f:f.write(text)
doc=Document(report/'QMF_算法可行性与研究路线报告_20261009.docx')
doc.add_heading('测量口径补充',1)
for line in notes.splitlines()[1:]:
    if line.strip():doc.add_paragraph(line.removeprefix('- '))
doc.add_paragraph('节点类型与实际/预期fallback语义见 NODE_DIAGNOSTIC_COVERAGE.csv；缺失类型保留 NOT AVAILABLE。')
out=report/'QMF_算法可行性与研究路线报告_20261009_最终版.docx'
assert not out.exists();doc.save(out)
with (report/'DELIVERABLES.json').open('x') as f:json.dump({'markdown':str(md),'word':str(out),
    'content':'Full Chinese report, six requested tables, formulas, exact validator evidence, raw-result paths, route decisions and <=500 Chinese character advisor summary',
    'prior_versions_preserved':True,'scientific_results_changed':False},f,ensure_ascii=False,indent=2)
print(str(md));print(str(out))
