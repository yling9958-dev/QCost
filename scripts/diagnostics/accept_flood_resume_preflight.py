"""Append a controller-only acceptance amendment without rewriting Phase 2 evidence."""
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/paper_eval'))
import flood_resume as f
import run
import support as s

OUT=Path('/var/tmp/qmf-flood-resume-preflight-20260915')

def main():
    original=f.AUDIT/'acceptance.json'
    old=s.read_json(original)
    destination=f.AUDIT/'acceptance_resume_preflight_20260915.json'
    if destination.exists():raise RuntimeError('Do not overwrite a prior receipt')
    allowed={str(ROOT/'scripts/paper_eval'/name) for name in ['flood_resume.py','run.py']}
    for category in ['source_files','runtime_files','evidence_files']:
        for path,digest in old[category].items():
            if category=='source_files' and path in allowed:continue
            assert s.sha(path)==digest,(category,path)
    assert s.sha(OUT/'run_before.py')==old['source_files'][str(ROOT/'scripts/paper_eval/run.py')]
    # Recover the pre-fix controller from its preserved Phase 1 source and the
    # exact Phase 2 changes. The prior receipt SHA proves the recovered bytes.
    before=(f.AUDIT/'phase1_flood_resume.py').read_text()
    before=before.replace("AUDIT=Path('/var/tmp/qmf-flood-correctness-memfix-20260915')", "AUDIT=Path('/var/tmp/qmf-flood-correctness-memfix-phase2-20260915')")
    before=before.replace("results/flood_correctness_memfix_20260915/attempts", "results/flood_correctness_memfix_phase2_20260915/attempts")
    before=before.replace('def validate_build():', '''def runtime_path(target):
    # UNIX socket paths must remain below sockaddr_un's 108-byte limit.
    return Path('/var/tmp')/('qmf-flood-p2-'+target.name[-16:])

def validate_build():''')
    before=before.replace("runtime=target/'runtime';common=runtime/'common'", "runtime=runtime_path(target);common=runtime/'common'")
    before=before.replace("    common.mkdir(parents=True)\n", "    common.mkdir(parents=True)\n    (target/'runtime').symlink_to(runtime,target_is_directory=True)\n")
    before=before.replace("str(target/'runtime/common/pg_data')", "str(runtime_path(target)/'common/pg_data')")
    assert hashlib.sha256(before.encode()).hexdigest()==old['source_files'][str(ROOT/'scripts/paper_eval/flood_resume.py')]
    with (OUT/'flood_resume_before.py').open('x') as handle:handle.write(before)
    tests=OUT/'pre_acceptance_tests.xml'
    assert run.passing_test_xml(tests)
    gate=copy.deepcopy(old)
    gate['scope']=old['scope']+'; exFAT-compatible attempt path receipt and preflight logging'
    gate['source_files'].update({path:s.sha(path) for path in allowed})
    for name in ['diagnose_flood_resume.py','test_flood_resume_preflight.py']:
        path=ROOT/'scripts/paper_eval'/name;gate['source_files'][str(path)]=s.sha(path)
    gate['evidence_files'].update({str(path):s.sha(path) for path in
        [original,tests,OUT/'before.json',OUT/'flood_resume_before.py',OUT/'run_before.py',
         f.AUDIT/'resume_fix_before.json']})
    gate['tests_path']=str(tests)
    gate['archive_verification_path']=str(OUT/'archive_verification.json')
    gate['preflight_amendment']={'parent_receipt':str(original),'parent_sha256':s.sha(original),
        'changed_controller_sources':sorted(allowed),'algorithm_or_model_changes':False,
        'reason':'exFAT cannot create symbolic links; persist plain JSON runtime path instead'}
    with destination.open('x') as handle:json.dump(gate,handle,indent=2);handle.write('\n')
    f.verify_gate()
    print('Controller amendment accepted; original Phase 2 receipt retained')

if __name__=='__main__':main()
