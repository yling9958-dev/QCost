#!/usr/bin/env python3
"""Record actual source-copy identities and function AST comparisons for this assembly."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    original = a.source_root.resolve()
    groups = []
    for name in ['src/python/qmapli','src/python/hybrid_qmf','src/python/qcost_experiments/ablation',
                 'src/python/qcost_experiments/selection','src/cpp','src/postgres','models','references']:
        files = [f for f in (original/name).rglob('*') if f.is_file() and '__pycache__' not in f.parts]
        # The added postgres/client directory has no counterpart in the old root.
        matches = [dict(path=f.relative_to(original).as_posix(), sha256=sha(f)) for f in files
                   if (ROOT/f.relative_to(original)).is_file() and sha(f)==sha(ROOT/f.relative_to(original))]
        assert len(matches) == len(files), name
        groups.append(dict(original=name, released=name, files=len(files), byte_identical=True, identities=matches))
    mappings = {
        'reproduce/select_frozen_nodes.py': '../QMF-Motivation-Study/experiments/census.py',
        'src/python/qcost_experiments/comparison/comparison_adapter.py': 'hybrid_qmf_ablation/02_code/src/comparison_adapter.py',
        'src/python/qcost_experiments/comparison/controlled_builder.py': 'hybrid_qmf_ablation/02_code/src/controlled_builder.py',
        'src/python/qcost_experiments/comparison/four_strategies.py': 'hybrid_qmf_ablation/02_code/vendor/build_index.py',
        'src/python/qcost_experiments/comparison/standalone_search.py': 'hybrid_qmf_ablation/02_code/vendor/python/qmapli/wg_qmf/search.py',
        'src/python/qcost_experiments/comparison/work_observer.py': 'hybrid_qmf_ablation/02_code/src/work_observer.py',
        'src/python/qcost_experiments/comparison/memory_metrics.py': 'hybrid_qmf_ablation/02_code/src/memory_metrics.py',
        'src/python/qcost_experiments/comparison/formal_beam.py': '../QMF-Motivation-Study/experiments/search_worker.py',
        'src/postgres/client/postgres_full.cpp': 'submission_release/Q_COST_ICDE2027_Code_Repro_20261025/code/fullscale/original_paper_controller/postgres_full.cpp',
        'src/postgres/client/flood_memory_trace.hpp': 'submission_release/Q_COST_ICDE2027_Code_Repro_20261025/code/fullscale/original_paper_controller/flood_memory_trace.hpp'
    }
    for path in (ROOT/'src/python/qmf_quantum').glob('*.py'):
        key = path.relative_to(ROOT).as_posix()
        mappings[key] = ('../QMF-Quantum-Circuit/experiments/run_stage.py' if path.name=='stage_validation.py'
                         else '../QMF-Quantum-Circuit/src/qmf_quantum/'+path.name)
    restored=[]
    for target, source in mappings.items():
        old,new = original/source,ROOT/target
        row = dict(source=source,released=target,source_sha256=sha(old),released_sha256=sha(new),
                   byte_identical=old.read_bytes()==new.read_bytes())
        if new.suffix=='.py':
            def functions(path):
                return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body
                        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
            before,after=functions(old),functions(new)
            row['common_function_or_class_AST_identity']={n:before[n]==after[n] for n in sorted(before.keys() & after.keys())}
        restored.append(row)
    resource_groups=[]
    for released,source in [
        ('experiments/plotting/section4_2','submission_release/Q_COST_ICDE2027_Code_Repro_20261025/plots/section4_2'),
        ('experiments/plotting/section4_3_4_4','submission_release/Q_COST_ICDE2027_Code_Repro_20261025/plots/section4_3_4_4'),
        ('experiments/plotting/section4_5_4_6','submission_release/Q_COST_ICDE2027_Code_Repro_20261025/plots/section4_5_4_6'),
        ('experiments/plotting/revised','bestfirst_removal_revision')]:
        records=[]
        for path in sorted((ROOT/released).rglob('*')):
            if path.is_file():
                old=original/source/path.relative_to(ROOT/released)
                assert old.is_file() and sha(old)==sha(path), old
                records.append(dict(file=path.relative_to(ROOT).as_posix(),sha256=sha(path)))
        resource_groups.append(dict(source=source,released=released,files=records))
    result=dict(status='PASS',source_root=str(original),
        canonical_byte_identical_groups=groups, restored_sources=restored,
        historical_plot_inputs=resource_groups,
        ports='Imports and project-relative model paths replace historical machine paths. Stage gate wrapper removes old guard-receipt deployment paths; scientific loops remain original. AST results identify any edited function bodies for review.',
        readme_consolidation='Original root, fullscale/data/recovery/baseline, quantum, plotting and current ablation/selection instructions consolidated into the sole root README. Superseded reports, unrelated dependencies and presentation documents are excluded.',
        source_selection='Current source plus final 2026-10-25 submission/BestFirst-removal exports. Removed BestFirst is not relabelled Random. Sibling motivation and quantum projects are followed original dependencies, now restored locally.',
        exclusions='Original files remain in place. Copies exclude full raw data, derived node payloads without established redistribution rights, duplicate outputs, logs, images, caches, binaries, archives, editor settings, secrets and Git history.')
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='PASS',canonical_groups=len(groups),restored_files=len(restored),plot_groups=len(resource_groups))))

if __name__=='__main__':
    main()
