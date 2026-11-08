"""Downstream numeric reporting. Never starts workers or edits benchmark checkpoints."""
import csv
import math
from pathlib import Path
import statistics
import subprocess
import io
import json
import support as s
from paper_protocol import (DATASET_NAMES, DATASET_RESULT_SLUGS,
                            PERFORMANCE_REPETITIONS, QUERY_COUNTS,
                            REPORT_METHOD_LABELS)

DISPLAY=list(REPORT_METHOD_LABELS)
SHORT=list(DATASET_RESULT_SLUGS)
NAMES=list(DATASET_NAMES)
FIELDS=['Method',*s.METRICS,'Correctness','Status']

def method_result_root(dataset,runtime):
    if runtime!='flood':return s.OUT
    pointer=s.OUT/'debug/flood_correctness_memfix_20260915/published.json'
    if not pointer.exists():return s.OUT
    receipt=s.read_json(pointer)
    if receipt.get('dataset')!=dataset:return s.OUT
    target=Path(receipt['attempt'])
    marker=target/'checkpoints'/dataset/'flood_method.done'
    if s.sha(marker)!=receipt['method_sha256']:raise RuntimeError('Published Flood result SHA mismatch')
    return target

def text(path,value):
    import os
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.part')
    with temp.open('w') as f:
        f.write(value); f.flush(); os.fsync(f.fileno())
    temp.replace(path)

def fmt(v):
    if v is None or v=='': return 'N/A'
    if isinstance(v,float): return f'{v:.6g}' if math.isfinite(v) else 'N/A'
    return str(v)

def rows(dataset):
    result=[]
    for label,(display,runtime) in zip(DISPLAY,s.METHODS):
        method_root=method_result_root(dataset,runtime)
        cp=method_root/'checkpoints'/dataset/(runtime+'_method.done')
        r=s.read_json(cp)['payload'] if cp.exists() else {}
        r={**{m:None for m in s.METRICS},'Correctness':'NOT_RUN','Status':'NOT_RUN',**r,'Method':label}
        if not cp.exists():
            # An ongoing retry must not hide its still-valid offline measurements.
            build=s.marker(dataset,runtime+'_build_r0')
            if build.exists():
                value=s.read_json(build)['payload']
                r.update(Build_s=value.get('build_seconds'),Status='INCOMPLETE')
                if runtime in s.PERSISTENT and value.get('serialized_bytes') is not None:
                    r['IndexSize_MiB']=value['serialized_bytes']/2**20
                if value.get('peak_rss_kib') is not None: r['PeakMemory_MiB']=value['peak_rss_kib']/1024
        corr=method_root/'checkpoints'/dataset/(runtime+'_correctness.done')
        if corr.exists():
            v=s.read_json(corr)['payload']; r['Missing']=v.get('missing'); r['Extra']=v.get('extra')
            if not cp.exists() and (v.get('exact'),v.get('missing'),v.get('extra'))==(
                    QUERY_COUNTS['correctness'],0,0) and s.valid(dataset,runtime+'_correctness'):
                r['Correctness']=(f"{QUERY_COUNTS['correctness']}/"
                                  f"{QUERY_COUNTS['correctness']} exact")
        else:
            r['Missing']=r['Extra']=None
            if r['Status'] in ('CORRECTNESS_INVALID','CORRECTNESS_FAILED'): r['Correctness']='INVALID'
        result.append(r)
    return result

