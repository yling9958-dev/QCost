"""Allowlisted code/measurement export. Never copies point or workload datasets."""
from pathlib import Path
import hashlib, json, shutil, subprocess, zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).parent / 'Q_COST_ICDE2027_Code_Repro_20261025'
LEDGER = []

def digest(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()

def copy(source, target=None, category='source'):
    source = Path(source)
    if not source.is_absolute(): source = ROOT / source
    assert source.is_file() and not source.is_symlink(), source
    target = OUT / (target if target is not None else source.relative_to(ROOT))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    LEDGER.append(dict(source=str(source), packaged=str(target.relative_to(OUT)),
                       source_sha256=digest(source), category=category))

def tree(source, target, suffixes, category='source'):
    source = ROOT / source
    for p in sorted(source.rglob('*')):
        if '__pycache__' not in p.parts and p.is_file() and p.suffix in suffixes:
            copy(p, Path(target) / p.relative_to(source), category)

def main():
    OUT.mkdir(exist_ok=False)
    base = 'QMF_PostGIS_100M_Repro_20260910'
    for folder in ['src','config','third_party','environment','docs','tests']:
        tree(f'{base}/{folder}', f'code/fullscale/{folder}',
             {'.py','.cpp','.hpp','.h','.c','.sql','.control','.pt','.yaml','.yml',
              '.txt','.lock','.md','.sh','.csv','.json','.patch','.repro',''}, 'production source/config')
    for f in ['CMakeLists.txt','Makefile']:
        for p in (ROOT/base/'src').rglob(f):
            dst=OUT/'code/fullscale/src'/p.relative_to(ROOT/base/'src')
            if not dst.exists(): copy(p,dst.relative_to(OUT))
    for name in ['common.sh','03_fetch_baselines.sh','04_build_all.sh','prepare_bmtree_worktree.sh']:
        copy(f'{base}/scripts/{name}',f'code/fullscale/scripts/{name}')
    copy(f'{base}/LICENSES.md','LICENSES.md','licensing')
    tree('scripts/paper_eval','code/fullscale/original_paper_controller',{'.py','.cpp','.hpp'},'historical controller source')
    for source,target in [('qmf_random_ablation_revision/02_code','code/hybrid'),
                          ('qmf_selection_diagnostics/01_code_audit','code/selection')]:
        for folder in ['src','vendor']:
            tree(f'{source}/{folder}',f'{target}/{folder}',{'.py'})
    for s,t in [('qmf_random_ablation_revision/02_code/run_random.py','code/original_drivers/run_random.py'),
                ('hybrid_qmf_ablation/02_code/run_ablation.py','code/original_drivers/run_ablation_historical.py'),
                ('qmf_random_ablation_revision/02_code/analyze_random.py','code/analysis/analyze_random.py'),
                ('qmf_selection_diagnostics/08_reproduce/analyze.py','code/analysis/analyze_selection.py'),
                ('qmf_selection_diagnostics/08_reproduce/prepare_nodes.py','code/original_drivers/prepare_nodes.py'),
                ('qmf_selection_diagnostics/08_reproduce/run_diagnostics.py','code/original_drivers/run_diagnostics.py')]: copy(s,t)
    with zipfile.ZipFile(ROOT/'QMF_gate_level_prototype.zip') as z:
        for name in z.namelist():
            assert '/' not in name
            dest=OUT/'code/gate_prototype'/name;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(z.read(name))
            LEDGER.append(dict(source='QMF_gate_level_prototype.zip::'+name,packaged=str(dest.relative_to(OUT)),
                               source_sha256=digest(dest),category='gate source'))
    copy(f'{base}/config/r4.pt','models/r4.pt','trained scorer (not a dataset)')
    # Only recovery recipes and identities, not the frozen CSV or frozen queries.
    for name in ['README.md','LICENSE_DATASET.md','dataset_manifest.csv','dataset_manifest.json',
                 'normalized_hashes.json','expected_dataset.sha256','fetch_geolife.sh','verify_geolife_100m.sh',
                 'recovery/README.md','recovery/fetch_geolife.sh','recovery/verify_source.sh','recovery/geolife_plt_order.txt']:
        copy(f'{base}/data/{name}',f'external_inputs/geolife_legacy_recipe/{name}','data recovery recipe/identity')
    copy('scripts/paper_eval/paper_protocol.py','external_inputs/fullscale_protocol.py','protocol')
    for name in ['main40.json','phase4_frozen.json','node_inventory.json','T_EXACT_RAW_MEASUREMENTS.csv','requirements_frozen.txt']:
        copy(f'hybrid_qmf_ablation/01_audit/{name}',f'configs/{name}','protocol/identity')
    for source,target in [('hybrid_qmf_ablation/06_reports/ABLATION_PROTOCOL.md','protocols/ORIGINAL_ABLATION_PROTOCOL.md'),
                          ('qmf_random_ablation_revision/01_audit/QMF_RANDOM_PROTOCOL.md','protocols/RANDOM_ABLATION_PROTOCOL.md'),
                          ('qmf_selection_diagnostics/01_code_audit/FROZEN_PROTOCOL.md','protocols/SELECTION_DIAGNOSTICS_PROTOCOL.md'),
                          ('qmf_selection_diagnostics/01_code_audit/FROZEN_NEW_NODE_ORDER.json','configs/FROZEN_NEW_NODE_ORDER.json'),
                          ('qmf_random_ablation_revision/03_runs/formal/manifest.json','provenance/random_run_manifest.json'),
                          ('hybrid_qmf_ablation/03_runs/formal/manifest.json','provenance/original_ablation_run_manifest.json')]: copy(source,target,'protocol/provenance')
    original_nodes=json.loads((ROOT/'qmf_selection_diagnostics/01_code_audit/NODE_MANIFEST.json').read_text())
    nodes=[]
    for original in original_nodes:
        node=dict(original);ref=Path(node['Reference_File'])
        assert digest(ref)==node['Reference_SHA256']
        copy(ref,f'references/{node["Node_ID"]}.json','offline exact answer')
        node['Input_File']=f'{node["Node_ID"]}/input.npz'
        node['Reference_File']=f'references/{node["Node_ID"]}.json'
        nodes.append(node)
    (OUT/'configs/NODE_MANIFEST.json').write_text(json.dumps(nodes,indent=2)+'\n')
    (OUT/'configs/seeds.json').write_text(json.dumps(list(range(2026101100,2026101130)))+'\n')
    # Scalar measurement records are results, not point or query workloads.
    tree('qmf_random_ablation_revision/04_metrics','results/ablation',{'.csv','.json'},'measured results')
    copy('qmf_random_ablation_revision/QMF_RANDOM_ABLATION_SUMMARY.csv','results/ablation/REFERENCE_SUMMARY.csv','measured results')
    copy('qmf_random_ablation_revision/ABLATION_TABLE_FIVE_VARIANTS.tex','tables/ABLATION_TABLE_FIVE_VARIANTS.tex','paper table')
    for p in sorted((ROOT/'qmf_selection_diagnostics/03_metrics').glob('*')):
        if p.is_file() and p.suffix in ['.csv','.json']:
            copy(p,'results/selection/'+p.name,'measured results')
    copy('qmf_selection_diagnostics/04_tables/QMF_SELECTION_TABLE.tex','tables/QMF_SELECTION_TABLE.tex','paper table')
    copy('qmf_random_ablation_revision/QMF_RANDOM_ABLATION_REPORT.md','reports/RECORDED_ABLATION_REPORT.md','recorded interpretation')
    copy('qmf_selection_diagnostics/06_reports/QMF_SELECTION_FINAL_REPORT.md','reports/RECORDED_SELECTION_REPORT.md','recorded interpretation')
    groups=[('figures_sec4_2','plots/section4_2',[6,7,8,9],
             ['fullscale_results.csv','fullscale_latency_observations.csv','fig6_ecdf_steps.csv',
              'fig6_ecdf_statistics.csv','construction_results.csv','storage_results.csv',
              'workload_build_pairs.csv','workload_area_results.csv']),
            ('figures_sec4_3_4_4','plots/section4_3_4_4',[10,11],
             ['fig10_latency_summary.csv','fig10_root_summary.csv','fig11_summary.csv']),
            ('figures_sec4_5_4_6','plots/section4_5_4_6',[14,15],
             ['gate_validation_results.csv','circuit_complexity.csv','parameter_sensitivity.csv'])]
    for source,target,figs,data in groups:
        for script in ['plot_style.py','layout_tools.py']+[f'plot_fig{i}.py' for i in figs]:
            copy(f'{source}/scripts/{script}',f'{target}/scripts/{script}')
        for f in data: copy(f'{source}/data/{f}',f'{target}/data/{f}','plot measurements')
    for script in ['plot_style.py','layout_tools.py']+[f'regenerate_fig{i}.py' for i in [12,13,16]]:
        copy(f'bestfirst_removal_revision/08_reproduce/{script}',f'plots/revised/08_reproduce/{script}')
    for f in ['FIG12_REVISED_DATA.csv','FIG13_REVISED_DATA.csv','FIG16_REVISED_DATA.csv','ORIGINAL_AXIS_LIMITS.json']:
        copy(f'bestfirst_removal_revision/02_plot_data/{f}',f'plots/revised/02_plot_data/{f}','plot measurements')
    copy('qmf_selection_diagnostics/08_reproduce/plot_results.py','plots/selection/08_reproduce/plot_results.py')
    for f in ['QMF_SELECTION_METRICS.csv','FIRST_OPTIMAL_DISTRIBUTION.csv']:
        copy(f'qmf_selection_diagnostics/03_metrics/{f}',f'plots/selection/03_metrics/{f}','plot measurements')
    (OUT/'provenance/SOURCE_FILES.json').write_text(json.dumps(LEDGER,indent=2)+'\n')
    git=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             working_tree='Uncommitted changes included as inspected; file hashes, not commit alone, identify this export.')
    (OUT/'provenance/GIT_SNAPSHOT.json').write_text(json.dumps(git,indent=2)+'\n')
    print(json.dumps(dict(output=str(OUT),source_files=len(LEDGER),bytes=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()))))

if __name__=='__main__':main()
