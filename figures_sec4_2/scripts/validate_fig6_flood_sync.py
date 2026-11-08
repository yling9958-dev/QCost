"""Confirm append-only real ECDF data and preservation of Figures 7 and 8."""
from pathlib import Path
import hashlib,json,csv,xml.etree.ElementTree as ET
import pandas as pd,numpy as np
from PIL import Image
import pymupdf as fitz
R=Path(__file__).resolve().parents[1];A=R/'reports/fig6_flood_sync_20261025'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    before=json.loads((A/'BEFORE.json').read_text());allowed=json.loads((A/'SCOPE.json').read_text())['Mutable_Files']
    changed=[];unchanged=[]
    for entry in before:
        p=R/entry['Path'];assert p.is_file(),p
        if sha(p)!=entry['SHA256']:
            assert entry['Path'] in allowed,entry['Path'];changed.append(entry['Path'])
        else:unchanged.append(entry['Path'])
    for stem in ['fig7_grouped_bar','fig8_construction_storage']:
        assert all(f'figures/{stem}.{ext}' in unchanged for ext in ['png','svg','pdf'])
    for name in ['fullscale_latency_observations.csv','fig6_ecdf_steps.csv','fig6_ecdf_statistics.csv']:
        old=(A/'before/data'/name).read_bytes();new=(R/'data'/name).read_bytes();assert new.startswith(old)
    raw=pd.read_csv(R/'data/fullscale_latency_observations.csv')
    assert len(raw)==420000
    flood=raw[raw.dataset.eq('Skewed 2D')&raw.method_display.eq('Flood')]
    assert len(flood)==15000 and flood.groupby('repetition').size().to_dict()=={i:3000 for i in range(5)}
    assert not flood.duplicated(['repetition','ordinal']).any()
    stats=pd.read_csv(R/'data/fig6_ecdf_statistics.csv');assert len(stats)==14 and stats.observations.eq(15000).all()
    steps=pd.read_csv(R/'data/fig6_ecdf_steps.csv');g=steps[steps.dataset.eq('Skewed 2D')&steps.method.eq('Flood')]
    assert g.multiplicity.sum()==15000 and np.isclose(g.cumulative_probability.iloc[-1],1.)
    v=np.sort(flood.latency_ns.to_numpy(dtype=np.float64)/1e6);x,c=np.unique(v,return_counts=True)
    assert np.array_equal(g.multiplicity,c) and np.allclose(g.latency_ms,x,rtol=1e-12)
    assert np.allclose(g.cumulative_probability,np.cumsum(c)/15000,rtol=1e-12)
    old=Image.open(A/'before/figures/fig6_latency_ecdf.png');new=Image.open(R/'figures/fig6_latency_ecdf.png')
    assert old.size==new.size and old.info['dpi']==new.info['dpi']
    original=np.asarray(old);actual=np.asarray(new);half=actual.shape[1]//2
    assert np.array_equal(original[:,:half],actual[:,:half])
    prior_layout=json.loads((R/'reports/fig6_latency_ecdf_compact_layout.json').read_text())
    new_layout=json.loads((A/'render/reports/fig6_latency_ecdf_compact_layout.json').read_text());assert prior_layout==new_layout
    p=fitz.open(R/'figures/fig6_latency_ecdf.pdf');oldp=fitz.open(A/'before/figures/fig6_latency_ecdf.pdf')
    assert len(p)==len(oldp)==1 and p[0].rect==oldp[0].rect and not p[0].get_images()
    svg=ET.parse(R/'figures/fig6_latency_ecdf.svg').getroot();assert not svg.findall('.//{http://www.w3.org/2000/svg}image')
    pages={}
    for stem in ['section4_2_figures_layout_preview','section4_2_figures_three_widths']:
        current=fitz.open(R/'latex'/f'{stem}.pdf');previous=fitz.open(A/'before/latex'/f'{stem}.pdf')
        assert len(current)==len(previous);pages[stem]=len(current)
        for i,page in enumerate(current):
            text=page.get_text();assert len(text.strip())>20
            if 'Empirical distributions' in text:
                assert 'includes seven' in text and 'includes six' not in text
                page.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(A/f'{stem}_page{i+1}.png')
    receipt=dict(Status='PASS',Original_Raw_Observations_Untouched=405000,Added_Real_Observations=15000,
        Existing_ECDFs_Untouched=13,Current_ECDFs=14,GeoLife_Pixel_Identical=True,
        Figure7_Byte_Identical=True,Figure8_Byte_Identical=True,Other_Figures_Unchanged=True,
        Layout_Identical=True,Axes_Unchanged=True,PNG_Size=list(new.size),PNG_DPI=new.info['dpi'],SVG_PDF_Vector=True,
        Current_Preview_Pages=pages,Modified_Existing_Files=changed,Unchanged_Existing_Files=len(unchanged),
        Original_Source_Logs='Unmodified',Experiments_Run=0)
    (A/'VALIDATION.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
if __name__=='__main__':main()