def valid_method(dataset,runtime):
    """Validate retained numeric evidence; a deleted completed index need not be rebuilt."""
    root=method_result_root(dataset,runtime)
    if root!=s.OUT:
        previous=s.OUT
        try:
            s.OUT=root
            return valid_method(dataset,runtime)
        finally:s.OUT=previous
    cp=s.marker(dataset,runtime+'_method')
    if not cp.exists(): return False
    result=s.read_json(cp)['payload']
    expected_correctness=(f"{QUERY_COUNTS['correctness']}/"
                          f"{QUERY_COUNTS['correctness']} exact")
    if result.get('Status')!='PASS' or result.get('Correctness')!=expected_correctness: return False
    required=[m for m in s.METRICS if m!='IndexSize_MiB' or runtime in s.PERSISTENT]
    if any(result.get(m) is None or not math.isfinite(result[m]) or result[m]<0 for m in required): return False
    build=s.marker(dataset,runtime+'_build_r0')
    if not build.exists() or s.read_json(build)['payload'].get('build_seconds')!=result['Build_s']: return False
    corr=s.marker(dataset,runtime+'_correctness')
    if not corr.exists() or not s.valid(dataset,runtime+'_correctness'): return False
    v=s.read_json(corr)['payload']
    if (v.get('exact'),v.get('missing'),v.get('extra'))!=(QUERY_COUNTS['correctness'],0,0):
        return False
    seen=set()
    for rep in range(1,PERFORMANCE_REPETITIONS+1):
        marker=s.marker(dataset,f'{runtime}_timing_r{rep}')
        if not marker.exists(): return False
        for entry in s.read_json(marker)['files']:
            if entry['path'] in seen: continue
            seen.add(entry['path']); p=Path(entry['path'])
            if not p.is_file() or p.stat().st_size!=entry['bytes'] or s.sha(p)!=entry['sha256']: return False
    raw=s.OUT/'05_performance'/dataset/runtime/'query_latency_raw.csv.zst'
    if not raw.exists(): return False
    proc=subprocess.run(['zstd','-q','-dc',str(raw)],capture_output=True,text=True)
    if proc.returncode: return False
    records=list(csv.DictReader(io.StringIO(proc.stdout)))
    with (s.OUT/'02_queries'/dataset/(dataset+'_queries.csv')).open() as f:
        expected=[r['query_id'] for r in csv.DictReader(f) if r['split']=='performance']
    if len(expected)!=QUERY_COUNTS['performance'] or \
       len(records)!=QUERY_COUNTS['performance']*PERFORMANCE_REPETITIONS: return False
    return all([r['query_id'] for r in records if int(r['repetition'])==rep]==expected
               for rep in range(PERFORMANCE_REPETITIONS))

def completion(dataset):
    def was_attempted(runtime):
        if s.marker(dataset,runtime+'_method').exists(): return True
        if dataset=='geolife_2d_4p2G':
            return (s.OUT/'debug/original_attempts'/runtime/(runtime+'_method.done')).exists()
        return False
    attempted=sum(was_attempted(runtime) for _,runtime in s.METHODS)
    valid=sum(valid_method(dataset,runtime) for _,runtime in s.METHODS)
    return {'methods_attempted':attempted,'methods_valid':valid,'attempted':attempted==8,'scientifically_complete':valid==8}

def ranks(data):
    result=[]
    for metric in s.METRICS:
        eligible=[(i,r[metric]) for i,r in enumerate(data) if r['Status']=='PASS' and r.get(metric) is not None
                  and (metric!='IndexSize_MiB' or s.METHODS[i][1] in s.PERSISTENT)]
        v=data[0].get(metric)
        rank=None
        if any(i==0 for i,_ in eligible):
            rank=1+sum((x>v if metric=='QPS' else x<v) for i,x in eligible)
        result.append({'Metric':metric,'QMFRank':rank,'Denominator':len(eligible)})
    return result

def table(data):
    labels=['Method','Build(s)','Size(MiB)','Mean(ms)','P95(ms)','P99(ms)','QPS','PeakMem(MiB)','Correctness','Status']
    return '| '+' | '.join(labels)+' |\n|'+ '|'.join(['---']+['---:']*7+['---','---'])+'|\n'+''.join(
        '| '+' | '.join(fmt(r.get(k)) for k in FIELDS)+' |\n' for r in data)

