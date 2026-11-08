"""Apply only the confirmed Flood / 204986702-point Skewed result; redraw Figure 7."""
from pathlib import Path
import csv,io,json,hashlib,shutil,subprocess,sys,os

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'reports/flood_skewed_real_update_20261025'
VALUES=dict(build_s='153.381455',mean_ms='199.713213',p95_ms='715.018688',
            p99_ms='4286.059673',qps='5.007180')
SOURCE=ROOT.parent/'flood_skewed2d_completion/07_metrics/final_handoff.json'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def replace_record(path,changes,point_count=True):
    # Preserve every non-target line byte for byte, including decimal spelling.
    raw=path.read_bytes();lines=raw.decode().splitlines(keepends=True)
    fields=next(csv.reader([lines[0]]));found=0
    for index,line in enumerate(lines[1:],1):
        row=next(csv.reader([line]));record=dict(zip(fields,row))
        if (record.get('method'),record.get('dataset'))!=('Flood','Skewed 2D'):continue
        if point_count and record.get('point_count')!='204986702':continue
        found+=1;updates=changes(record) if callable(changes) else changes
        for key,value in updates.items():row[fields.index(key)]=str(value)
        stream=io.StringIO(newline='');ending='\r\n' if line.endswith('\r\n') else '\n'
        csv.writer(stream,lineterminator=ending).writerow(row);lines[index]=stream.getvalue()
    assert found==(1 if point_count else 4),(path,found)
    result=''.join(lines).encode()
    if result!=raw:path.write_bytes(result)

def main():
    assert (AUDIT/'BEFORE.json').is_file(),'A protected pre-update snapshot is required'
    source=json.loads(SOURCE.read_text())
    assert source['status']=='EXPERIMENT_COMPLETED'
    assert source['metrics']['Points']=='204986702' and source['metrics']['Index_Size_MiB']=='N/A'
    assert source['formal_latency_records']==15000 and source['completed_rounds']==5 and source['exact_correctness_queries']==1000
    # Published values are the user's confirmed precision, not recomputed measurements.
    full=dict(VALUES,correctness_status='1000/1000 passed',timing_observations='15000',correctness_observations='1000')
    for name in ['fullscale_results.csv','fullscale_plot_accepted.csv']:
        replace_record(ROOT/'data'/name,full)
    replace_record(ROOT/'data/construction_results.csv',dict(build_s=VALUES['build_s'],construction_hours=str(float(VALUES['build_s'])/3600)))
    replace_record(ROOT/'data/fig7_current_plotted_values.csv',lambda row:{'value':VALUES[row['metric']]},point_count=False)
    path=ROOT/'data/user_supplied_flood_skewed_summary.json';obj=json.loads(path.read_text())
    assert (obj['method'],obj['dataset'],obj['point_count'])==('Flood-V2','Skewed 2D',204986702)
    obj.update({key:float(value) for key,value in VALUES.items() if key!='qps'})
    obj.update(index_size_mib=None,reported_qps=5.007180,peak_memory_mib=16535.820313,
               timing_observations_verified=15000,correctness_observations_verified=1000,
               correctness='1000/1000 passed',warmup_queries=300,measurement_rounds=5)
    obj['derived_qps']=1000/obj['mean_ms'];obj['reported_qps_matches_rounding']=round(obj['derived_qps'],6)==obj['reported_qps']
    path.write_text(json.dumps(obj,indent=2)+'\n')
    result=ROOT/'data/flood_skewed_real_result.csv'
    with result.open('w',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['Dataset','Method','Points','Build_s','IndexSize_MiB','Mean_ms','P95_ms','P99_ms','QPS','PeakMemory_MiB','Correctness','WarmupQueries','FormalMeasurements','MeasurementRounds'])
        writer.writerow(['Skewed 2D','Flood','204986702','153.381455','N/A','199.713213','715.018688','4286.059673','5.007180','16535.820313','1000/1000 passed','300','15000','5'])
    # Isolate incidental script exports: promote only Figure 7 and its source-hash receipt.
    stage=AUDIT/'render'
    for name in ['scripts','data','figures','reports']:(stage/name).mkdir(parents=True,exist_ok=True)
    for name in ['plot_fig7.py','plot_style.py','layout_tools.py']:shutil.copy2(ROOT/'scripts'/name,stage/'scripts'/name)
    shutil.copy2(ROOT/'data/fullscale_results.csv',stage/'data/fullscale_results.csv')
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',MPLCONFIGDIR=str(stage/'reports/mplconfig'))
    with (AUDIT/'render.log').open('w') as out:
        subprocess.run([sys.executable,'-B',str(stage/'scripts/plot_fig7.py')],env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
    assert (stage/'reports/fig7_bar_style_audit.csv').read_bytes()==(ROOT/'reports/fig7_bar_style_audit.csv').read_bytes()
    assert json.loads((stage/'reports/fig7_grouped_bar_compact_layout.json').read_text())==json.loads((ROOT/'reports/fig7_grouped_bar_compact_layout.json').read_text())
    previous=json.loads((AUDIT/'before/reports/fig7_current_data_check.json').read_text())
    generated=json.loads((stage/'reports/fig7_current_data_check.json').read_text())
    assert generated['limits']==previous['limits']
    assert generated['source_sha256']==sha(ROOT/'data/fullscale_results.csv')
    for ext in ['png','svg','pdf']:shutil.copy2(stage/'figures'/f'fig7_grouped_bar.{ext}',ROOT/'figures'/f'fig7_grouped_bar.{ext}')
    shutil.copy2(stage/'reports/fig7_current_data_check.json',ROOT/'reports/fig7_current_data_check.json')
    (AUDIT/'APPLICATION.json').write_text(json.dumps(dict(Status='APPLIED',Target=['Flood','Skewed 2D',204986702],
        Confirmed_Values=VALUES,Peak_RSS_MiB='16535.820313',Index_Size='N/A',Correctness='1000/1000 passed',
        Warmup_Queries=300,Formal_Measurements=15000,Rounds=5,New_Result=str(result),
        Source_Handoff=str(SOURCE),Source_SHA256=sha(SOURCE),Layout_Identical=True,Style_Identical=True,Axes_Identical=True,
        Run_Scripts=['plot_fig7.py'],Experiments_Run=0,Legacy_Import_Metadata='Preserved; current confirmation and original source are recorded here'),indent=2))
    print('Applied one exact dataset/method record; Figure 7 PNG/SVG/PDF redrawn without layout or axis changes.')

if __name__=='__main__':main()
