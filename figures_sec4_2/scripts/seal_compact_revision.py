"""Package only the current compact revision, preserving prior delivery archives."""
from pathlib import Path
import hashlib,json,zipfile
OUT=Path(__file__).resolve().parents[1]
NAMES=['fig6_latency_ecdf','fig7_grouped_bar','fig8_construction_storage','fig9_latency_reduction','fig9_relative_latency_zoom']
def main():
    files=[]
    files += [OUT/'figures'/f'{n}.{e}' for n in NAMES for e in ['pdf','svg','png']]
    files += [OUT/'figures/fig9_comparison.png']
    scripts=['plot_style','layout_tools','plot_fig6','plot_fig7','plot_fig8','plot_fig9',
             'write_layout_revision','check_compact_revision','preview_and_check','render_svg','archive_current','seal_compact_revision']
    files += [OUT/'scripts'/f'{n}.py' for n in scripts]
    files += [OUT/'data'/n for n in ['fullscale_results.csv','fullscale_plot_accepted.csv','fullscale_latency_observations.csv',
              'construction_results.csv','storage_results.csv','workload_build_pairs.csv','workload_area_results.csv',
              'fig6_ecdf_steps.csv','fig7_speedups_28_pairs.csv','fig7_current_plotted_values.csv',
              'fig9_current_statistics.csv','fig9_current_paired_builds.csv']]
    for stem in ['section4_2_figures_revised','fig9_version_B_alternative','section4_2_body_revisions',
                 'section4_2_figures_layout_preview','section4_2_figures_three_widths']:
        files += list((OUT/'latex').glob(stem+'.*'))
    reports=['compact_layout_check.md','manual_visual_review_compact.md','layout_revision_data_audit.md',
        'layout_revision_integrity.md','compact_export_checks.csv','layout_revision_protection_before.csv',
        'layout_revision_protection_after.csv','fig7_bar_style_audit.csv','flood_confirmation_revision.json']
    files += [OUT/'reports'/n for n in reports]
    for pat in ['*_compact_layout.json','fig7_current_data_check.json','fig9_*_data_check.json','fig*_compact_run.log',
                '*_current_pdf_fonts.txt','compact_quality_run.log']:
        files += list((OUT/'reports').glob(pat))
    files += [f for f in (OUT/'reports/compact_previews').glob('*') if f.is_file()]
    files += [OUT/'README.md',OUT/'reproduce_layout.sh',OUT/'reproduce.sh']
    files=sorted(set(files))
    manifest=OUT/'COMPACT_REVISION_MANIFEST.json'
    rows=[dict(path=str(f.relative_to(OUT)),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size) for f in files]
    manifest.write_text(json.dumps(dict(scope='Figure 6–9 compact layout only',title_font_pt=14.5,
        fullscale_pairs=28,fig9_default='A: latency reduction',experiments_run=0,files=rows),indent=2))
    archive=OUT/'figures_sec4_2_compact_14p5_delivery.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in files+[manifest]:z.write(f,arcname=str(Path(OUT.name)/f.relative_to(OUT)))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    print(archive,archive.stat().st_size,'bytes;',len(files),'files plus manifest')

if __name__=='__main__':main()
