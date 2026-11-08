"""Reconstruct existing observations only; no benchmark/build is executed.

prepare_data.py is the retained, validated extraction logic. The extension
keeps user-supplied aggregates distinct from verified raw observations.
"""
from pathlib import Path
import hashlib
import json
import pandas as pd
import numpy as np
import prepare_data as audit

OUT = Path(__file__).resolve().parents[1]

def main():
    audit.main()
    for n in range(1,5):
        audit.raw(OUT.parent/f'{n}.png')
    for r in pd.read_csv(OUT/'reports/latex_source_inventory.csv').itertuples():
        audit.raw(r.path)
    pd.DataFrame(audit.SOURCE.values()).to_csv(OUT/'reports/source_sha256.csv',index=False)
    f = pd.read_csv(OUT/'data/fullscale_results.csv')
    f['verification_status'] = np.where(f.status.eq('PASS'), 'RAW_VERIFIED', 'NO_COMPLETED_RAW_RUN')
    f['verified_for_plot'] = f.status.eq('PASS')
    # Only confirmed target metrics are revised. Legacy import labels are retained;
    # current provenance is in FLOOD_SKEWED_REAL_RESULT_UPDATE.md and its source receipt.
    supplied = {
        'provenance_type': 'user_supplied_summary',
        'source': 'User message: Section 4.2 Figures 6-9 redesign, received 2026-10-20',
        'method': 'Flood-V2', 'dataset': 'Skewed 2D', 'point_count': 204986702,
        'build_s': 153.381455, 'index_size_mib': None, 'mean_ms': 199.713213,
        'p95_ms': 715.018688, 'p99_ms': 4286.059673, 'reported_qps': 5.007180,
        'peak_memory_mib': 16535.820313,
        'verification_status': 'UNVERIFIED_RAW_RECORDS_NOT_LOCATED',
        'timing_observations_verified': 15000, 'correctness_observations_verified': 1000,
        'correctness': '1000/1000 passed', 'warmup_queries': 300, 'measurement_rounds': 5,
    }
    supplied['derived_qps'] = 1000/supplied['mean_ms']
    supplied['reported_qps_matches_rounding'] = round(supplied['derived_qps'],6)==supplied['reported_qps']
    p = OUT/'data/user_supplied_flood_skewed_summary.json'
    p.write_text(json.dumps(supplied, indent=2)+'\n')
    mask = f.dataset.eq('Skewed 2D') & f.method.eq('Flood') & f.point_count.eq(204986702)
    assert mask.sum() == 1
    old = f.loc[mask].copy()
    old.to_csv(OUT/'data/flood_skewed_retained_failed_attempt.csv',index=False)
    f['previous_attempt_status'] = ''
    f['previous_attempt_source_file'] = ''
    f.loc[mask,'previous_attempt_status'] = old.status.iloc[0]
    f.loc[mask,'previous_attempt_source_file'] = old.source_file.iloc[0]
    for key in ['mean_ms','p95_ms','p99_ms','build_s']:
        f.loc[mask,key] = supplied[key]
    f.loc[mask,'qps'] = supplied['reported_qps']
    f.loc[mask,'timing_observations'] = supplied['timing_observations_verified']
    f.loc[mask,'correctness_observations'] = supplied['correctness_observations_verified']
    f.loc[mask,'status'] = 'USER_SUPPLIED_SUMMARY'
    f.loc[mask,'verification_status'] = supplied['verification_status']
    f.loc[mask,'correctness_status'] = supplied['correctness']
    f.loc[mask,'correctness_scope'] = 'NO_MATCHING_CORRECTNESS_LOG'
    f.loc[mask,'source_file'] = str(p)
    f.loc[mask,'summary_file'] = str(p)
    f.loc[mask,'attempt_id'] = 'USER_SUPPLIED_NO_RUN_ID'
    f.loc[mask,'implementation_version'] = 'Flood-V2 (user-supplied name; exact revision unverified)'
    f.loc[mask,'failure_reason'] = 'User aggregate retained; matching raw timing/correctness/receipt not found. Older failed attempt preserved separately.'
    # A later unverified summary must not inherit hashes from an older failed run.
    f.loc[mask,['dataset_sha256','query_sha256','protocol_sha256','environment_id']] = ''
    f.to_csv(OUT/'data/fullscale_results.csv',index=False)
    f[f.verified_for_plot].to_csv(OUT/'data/fullscale_verified_results.csv',index=False)
    fastest=[]
    for ds,g in f[f.verified_for_plot].groupby('dataset',sort=False):
        q=g[g.method=='Q-COST'].iloc[0]; c=g[g.method!='Q-COST'].sort_values('mean_ms').iloc[0]
        fastest.append(dict(dataset=ds,competitor=c.method,qcost_mean_ms=q.mean_ms,
            competitor_mean_ms=c.mean_ms,speedup=c.mean_ms/q.mean_ms,
            valid_competitors=len(g)-1,comparison_scope='raw-verified completed systems',
            qcost_source=q.source_file,competitor_source=c.source_file))
    pd.DataFrame(fastest).to_csv(OUT/'data/fastest_competitor_speedups.csv',index=False)
    b=f[['dataset','method','point_count','build_s','status','verification_status','summary_file']].copy()
    b['construction_hours']=b.build_s/3600
    b['included_in_fig8a']=b.method.eq('Q-COST') & b.status.eq('PASS')
    b['comparison_scope']='Different system build/load/export boundaries; no cross-method ranking'
    b.to_csv(OUT/'data/construction_results.csv',index=False)
    pd.read_csv(OUT/'data/storage_scope.csv').to_csv(OUT/'data/storage_results.csv',index=False)
    w=pd.read_csv(OUT/'data/workload_statistics.csv')
    w['source_pairs']='workload_build_pairs.csv'
    w.to_csv(OUT/'data/workload_area_results.csv',index=False)
    assert ((w[w.method=='Q-COST'].ci95_low<=1)&(w[w.method=='Q-COST'].ci95_high>=1)).all()
    manifest=pd.read_csv(OUT/'reports/source_sha256.csv')
    manifest['source_kind']='retained_original_file'
    manifest['verification_status']='SHA256_RECORDED'
    extra=dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size,
               mtime_ns=p.stat().st_mtime_ns,source_kind='user_supplied_summary',verification_status='NOT_RAW_VERIFIED')
    pd.concat([manifest,pd.DataFrame([extra])],ignore_index=True).to_csv(OUT/'data/provenance.csv',index=False)
    print(pd.DataFrame(fastest)[['dataset','competitor','speedup']].to_string(index=False))
    print('Coverage: 27 raw-verified + 1 unverified user summary. QPS rounding check:',supplied['reported_qps_matches_rounding'])

if __name__=='__main__': main()