def publish_flood_attempt(formal,attempt,dataset):
    """Publish measured Flood PASS only, preserving every other method row.

    Old method/checkpoint/resource receipts remain at their original paths.
    This downstream operation never runs a benchmark or recomputes metrics.
    """
    previous=s.OUT
    try:
        s.OUT=attempt
        if not valid_method(dataset,'flood'):raise RuntimeError('Flood is not scientifically PASS; publication forbidden')
        result=s.read_json(s.marker(dataset,'flood_method'))['payload']
    finally:s.OUT=previous
    primary=formal/'geolife/GEOLIFE_8_METHODS_7_METRICS.csv'
    original=primary.read_bytes();lines=original.splitlines(keepends=True)
    fields=next(csv.reader([lines[0].decode()]))
    positions=[i for i,line in enumerate(lines[1:],1) if next(csv.reader([line.decode()]))[0]=='Flood']
    if len(positions)!=1:raise RuntimeError('Ambiguous Flood row')
    i=positions[0];newline='\r\n' if lines[i].endswith(b'\r\n') else '\n'
    buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=fields,lineterminator=newline)
    writer.writerow({k:result.get(k) if result.get(k) is not None else 'N/A' for k in fields})
    lines[i]=buffer.getvalue().encode();new_csv=b''.join(lines)
    md=primary.with_suffix('.md');old_md=md.read_bytes();mdlines=old_md.splitlines(keepends=True)
    locations=[j for j,line in enumerate(mdlines) if line.startswith(b'| Flood |')]
    if len(locations)!=1:raise RuntimeError('Ambiguous Flood Markdown row')
    mdlines[locations[0]]=table([{**result,'Method':'Flood'}]).splitlines(keepends=True)[2].encode()
    # Retain the complete old table bytes beside the new evidence before the
    # explicitly allowed post-PASS publication. Never rewrite old hash manifests.
    for name,data in [('primary_before.csv',original),('primary_before.md',old_md)]:
        destination=attempt/name
        if not destination.exists():destination.write_bytes(data)
    for path,data in [(primary,new_csv),(md,b''.join(mdlines))]:
        if path.read_bytes()==data:continue
        import uuid
        temp=path.with_name(path.name+'.flood-publish.'+uuid.uuid4().hex+'.part')
        with temp.open('xb') as handle:
            handle.write(data);handle.flush()
            import os
            os.fsync(handle.fileno())
        temp.replace(path)
    receipt={'dataset':dataset,'attempt':str(attempt),
        'method_sha256':s.sha(attempt/'checkpoints'/dataset/'flood_method.done'),
        'primary_csv_sha256':s.sha(primary),'primary_md_sha256':s.sha(md),
        'historical_checkpoints_retained':True,'other_method_rows_unchanged':True}
    s.atomic_json(formal/'debug/flood_correctness_memfix_20260915/published.json',receipt)
    s.atomic_json(attempt/'publication.json',receipt)
    print(table([{**result,'Method':'Flood'}]),flush=True)

def dataset_report(row,index):
    dataset=row['dataset_id']; data=rows(dataset); ranking=ranks(data)
    root=s.OUT/SHORT[index]; prefix=SHORT[index].upper()
    primary=root/(prefix+'_8_METHODS_7_METRICS.csv'); md=primary.with_suffix('.md')
    rankfile=root/(prefix+'_QMF_RANKING.csv')
    s.atomic_csv(primary,[{k:(r.get(k) if r.get(k) is not None else 'N/A') for k in FIELDS} for r in data],FIELDS)
    s.atomic_csv(rankfile,ranking,['Metric','QMFRank','Denominator'])
    q=data[0]; top=sum(v['QMFRank']==1 for v in ranking)
    state=completion(dataset)
    body=f'{NAMES[index].upper()} RESULT\n{row["record_count"]:,} POINTS\n\n'
    body+=f'Methods attempted = {state["methods_attempted"]}/8; methods valid = {state["methods_valid"]}/8; scientifically complete = {"YES" if state["scientifically_complete"] else "NO"}.\n\n'+table(data)
    body+='\nQMF-INDEX — '+NAMES[index]+'\n\n'+''.join(f'{k} = {fmt(q.get(k))}\n\n' for k in [*s.METRICS,'Correctness','Missing','Extra'])
    body+='Ranks:\n\n'+''.join(f'{v["Metric"]} = {fmt(v["QMFRank"])}/{v["Denominator"]}\n\n' for v in ranking)
    body+=f'QMF TOP-1 COUNT = {top} / 7\n\n'
    for metric in ['Mean_ms','P95_ms','P99_ms','QPS']:
        eligible=[r for r in data[1:] if r['Status']=='PASS' and r.get(metric) is not None]
        best=(max if metric=='QPS' else min)(eligible,key=lambda r:r[metric]) if eligible else None
        body+=f'Best competing method for {metric} = {best["Method"] if best else "N/A"}\n\n'
    body+='Build repetitions = 1. Only correctness-valid methods enter rankings. Missing measurements are N/A.\n\nQMF_ALGORITHM_CHANGED = NO\n'
    restored=s.OUT/'debug/runtime_restored.json'
    if dataset=='geolife_2d_4p2G' and restored.exists():
        receipt=s.read_json(restored)
        body+=('\nPostGIS recovery: the original successful build measurement and exact correctness receipt are retained. '
            f'The lost SQL runtime was restored in {receipt["restoration_reference"]["payload"]["elapsed_seconds"]} s. '
            f'Its current index is {receipt["restored_gist_bytes"]} bytes; the historical build index was '
            f'{receipt["original_gist_bytes"]} bytes. Size in the repaired method row describes the current query-ready index. '
            'GiST insertion tie breaking can vary the physical layout. No timing repetition or query is selected or changed.\n')
    text(md,body)
    files=[primary,md,rankfile,s.OUT/'02_queries'/dataset/'query_manifest.json',s.OUT/'01_dataset_inventory'/f'{dataset}.json']
    manifest=root/(prefix+'_RESULT_MANIFEST.sha256')
    text(manifest,''.join(s.sha(p)+'  '+str(p)+'\n' for p in files))
    print(body,flush=True)
    return [*files,manifest]

