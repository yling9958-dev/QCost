"""Create a manifest and ZIP of this isolated delivery, never original data."""
from pathlib import Path
import hashlib,json,zipfile

OUT=Path(__file__).resolve().parents[1]
PRIMARY=['fig6_latency_ecdf','fig7_grouped_bar','fig8_construction_storage','fig9_workload_lines',
         'fig7_grouped_bar_with_user_summary']
def active(p):
    r=p.relative_to(OUT);parts=r.parts
    if parts[0]=='archive' or 'mplconfig' in parts or '__pycache__' in parts:return False
    if parts[0]=='figures':return p.stem in PRIMARY
    if parts[0]=='latex':return p.stem in ['section4_2_revised','section4_2_preview','ieee_figures_6_9_preview'] and p.suffix in ['.tex','.pdf']
    if parts[0]=='data':return p.name not in ['fig7_plotted_values.csv']
    if parts[0]=='reports':
        if 'backups' in parts:return True
        if 'previews' in parts:
            return any(p.name.startswith(x+'_') for x in PRIMARY) and '_first' not in p.name or p.name.startswith(('section4_2_preview-','ieee_figures_6_9_preview-','ieee_12_page_contact_sheet'))
        if p.name.startswith(('fig7_A','fig7_B','fig7_shared','fig8_construction_storage_double','fig9_workload_area')):return False
        if p.name.startswith(('section4_2_preview_A','section4_2_preview_B','ieee_figures_preview')):return False
        if p.suffix=='.log':return '_revision' in p.stem or p.name in ['section4_2_preview_compile.log','ieee_figures_6_9_preview_compile.log']
        return True
    return True
def main():
    archive=OUT/'figures_sec4_2_delivery.zip'
    manifest=OUT/'DELIVERY_MANIFEST.json'
    files=[p for p in OUT.rglob('*') if p.is_file() and p not in [archive,manifest] and active(p)]
    rows=[{'path':str(p.relative_to(OUT)),'bytes':p.stat().st_size,
           'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]
    manifest.write_text(json.dumps({'scope':'Section 4.2 Figures 6–9 only','fullscale_status':'27_RAW_VERIFIED_PLUS_1_UNVERIFIED_USER_SUMMARY',
                                   'primary_figures':PRIMARY[:4],'supplement':PRIMARY[4],
                                   'manuscript_global_numbering':'UNVERIFIED_MAIN_SOURCE_NOT_FOUND',
                                   'large_experiments_run':0,'files':rows},indent=2))
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(files)+[manifest]:z.write(p,arcname=str(Path(OUT.name)/p.relative_to(OUT)))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    print(f'{archive}: {archive.stat().st_size} bytes; {len(rows)} files plus manifest')

if __name__=='__main__':main()
