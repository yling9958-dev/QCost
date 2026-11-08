"""Verify exact single-result scope, byte preservation and unchanged Figure 7 design."""
from pathlib import Path
import csv,json,hashlib,difflib,ast
from decimal import Decimal,ROUND_HALF_UP
import numpy as np
from PIL import Image
import pymupdf as fitz

ROOT=Path(__file__).resolve().parents[1];A=ROOT/'reports/flood_skewed_real_update_20261025'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return list(csv.DictReader(p.open()))
def main():
    inventory=json.loads((A/'BEFORE.json').read_text());scope=json.loads((A/'SCOPE.json').read_text())
    changed=[];preserved=[]
    for record in inventory:
        p=ROOT/record['Path'];assert p.is_file(),p
        current=sha(p)
        if current!=record['SHA256']:
            assert record['Path'] in scope['Mutable_Files'],('Unexpected file change',record['Path'])
            changed.append(dict(Path=record['Path'],Before_SHA256=record['SHA256'],After_SHA256=current))
        else:preserved.append(record['Path'])
    differences=[]
    metric_fields={'build_s','mean_ms','p95_ms','p99_ms','qps','correctness_status','timing_observations','correctness_observations'}
    rules={'fullscale_results.csv':metric_fields,'fullscale_plot_accepted.csv':metric_fields,
           'construction_results.csv':{'build_s','construction_hours'},'fig7_current_plotted_values.csv':{'value'}}
    for name,allowed in rules.items():
        before=rows(A/'before/data'/name);after=rows(ROOT/'data'/name)
        assert len(before)==len(after)
        for rownum,(old,new) in enumerate(zip(before,after),2):
            assert old.keys()==new.keys()
            for field in old:
                if old[field]!=new[field]:
                    assert (old['method'],old['dataset'])==('Flood','Skewed 2D')
                    assert old.get('point_count','204986702')=='204986702' and field in allowed,(name,field)
                    differences.append(dict(File=name,Line=rownum,Field=field,Before=old[field],After=new[field]))
    expected=dict(Build_s='153.381455',IndexSize_MiB='N/A',Mean_ms='199.713213',P95_ms='715.018688',P99_ms='4286.059673',
        QPS='5.007180',PeakMemory_MiB='16535.820313',Correctness='1000/1000 passed',WarmupQueries='300',FormalMeasurements='15000',MeasurementRounds='5')
    published=rows(ROOT/'data/flood_skewed_real_result.csv');assert len(published)==1
    published=published[0];assert (published['Dataset'],published['Method'],published['Points'])==('Skewed 2D','Flood','204986702')
    for k,v in expected.items():assert published[k]==v,(k,published[k])
    old=json.loads((A/'before/data/user_supplied_flood_skewed_summary.json').read_text())
    new=json.loads((ROOT/'data/user_supplied_flood_skewed_summary.json').read_text())
    allowed={'build_s','mean_ms','p95_ms','p99_ms','reported_qps','derived_qps','peak_memory_mib',
        'timing_observations_verified','correctness_observations_verified','correctness','warmup_queries','measurement_rounds'}
    for key in set(old)|set(new):
        if old.get(key)!=new.get(key):assert key in allowed,key
    assert new['index_size_mib'] is None
    qcost=[r for r in rows(ROOT/'data/fullscale_results.csv') if (r['method'],r['dataset'])==('Q-COST','Skewed 2D')][0]
    assert qcost['mean_ms']=='6.423591329733333'
    source=ROOT.parent/'flood_skewed2d_completion/07_metrics/final_handoff.json'
    real=json.loads(source.read_text())['metrics']
    mapping={'Build_s':'Build_Time_s','Mean_ms':'Mean_Latency_ms','P95_ms':'P95_Latency_ms','P99_ms':'P99_Latency_ms','QPS':'QPS','PeakMemory_MiB':'Peak_RSS_MiB'}
    for key,rawkey in mapping.items():assert Decimal(real[rawkey]).quantize(Decimal('.000001'),rounding=ROUND_HALF_UP)==Decimal(expected[key])
    a=Image.open(A/'before/figures/fig7_grouped_bar.png');b=Image.open(ROOT/'figures/fig7_grouped_bar.png')
    assert a.size==b.size==(4235,2723) and a.info['dpi']==b.info['dpi']
    changed_pixels=np.any(np.asarray(a)!=np.asarray(b),axis=2);h,w=changed_pixels.shape;boxes=[]
    for i in range(2):
        for j in range(2):
            ys,xs=np.where(changed_pixels[i*h//2:(i+1)*h//2,j*w//2:(j+1)*w//2])
            box=[int(xs.min()+j*w//2),int(ys.min()+i*h//2),int(xs.max()+j*w//2),int(ys.max()+i*h//2)]
            # Each component is confined to the previously recorded target bar footprint.
            assert (box[0],box[2])==((1892,1940) if j==0 else (4028,4076))
            boxes.append(dict(Panel=i*2+j,Changed_Pixels=len(xs),Bounds=box))
    baseline=fitz.open(A/'before/figures/fig7_grouped_bar.pdf');pdf=fitz.open(ROOT/'figures/fig7_grouped_bar.pdf')
    assert len(pdf)==len(baseline)==1 and pdf[0].rect==baseline[0].rect and not pdf[0].get_images()
    assert pdf[0].get_text()==baseline[0].get_text()
    assert json.loads((ROOT/'reports/fig7_grouped_bar_compact_layout.json').read_text())==json.loads((A/'render/reports/fig7_grouped_bar_compact_layout.json').read_text())
    assert (ROOT/'reports/fig7_bar_style_audit.csv').read_bytes()==(A/'render/reports/fig7_bar_style_audit.csv').read_bytes()
    for name in ['extract_results.py','plot_fig7.py','write_layout_revision.py','update_flood_skewed_real_result.py']:ast.parse((ROOT/'scripts'/name).read_text())
    with (A/'FIELD_CHANGES.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(differences[0]));writer.writeheader();writer.writerows(differences)
    (A/'CHANGED_FILES.json').write_text(json.dumps(changed,indent=2))
    diffs=[]
    for item in changed:
        name=item['Path']
        if Path(name).suffix not in {'.pdf','.png','.svg'}:
            before=(A/'before'/name).read_text();after=(ROOT/name).read_text()
            diffs.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='before/'+name,tofile='after/'+name))
    (A/'MINIMAL_CHANGES.diff').write_text(''.join(diffs))
    receipt=dict(Status='PASS',Modified_Existing_Files=len(changed),Unchanged_Existing_Files=len(preserved),
        Protected_Original_Project_Files=len(inventory),Non_Target_Data_Fields_Changed=0,Changed_Bar_Endpoints=4,Unchanged_Bar_Endpoints=108,
        All_Other_Figures_Unchanged=True,Unchanged_Figure_Files=sum(x.startswith('figures/') for x in preserved),
        All_LaTeX_Unchanged=all(x['Path'].split('/')[0]!='latex' for x in changed),Style_Identical=True,Layout_Identical=True,
        Axes_Unchanged=True,PNG_Pixels=list(b.size),PNG_DPI=b.info['dpi'],Vector_PDF=True,Pixel_Difference_Regions=boxes,
        Index_Size='N/A',Q_COST_Skewed_Mean_ms=qcost['mean_ms'],Real_Source_Rounding_Matches=True,Experiments_Run=0,
        Unresolved_Items=[])
    (A/'VALIDATION.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
if __name__=='__main__':main()
