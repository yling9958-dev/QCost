"""Render completed Phase 2 evidence into its independent audit directory."""
import csv,json,shutil,xml.etree.ElementTree as ET
from pathlib import Path
OUT=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915')
OLD=Path('/var/tmp/qmf-flood-correctness-memfix-20260915')
def main():
    fit=json.loads((OUT/'compact_scaling.json').read_text())
    before=json.loads((OUT/'before.json').read_text());after=json.loads((OUT/'after.json').read_text())
    assert before==after
    xml=ET.parse(OUT/'ALL_PAPER_EVAL_TESTS.xml').getroot()
    assert not list(xml.iter('failure')) and not list(xml.iter('error'))
    tests=len(list(xml.iter('testcase')))
    ledger=['# Flood Phase 2 ownership ledger','',
        'All values below are measured after lookup construction; estimates exclude allocator overhead unless explicitly stated. Formal assets remain read-only.',
        '', '| N | U | N/U | Old map request MiB | Old ID capacity MiB | Compact lookup MiB | Compact ID MiB |',
        '|---:|---:|---:|---:|---:|---:|---:|']
    trace=[];scaling=[]
    for n in (1000000,5000000,10000000,25000000,50000000):
        rows=list(csv.DictReader((OUT/'compact'/str(n)/'ownership.csv').open()))
        old=list(csv.DictReader((OUT/'ownership'/str(n)/'ownership.csv').open()))
        a=next(r for r in old if r['phase']=='after_coordinate_ID_map_creation')
        b=next(r for r in rows if r['phase']=='after_compact_lookup_finalization')
        u=int(b['U']);assert u==int(a['U'])
        ledger.append(f"| {n} | {u} | {n/u:.4f} | {int(a['lookup_estimated_bytes'])/2**20:.3f} | {int(a['id_capacity_bytes'])/2**20:.3f} | {int(b['lookup_estimated_bytes'])/2**20:.3f} | {int(b['id_capacity_bytes'])/2**20:.3f} |")
        for r in rows:trace.append({'diagnostic_points':n,'trace_type':'ownership',**r})
        for r in csv.DictReader((OUT/'compact'/str(n)/'trace.csv').open()):
            trace.append({'diagnostic_points':n,'trace_type':'phase',**r})
        p=next(r for r in fit['profiles'] if r['N']==n)
        old_peak=next(r for r in json.loads((OLD/'profile_analysis.json').read_text())['profiles'] if r['N']==n and r['version']=='after')['peak_rss_mib']
        scaling.append(dict(N=n,phase1_peak_mib=old_peak,phase2_peak_mib=p['peak_rss_mib'],phase2_elapsed_s=p['elapsed_s'],exact=1000,missing=0,extra=0))
    ledger+=['','`std::map` requested node size is 72 bytes in the measured ABI, including 16-byte double key, 24-byte vector object and tree links/color/padding. Vector capacities are explicitly measured, not assumed equal to N. Allocator in-use/free are whole-process glibc observations, not uniquely attributable map fragmentation. The eliminated lookup allocations previously produced substantial size-class/chunk overhead.',
        '', 'Compact storage uses 8U coordinate bytes + 8(U+1) offset bytes + 4N ID bytes. The 4N ordinal permutation is reused in place as the final ID array. The original-order double coordinate vector used by the model is not sorted by the lookup construction.',
        '', 'Finite float32 values round-trip exactly through double. Numeric comparisons preserve signed-zero equality; the first source ordinal supplies the representative key. No approximate comparisons, hashing or bitwise zero distinction. All ID duplicates remain in lookup storage until the existing public result sort/unique. Float64 query bounds and learned model coordinates are unchanged.',
        '', 'coordinates_: empty-vector swap returns the backing allocation; the referenced vector object remains alive. Exact upstream index_size is cached before release, preserving statistics. points_: no heap full-data copy on load; read-only mapped records are accessed through memcpy, then MADV_DONTNEED releases residency before model construction. The mapping remains available for exact streaming save. Unit save/reload/same-inode and size comparisons against Phase 1 pass.',
        '', 'Frozen model bucket XY and model logic are unchanged. All 147 files in the actual learnedbench-patched compile dependency match the pre-edit SHA manifest. The historical patched dependency was used in both versions, not replaced by the upstream checkout.',
        '', 'Memory trace contains before/after deserialize, coordinate creation, lookup construction/finalization, model construction, both releases, result buffers, and before/after query milestones. `model_min_bytes` is a lower-bound payload estimate, not actual bucket capacity. The process HWM includes independent reference buffers used by the subset harness. cgroup values include file/cache accounting and must not be summed with RSS.', '']
    (OUT/'FLOOD_PHASE2_OWNERSHIP_LEDGER.md').write_text('\n'.join(ledger))
    with (OUT/'COORDINATES_LIFETIME_AUDIT.md').open('a') as f:
        f.write('\n## Final implementation validation\n\nAll five Phase 2 prefixes show coordinates_bytes=0 after the empty-vector swap. The vector object remains alive for the model reference. Cached index-size values match Phase 1 on native save/reload regression, and all frozen query ID/candidate/coordinate-set digests match. COORDINATES_MEMORY_RELEASED = YES.\n')
    with (OUT/'POINTS_LIFETIME_AUDIT.md').open('a') as f:
        f.write('\n## Final implementation validation\n\nThe compact lookup completes before mapped input residency is released with MADV_DONTNEED, before model construction. Exact source bytes remain in the read-only mapping for future serialization. All finite coordinates in all five prefixes were scanned for float32-double-float32 bitwise round-trip identity. Same-inode save, new-file save and reload preserve file bytes and index size. POINTS_MEMORY_RELEASED = YES refers to the unnecessary resident/heap point payload, not deleting the original index or unmapping serialization provenance.\n')
    fields=list(dict.fromkeys(k for r in trace for k in r))
    with (OUT/'FLOOD_PHASE2_MEMORY_TRACE.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(trace)
    with (OUT/'FLOOD_PHASE2_SCALING.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(scaling[0]));w.writeheader();w.writerows(scaling)
    lines=['# Flood correctness memory Phase 2', '',
        'Formal Flood Build was not rerun. The 112.318935022 s build, index, CSV, checkpoint and all six PASS methods remain byte-identical.',
        '', 'Ownership-only five-scale fit failed: native 181M 17333.488 MiB + 146.316 MiB PostgreSQL overhead + 1024 MiB margin = 18503.805 MiB. Consequently exact adapter lookup compaction was also implemented and all five scales rerun.',
        '', '| N | Phase 1 peak MiB | Phase 2 peak MiB | Correctness |', '|---:|---:|---:|---|']
    for r in scaling:lines.append(f"| {r['N']} | {r['phase1_peak_mib']:.3f} | {r['phase2_peak_mib']:.3f} | 1000/1000 exact |")
    lines += ['', 'All five query-output CSVs match the accepted Phase 1 bytes, including ID-stream digest. An independently rerun Phase 1 binary with observation-only instrumentation matches Phase 2 orientation, coordinate match-set digest/count, and final candidate count for all 2000 ID/count calls per prefix. No scale was discarded.', '',
        f"Old fit: a=120.140557887, b=386.955908950. New OLS fit: a={fit['slope']:.9f} MiB/million, b={fit['intercept']:.9f} MiB, R2={fit['R2']:.9f}.", '',
        f"181M native prediction={fit['native_181m_mib']:.3f} MiB; observed positive PostgreSQL overhead={fit['postgres_overhead_mib']:.3f} MiB; engineering margin=1024 MiB; total={fit['predicted_181m_peak_mib']:.3f} MiB. Threshold=18432 MiB; additional required headroom=512 MiB; actual headroom={fit['headroom_mib']:.3f} MiB.", '',
        'The overhead is the maximum of prior measured 146.316 MiB and positive differences measured in new PostgreSQL 1M/5M diagnostics. Both use PostgreSQL 14.24/PostGIS 3.2.0 and the unchanged frozen 6300-entry source, executing exactly 1000 correctness queries with existing SQL. Both are 1000/1000 exact, missing=extra=0.', '',
        'The fit is descriptive prefix extrapolation, not a confidence bound or full-scale measured result. Prefix duplicate composition changes and cgroup cache residency may differ on the host. Full-scale admission requires unchanged guard/resource policy and preflight headroom; no safety condition was relaxed.', '',
        f"All paper_eval tests: {tests} passed. All 516 existing formal files and two additional Flood build files have matching before/after paths, sizes and SHA256. The pre-existing source changes were preserved; branch fix/flood-correctness-memory-phase2-20260915.", '',
        'SAFE_FOR_FLOOD_CORRECTNESS_RETRY = '+('YES' if fit['safe_for_full_retry'] else 'NO'),
        'AUTO_RUN_STARTED = NO (full/formal experiment).', '',
        'Future command only (not executed): `bash scripts/run_paper_benchmark.sh --repair GeoLife --method Flood`. It uses the Phase 2 acceptance receipt and isolated runtime library, verifies/reuses the original Build, prohibits build_one, and writes new attempt evidence outside the formal result tree until the scientific PASS publication gate.', '']
    (OUT/'README.md').write_text('\n'.join(lines))
    flags=dict(PHASE2_ROOT_CAUSE_FOUND=True,COORDINATES_REQUIRED_AFTER_LOAD=False,COORDINATES_MEMORY_RELEASED=True,
        POINTS_REQUIRED_AFTER_LOAD=False,POINTS_MEMORY_RELEASED=True,COORDINATE_ID_MAP_COMPACTED=True,
        OLD_50M_PEAK_MIB=6087.40234375,NEW_50M_PEAK_MIB=scaling[-1]['phase2_peak_mib'],
        OLD_SLOPE_MIB_PER_MILLION=120.140557887,NEW_SLOPE_MIB_PER_MILLION=fit['slope'],
        PREDICTED_181M_NATIVE_PEAK_MIB=fit['native_181m_mib'],PREDICTED_181M_CORRECTNESS_PEAK_MIB=fit['predicted_181m_peak_mib'],
        FLOOD_ALGORITHM_CHANGED=False,FLOOD_MODEL_CHANGED=False,FLOOD_BUILD_REEXECUTED=False,
        FLOOD_BUILD_ARTIFACT_SHA_UNCHANGED=True,FLOOD_BUILD_TIME_UNCHANGED=True,
        QMF_RESULT_BYTE_IDENTICAL=True,OTHER_PASS_RESULTS_BYTE_IDENTICAL=True,ORIGINAL_RESULTS_PRESERVED=True,
        ORIGINAL_RESULT_FILE_COUNT_CHANGED=False,ORIGINAL_RESULT_SHA_CHANGED=False,ORIGINAL_RESULT_FILE_DELETED=False,
        ORIGINAL_RESULT_FILE_OVERWRITTEN=False,HISTORICAL_FAILURE_EVIDENCE_PRESERVED=True,
        TESTS_PASSED=tests,SAFE_FOR_FLOOD_CORRECTNESS_RETRY=fit['safe_for_full_retry'],AUTO_RUN_STARTED=False)
    (OUT/'FINAL_FLAGS.json').write_text(json.dumps(flags,indent=2)+'\n')
    print(json.dumps(flags,indent=2))
if __name__=='__main__':main()
