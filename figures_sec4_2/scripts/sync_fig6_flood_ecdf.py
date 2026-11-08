"""Append the completed Flood/Skewed timings and redraw only the existing Figure 6."""
from pathlib import Path
import csv,json,hashlib,io,shutil,subprocess,sys,os
from decimal import Decimal
import numpy as np

R=Path(__file__).resolve().parents[1];A=R/'reports/fig6_flood_sync_20261025'
SOURCE=R.parent/'flood_skewed2d_completion'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return list(csv.DictReader(p.open()))
def append_only(path,records):
    before=path.read_bytes();header=next(csv.reader(io.StringIO(before.decode())))
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=header,lineterminator='\n');writer.writerows(records)
    assert before.endswith(b'\n')
    with path.open('ab') as out:out.write(stream.getvalue().encode())
    assert path.read_bytes().startswith(before)
def main():
    assert (A/'BEFORE.json').exists()
    handoff=json.loads((SOURCE/'07_metrics/final_handoff.json').read_text())
    assert handoff['status']=='EXPERIMENT_COMPLETED' and handoff['metrics']['Points']=='204986702'
    aggregate=SOURCE/'FLOOD_SKEWED2D_LATENCIES.csv';published=read(aggregate)
    assert len(published)==15000 and sha(aggregate)==handoff['evidence_sha256'][aggregate.name]
    records=[];source_hashes=[];ns=[]
    for rep in range(5):
        source=SOURCE/f'05_queries/latency.r{rep}.csv';rows=read(source)
        assert len(rows)==3000 and sha(source)==handoff['evidence_sha256'][str(source.relative_to(SOURCE))]
        source_hashes.append(dict(Path=str(source),SHA256=sha(source),Observations=len(rows)))
        for ordinal,row in enumerate(rows):
            i=rep*3000+ordinal;summary=published[i]
            assert row['method']=='flood' and int(row['repetition'])==rep and int(row['ordinal'])==ordinal
            assert int(summary['Round'])==rep+1 and summary['Query_ID']==row['query_id']
            assert Decimal(summary['Latency_ms'])*1000000==int(row['latency_ns'])
            assert summary['Result_Count']==row['result_count'] and summary['Query_Class']==row['selectivity_group']
            ns.append(int(row['latency_ns']))
            records.append(dict(dataset='Skewed 2D',method_display='Flood',repetition=rep,ordinal=ordinal,
                query_id=row['query_id'],latency_ns=row['latency_ns'],result_count=row['result_count'],
                source_file=str(aggregate),source_row=i+2))
    v=np.sort(np.asarray(ns,dtype=np.float64)/1e6);x,counts=np.unique(v,return_counts=True);prob=np.cumsum(counts)/len(v)
    assert abs(v.mean()-199.713213)<=.5e-6 and abs(np.quantile(v,.95)-715.018688)<=.5e-6
    assert abs(np.quantile(v,.99)-4286.059673)<=.5e-6
    raw=R/'data/fullscale_latency_observations.csv'
    existing=[row for row in read(raw) if row['dataset']=='Skewed 2D' and row['method_display']=='Flood']
    if existing:
        assert len(existing)==15000 and [int(row['latency_ns']) for row in existing]==ns
    else:append_only(raw,records)
    path=R/'data/fig6_ecdf_steps.csv';prior=read(path)
    current=[row for row in prior if row['dataset']=='Skewed 2D' and row['method']=='Flood']
    if not current:
        append_only(path,[dict(dataset='Skewed 2D',method='Flood',latency_ms=xx,cumulative_probability=pp,multiplicity=int(cc)) for xx,pp,cc in zip(x,prob,counts)])
    else:
        assert len(current)==len(x) and np.allclose([float(row['latency_ms']) for row in current],x,rtol=1e-12)
    stats=dict(dataset='Skewed 2D',method='Flood',observations=len(v),minimum_ms=v[0],maximum_ms=v[-1],
        mean_ms=v.mean(),p95_ms=np.quantile(v,.95),p99_ms=np.quantile(v,.99),source_file=str(aggregate))
    path=R/'data/fig6_ecdf_statistics.csv'
    if not any(row['dataset']=='Skewed 2D' and row['method']=='Flood' for row in read(path)):append_only(path,[stats])
    stage=A/'render'
    for part in ['scripts','data','figures','reports']:(stage/part).mkdir(parents=True,exist_ok=True)
    for name in ['plot_fig6.py','plot_style.py','layout_tools.py']:shutil.copy2(R/'scripts'/name,stage/'scripts'/name)
    for name in ['fullscale_latency_observations.csv','fullscale_results.csv','fig6_ecdf_steps.csv','fig6_ecdf_statistics.csv']:shutil.copy2(R/'data'/name,stage/'data'/name)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',MPLCONFIGDIR=str(stage/'reports/mplconfig'))
    with (A/'render.log').open('w') as out:
        subprocess.run([sys.executable,'-B',str(stage/'scripts/plot_fig6.py')],env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
    assert json.loads((stage/'reports/fig6_latency_ecdf_compact_layout.json').read_text())==json.loads((R/'reports/fig6_latency_ecdf_compact_layout.json').read_text())
    for ext in ['png','svg','pdf']:shutil.copy2(stage/'figures'/f'fig6_latency_ecdf.{ext}',R/'figures'/f'fig6_latency_ecdf.{ext}')
    (A/'SOURCE_AND_RESULT.json').write_text(json.dumps(dict(Status='PASS',Added_Observations=15000,Rounds=5,Per_Round=3000,
        Aggregate_Source=str(aggregate),Aggregate_SHA256=sha(aggregate),Nanosecond_Sources=source_hashes,
        ECDF_Statistics=stats,Layout_Identical=True,Figure8='Unchanged: Q-COST-only construction and unavailable Flood index size',
        Experiments_Run=0,Figures_Redrawn=['fig6_latency_ecdf']),indent=2))
    print('Figure 6 now has seven real curves per dataset; Figure 7/8 remain unchanged.')
if __name__=='__main__':main()
