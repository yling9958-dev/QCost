"""Capture delivered code, analysis environment and artifact hashes."""
from pathlib import Path
import hashlib,json,sys,platform,subprocess,importlib.metadata,datetime
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files=[]
for folder in ['08_reproduce','03_metrics','04_tables','05_figures','07_latex']:
    for p in sorted((R/folder).rglob('*')):
        if p.is_file() and not any(x.startswith('checkpoint_') or x=='__pycache__' for x in p.parts):
            files.append(dict(File=str(p.relative_to(R)),Bytes=p.stat().st_size,SHA256=sha(p)))
pdf=R/'06_reports/paper_build/SecPaper_Yaqi-2-QMF-Selection.pdf'
files.append(dict(File=str(pdf.relative_to(R)),Bytes=pdf.stat().st_size,SHA256=sha(pdf)))
packages={}
for name in ['numpy','pandas','scipy','matplotlib','pymupdf','Pillow']:
    packages[name]=importlib.metadata.version(name)
result=dict(Created_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),Analysis_Python=sys.version,
    Platform=platform.platform(),Packages=packages,LaTeX=subprocess.check_output(['pdflatex','--version'],text=True).splitlines()[0],
    Optimizer_Environment='02_raw_logs/formal/manifest.json',Raw_Log_Hashes='03_metrics/RAW_SHA256.csv',Artifacts=files)
(R/'06_reports/REPRODUCIBILITY_MANIFEST.json').write_text(json.dumps(result,indent=2))
print('Final artifact hashes:',len(files))