def aggregate(inventory):
    summaries=[]; allrows=[]; rankrows=[]; comparisons=[]
    for i,row in enumerate(inventory):
        if not s.marker(row['dataset_id'],'results_persisted').exists(): continue
        data=rows(row['dataset_id']); rank=ranks(data); q=data[0]
        summary={'Dataset':NAMES[i],'Points':row['record_count'],**{k:q.get(k) for k in s.METRICS},'Correctness':q['Correctness']}
        for key,v in zip(['BuildRank','SizeRank','MeanRank','P95Rank','P99Rank','QPSRank','MemoryRank'],rank):
            summary[key]=f'{fmt(v["QMFRank"])}/{v["Denominator"]}'
        summary['Top1Count']=sum(v['QMFRank']==1 for v in rank)
        summary['Size_MiB']=summary.pop('IndexSize_MiB'); summaries.append(summary)
        rankrows.append({'Dataset':NAMES[i],**{k:summary[k] for k in ['BuildRank','SizeRank','MeanRank','P95Rank','P99Rank','QPSRank','MemoryRank','Top1Count']}})
        for r in data:
            allrows.append({'Dataset':NAMES[i],**{k:r.get(k) for k in [*FIELDS,'Missing','Extra']}})
        for metric in ['Mean_ms','P95_ms','P99_ms','QPS']:
            eligible=[r for r in data[1:] if r['Status']=='PASS' and r.get(metric) is not None]
            best=(max if metric=='QPS' else min)(eligible,key=lambda r:r[metric]) if eligible else None
            improvement=None
            if best and q['Status']=='PASS' and best[metric]:
                improvement=100*((q[metric]-best[metric]) if metric=='QPS' else (best[metric]-q[metric]))/best[metric]
            comparisons.append({'Dataset':NAMES[i],'Metric':metric,'QMF':q.get(metric),'BestBaselineMethod':best['Method'] if best else None,
                'BestBaselineValue':best[metric] if best else None,'QMFRelativeImprovementPercent':improvement,
                'QMFRank':rank[s.METRICS.index(metric)]['QMFRank']})
    if not summaries: return
    s.atomic_csv(s.OUT/'QMF_CROSS_DATASET_SUMMARY.csv',summaries)
    s.atomic_csv(s.OUT/'QMF_RANKS.csv',rankrows)
    s.atomic_csv(s.OUT/'ALL_DATASETS_ALL_METHODS_7_METRICS.csv',allrows)
    s.atomic_csv(s.OUT/'QMF_VS_BEST_BASELINE.csv',comparisons)
    def mdtable(values):
        fields=list(values[0]); return '| '+' | '.join(fields)+' |\n|'+'|'.join(['---']*len(fields))+'|\n'+''.join('| '+' | '.join(fmt(r.get(k)) for k in fields)+' |\n' for r in values)
    body=mdtable(summaries)+'\n'+mdtable(rankrows)+'\n'
    for i,row in enumerate(inventory):
        if s.marker(row['dataset_id'],'results_persisted').exists(): body+='\n'+NAMES[i]+'\n\n'+table(rows(row['dataset_id']))
    text(s.OUT/'QMF_CROSS_DATASET_SUMMARY.md',body)
    text(s.ROOT/'FOUR_DATASET_PAPER_METRICS_20260911.md',body)
