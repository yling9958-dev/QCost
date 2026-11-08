"""Write standalone review material; never edit the original manuscript."""
from pathlib import Path
import json
import pandas as pd
import numpy as np

OUT=Path(__file__).resolve().parents[1]
def rd(n): return pd.read_csv(OUT/'data'/n)
def md(df):
    columns=list(df.columns)
    rows=['| '+' | '.join(columns)+' |','| '+' | '.join(['---']*len(columns))+' |']
    rows += ['| '+' | '.join(str(v).replace('|','/') for v in row)+' |' for row in df.itertuples(index=False,name=None)]
    return '\n'.join(rows)
def write(name,text): (OUT/name).write_text(text.strip()+'\n')

def main():
    d=rd('fullscale_results.csv');v=d[d.verified_for_plot];s=rd('fastest_competitor_speedups.csv')
    b=rd('construction_results.csv');b=b[b.included_in_fig8a]
    st=rd('storage_results.csv');w=rd('workload_area_results.csv')
    cov=v.groupby('method',sort=False).agg(datasets=('dataset','size'),timings=('timing_observations','sum')).reset_index()
    speed=s[['dataset','competitor','qcost_mean_ms','competitor_mean_ms','speedup']].copy()
    for c in ['qcost_mean_ms','competitor_mean_ms']:speed[c]=speed[c].map(lambda x:f'{x:.6f}')
    speed['speedup']=speed.speedup.map(lambda x:f'{x:.6f}x')
    supplied=json.loads((OUT/'data/user_supplied_flood_skewed_summary.json').read_text())
    pd.DataFrame([
        {'figure':'6','status':'13_RAW_ECDF_CURVES;_FLOOD_SKEWED_MISSING','observations':195000},
        {'figure':'7','status':'27_OF_28_RAW_VERIFIED','observations':405000},
        {'figure':'7_summary_supplement','status':'27_VERIFIED_PLUS_1_USER_SUMMARY','observations':405000},
        {'figure':'8','status':'4_QCOST_BUILDS_AND_22_COMPARABLE_STORAGE_RECORDS','observations':None},
        {'figure':'9','status':'80_BUILDS_240_PAIRED_RATIOS','observations':1200000}
    ]).to_csv(OUT/'reports/delivery_status.csv',index=False)
    write('reports/data_audit.md',f'''# Section 4.2 Figures 6–9: data audit

## Coverage and scientific scope

**27 raw-verified combinations + 1 explicitly unverified user-supplied summary; not 28 verified combinations.**
No experiment, database query, model training or index build was run. Original files remain read-only.
The old delivery is preserved in `archive/previous_delivery_*.zip` with a SHA-256 member manifest.

{md(cov)}

The four added LMSFC records and the NYC/Skewed GiST completions bring the old 21 records to 27.
Each verified pair has 15,000 positive, finite nanosecond timings (3,000 frozen queries × 5 rounds)
and 1,000 passed correctness checks. All 405,000 clocks are retained, including long tails and
empty-result queries. Repeated (round, query ID) slots are absent. Query order and result counts
match Q-COST on every verified dataset–method pair. The performance/correctness query files
are byte-identical across the six baseline packages for each dataset.
No 20K/50K records enter the full-scale comparison.

## Directories, inventory and selected sources

Recursive scans cover `/media/lingyaqi/Lenovo F510/Mthod` and `/media/lingyaqi/Lenovo F510/QMF`.
Source references also lead to QMap-LI/paper_icde_qcost_results, QMF-Core-Ablation and existing
Q-COST-QMF-Necessity-Study TeX fragments. `data/recursive_inventory_latest.csv` records paths,
file types, sizes and mtimes; it includes CSV, compressed CSV, JSON, TXT, LOG, Excel and source
files. No SQLite/DB files were found in this inventory. `data/provenance.csv` records hashes
of consumed originals; `data/fullscale_results.csv` gives each pair's exact timing, summary,
correctness and implementation paths. Protected sources include all four visual references.

Selected summaries are BMTREE_FINAL_RESULTS.csv, LISA_FINAL_RESULTS.csv,
TSUNAMI_FINAL_RESULTS.csv, FLOOD_COMPLETE_FINAL_RESULTS.csv,
LMSFC_CR_PARTIAL_FINAL_RESULTS.csv and QMF_RESULT_PROVENANCE.json, together with
08_postgis_gist_completion/06_summary/{{historical_gist_validation,nyc_completed_summary,
skewed_completed_summary}}.json. Every verified mean and percentile was recomputed from
the referenced raw CSV/CSV.zst, rather than copied from a plot or rounded table.

## Units and numerical validation

Mean = mean(latency_ns)/10^6. P95 and P99 use NumPy linear empirical quantiles of the complete
15,000-element vector. QPS = 1000/mean_ms, a derived sequential-client rate, not measured
parallel throughput. All old 21-pair metrics agree with recomputation (relative tolerance 1e-10).
Point counts remain 181000000, 183000000, 181000000 and 204986702. Storage uses bytes/2^30
GiB; build hours use seconds/3600. All plotted times and log-axis values are strictly positive.

## Flood–Skewed user summary

The newly supplied numbers were searched across small CSV/JSON/TXT/LOG/MD files, including
238.4176, 862.5319, 4951.8274 and 14285.76; no matching original result was located.
Retained original attempts report HOST_SAFETY_STOP with zero timing/correctness observations.
This does not invalidate a possible later run; its evidence is simply unavailable locally.
`data/user_supplied_flood_skewed_summary.json` preserves the user's values: 118.42 s build,
238.4176 ms mean, 862.5319 ms P95, 4951.8274 ms P99, 4.1943 QPS and 14285.76 MiB peak memory.
The reciprocal mean is {supplied['derived_qps']:.10f} QPS, which rounds to 4.1943.
Arithmetic consistency does not establish correctness or completion of the missing run.
Index size stays missing; peak memory is never substituted. The row has status
USER_SUPPLIED_SUMMARY, verification_status=UNVERIFIED_RAW_RECORDS_NOT_LOCATED and
verified_for_plot=False. It inherits no dataset/query/protocol hashes from the older failed run.

The main `fig7_grouped_bar` includes 27 verified pairs. The separate
`fig7_grouped_bar_with_user_summary` uses the same CSV and adds the provided values as white,
cross-hatched, starred bars with a visible unverified-summary note. It is a review supplement.
No ECDF is synthesized from these aggregates. The missing Flood curve on Skewed is explicit.

## Actual implementations and protocol differences

| Display name | Measured implementation and qualification |
| --- | --- |
| Q-COST | Retained qmap_uniform_qmf / QMF-Index build; original analytic-QMF route |
| BMTree | Pinned author training/export implementation with native query adapter |
| LISA | LISA-V2 / lisa_v2_r3 adapter; saved complete query state |
| Tsunami | Local clean-room reproduction |
| Flood | FLOOD_RECOVERY_V2 adapter; three raw-verified datasets |
| PostGIS GiST | PostgreSQL 14 / PostGIS 3.2, historical and completed later runs |
| LMSFC | LMSFC-CR-Partial local partial reproduction; not LMSFC_FULL |

The user's instruction permits partial reproductions as baselines; the real identity remains
in the audit. Display names do not relabel the underlying code or evidence. Flood protocol
metadata hashes changed with source_version and EnvironmentID; timing policy bytes and the
remaining configuration match. Latest passing LISA/Flood revisions are selected consistently.

Native correctness logs check both counts and IDs. Later NYC/Skewed GiST completion logs check
counts against retained cross-checked truth. The same frozen rectangles and prepared
request–response timing boundary are retained. GiST completion scheduling, durability and
timeout controls differ from historical runs; Skewed has two sequential timing connections
after scheduled continuation and 600 warmups total rather than 300. See the retained
09_postgis_fairness_audit_20261019/FAIRNESS_AUDIT.md for details.
Thus identical workload and returned counts do not imply identical engines, cache residency,
planner behavior or full-subtree counting. These are system-level comparisons; their speedups
are not attributed to QMF search alone. No new fully harmonized benchmark is claimed.

## Figure 6: distributions

GeoLife has seven genuine ECDFs and Skewed has six: 13 × 15,000 observations. Every unique
observed latency and its multiplicity is saved in `fig6_ecdf_steps.csv`. Curves are right-continuous
empirical steps; path simplification and smoothing are disabled. Sparse markers lie on genuine
steps. Log-x limits include every observation. `fig6_ecdf_statistics.csv` cross-checks the
quantiles against Figure 7. Original CDF/P95 PDFs remain byte-identical and are backed up in
`reports/backups/`; the prior delivery is also archived.

## Figure 7: grouped bars and strongest-competitor ratios

{md(speed)}

Methods stay in the fixed order Q-COST, BMTree, LISA, Tsunami, Flood, PostGIS GiST, LMSFC.
Dataset order is GeoLife, Gowalla, NYC Taxi, Skewed 2D. Only three methods use sparse hatches.
All panels have logarithmic y axes and explicit positive baselines recorded in the JSON checks;
bar endpoints encode values. The main panel contains 108 endpoints (27 pairs × 4 metrics).
The four red ratios compare Q-COST with the lowest valid non-Q-COST mean, including LMSFC.
Gowalla therefore uses LISA (35.6x), not BMTree (37.6x). Raw-verified Q-COST means, P95 and
P99 are lowest on each dataset. This statement applies to the audited completed combinations.
The unverified Flood summary would not change the Skewed fastest competitor, but it is still
excluded from the formal inference. No uncertainty claim is derived from the pooled queries.

## Figure 8: construction and complete persistent state

The four Q-COST builds are {', '.join(f'{x:.6f}' for x in b.build_s)} seconds, shown as hours.
Other methods have different loading/training/export/index-creation timing boundaries and are
not ranked by build time. Figure 8(b) includes {int(st.included.sum())} complete-state observations:
Q-COST, BMTree, LISA, Tsunami and LMSFC on four datasets, plus NYC/Skewed GiST table-plus-index
footprints. Native point payloads are included. GiST includes heap, all indexes, TOAST/FSM/VM,
but excludes server catalogs/WAL/temp. The definition is complete per-dataset serving state;
representation and database bookkeeping differ, so it is not a pure metadata ranking.
Index-only historical GiST sizes and Flood point archives that reconstruct indexes on load are
excluded. Exclusions are explicit in `storage_results.csv` and not treated as zero.
Q-COST occupies 3.371399, 3.408652, 3.371397 and 3.818186 GiB. Ten still-present native files
are stat-checked; absent runtime files use retained build receipts and are labeled as such.

## Figure 9: paired controlled measurements

The QMF-Core-Ablation experiment contributes 80 builds (4 datasets × 4 methods × 5 seeds),
1,200,000 query clocks and 240 build-class ratios. Seeds are 11, 23, 37, 51 and 73.
For each dataset/seed/area class, the method's mean over 1,000 queries × 5 rounds is divided
by the corresponding R4 mean. The five resulting ratios are averaged; CI half-width is
t_(0.975,4) × sample_sd/sqrt(5). Query rounds are not treated as independent builds.
All 12 Q-COST intervals contain 1; no interval is narrowed or trimmed for presentation.
All original 240 paired ratios match. Lines connect S1/S2/S3, with small documented categorical
offsets solely to separate error bars; y values and intervals are unchanged and axes start at zero.

S1/S2/S3 mean nominal pre-clipping rectangle areas of 0.01%/0.1%/1%, not actual result
selectivities. These are 20K samples using a common C++ kernel. GeoLife derives from a retained
100 MiB reproduction, while the others derive from bounded 100K-row prefixes. They are not
new random samples of the entire billion-scale populations. Q-COST is cpu_qmf_h3 from the
original campaign, not the later Hybrid-QMF optimizer.

## Paper integration and protection

The full original manuscript source was not found: the scan contains 245 TeX files and 28
document-class entries, all Q-COST entries being snippets, previews or a supplement.
No actual current global Figure 6–9 mapping can therefore be certified. The proposed labels
are qcost_06/qcost_07/qcost_08/qcost_09 in that insertion order. They become Figures 6–9 only
if five figures precede them in the original manuscript. No counter manipulation is used.
`reports/figure_numbering_audit.md` records this limitation and integration instructions.
The full replacement subsection contains no TABLE II environment and changes its reference
to Figure 7; it is saved separately and does not alter Sections 4.3 onward.
SHA-256 results are in `original_file_integrity.md` after rendering.
''')
    write('reports/missing_results.md','''# Missing and qualified results

- **Flood–Skewed 2D**: provided aggregate saved, but no matching 15,000 timings,
  1,000 correctness checks, run ID, source revision or build receipt was located.
  Formal Figure 7 is 27/28 raw-verified. The explicit summary supplement includes a
  starred, unverified 28th row. Figure 6 cannot include its ECDF.
- Flood–Skewed index size is missing. Peak RSS is not storage.
- Flood archives on three other datasets are not complete persisted query states;
  GeoLife/Gowalla GiST records contain index-only sizes. These five records are excluded
  from direct storage comparison. No missing value is imputed.
- The original full Q-COST manuscript TeX entry point is unavailable. Proposed labels
  are supplied, while actual global numbering remains to be verified on integration.
- Workload results are complete for the retained 20K, five-build campaign. They do not
  measure the later Hybrid-QMF implementation or establish full-scale controlled speedups.
- No large rerun is required for this revision. If the missing Flood raw files are
  supplied later, validate their identities/protocol and update through a new version.
''')
    write('reports/figure_numbering_audit.md','''# Actual numbering versus requested numbering

`latex_source_inventory.csv` lists all 245 discovered TeX files and their labels.
The only main.tex under Mthod is the external LMSFC paper, not the Q-COST manuscript.
The Q-COST files found are figure snippets, generated previews, method revisions,
and paper_supplement.tex. None is the complete current submission with Section 4.2.
The historical snippets associate qcost_07 with latency distributions, qcost_08 with
construction/storage and qcost_09 with workload; these label strings are not evidence
of LaTeX's final displayed number.

| Requested figure | Proposed label | Content |
| --- | --- | --- |
| 6 | fig:qcost_06 | GeoLife and Skewed empirical latency distributions |
| 7 | fig:qcost_07 | Mean/P95/P99/derived QPS bars, replaces TABLE II |
| 8 | fig:qcost_08 | Q-COST build hours and complete persisted state |
| 9 | fig:qcost_09 | Paired 20K workload-class results |

Insert the four environments in this order only after checking the original paper's
existing figures. If there are five preceding figures, automatic numbering gives 6–9.
If there is an existing method figure numbered 6, its conflict needs manuscript-level
resolution; this delivery does not remove or renumber that unrelated figure.
No setcounter/addtocounter command for figures is used. The isolated section preview
naturally numbers its four figures 1–4, and is explicitly marked as a local preview.
The layout review PDF uses requested file identifiers solely as review headings.
The actual submission numbering remains unverified until the full main TeX is available.
''')
    write('reports/figure_design_notes.md','''# Reference analysis and final design

The four supplied PNGs were opened and visually inspected. Reference 1 combines fixed
method order, grouped bars, fine black borders, restrained hatches and concise speedup
annotations. Reference 2 separates related measurements into aligned panels with log
axes and a shared legend. Reference 3 uses clean lines and a unified legend. Reference 4
uses consistent per-dataset panels and color/marker coding. These principles are reused;
their measurements, thread axes, gray backgrounds and occasional clipped labels are not.

- Figure 6: two genuine step ECDFs with a shared two-row legend and sparse markers.
  Seven GeoLife and six Skewed curves; full tails retained. The missing-curve note is
  outside the data rectangle.
- Figure 7: chosen primary encoding is a 2×2 grouped bar chart. Positive log baselines,
  fixed seven-method ordering, sparse hatches, and four strongest-competitor ratios.
  A separate, visibly qualified user-summary candidate is provided, not mixed into the
  raw-verified main figure. The obsolete dot/bar comparison remains in the archive.
- Figure 8: four Q-COST red build-hour bars and a storage/latency scatter. Method colors
  and dataset shapes have separate compact legends; only comparable complete states appear.
- Figure 9: four line panels with markers and unmodified paired-build Student-t intervals.
  Shared 0–1.5 y range includes zero and keeps modest differences in perspective. Small
  horizontal offsets identify methods within each categorical area group.

All primary outputs are 7.1 inches wide, with Times New Roman, 12 pt axis labels,
10.3–11 pt ticks, about 11 pt legends and 12 pt bold, single-line bottom panel titles.
White background, fine gray horizontal grid, no top/right spines, no gradient/shadow/3D.
Q-COST is #E64B35 in every panel; the other six colors follow the current user specification.
SVG keeps text elements; PDF uses embedded Type 42 fonts. PNGs are 600 dpi.

Actual IEEEtran geometry is checked at 0.90, 0.95 and 1.00 textwidth. Double-column
figure* is recommended for all four primary figures; shrinking these layouts to one
column halves their effective font sizes and is not the recommended placement.
The original CDF/P95 PDFs and entire earlier delivery are preserved separately.
''')
    write('reports/paper_change_log.md','''# Section 4.2 integration changes

1. Replace only the Overall Index Performance subsection with the standalone new fragment.
2. Remove the original TABLE II environment manually during manuscript integration; replace
   Table~\\ref{tab:qcost_system} with Figure~\\ref{fig:qcost_07}.
3. Add the two-ECDF figure before the four-metric bar figure. Move distribution/long-tail
   discussion to qcost_06; qcost_07(a) now denotes mean latency, not the old GeoLife CDF.
4. Use 27 raw-verified combinations; separately acknowledge the unverified Flood summary.
5. Display LISA/Flood/Tsunami with no version suffix while disclosing actual local versions.
6. The new annotations are versus the fastest verified competitor: 34.1/35.6/220.8/10.3x.
   In particular Gowalla's comparator changes from BMTree to LISA.
7. Explain derived sequential QPS, positive log-bar baselines and the scope of storage.
8. Preserve original cpu_qmf_h3 lineage and paired five-build intervals for Figure 9.
9. Keep the proposed labels qcost_06, qcost_07, qcost_08 and qcost_09; verify automatic
   global numbering against the full manuscript. No figure counters were forced.
10. Sections 4.3 onward, the original paper and all historical experiments remain untouched.
''')
    write('README.md','''# Q-COST Section 4.2: Figures 6–9

The current primary outputs are `fig6_latency_ecdf`, `fig7_grouped_bar`,
`fig8_construction_storage` and `fig9_workload_lines`, each in PDF/SVG/600-dpi PNG.
The superseded delivery and its SHA-256 manifest are in `archive/`.

27 combinations are reconstructed from 405,000 raw timings and 27,000 correctness checks.
Flood–Skewed is stored as a user-supplied, raw-unverified summary. The main figures do not
silently promote it to a verified result. A starred review candidate is supplied as
`fig7_grouped_bar_with_user_summary`. There is no artificial Flood–Skewed ECDF.

Figure 9 uses 80 independent 20K builds and 1.2 million retained query timings. All 12
Q-COST confidence intervals include 1. This is the historical analytic-QMF builder.

Run `bash reproduce.sh` from this directory (or any directory). It only reads original
evidence and reconstructs this delivery; it never starts an experiment. Existing generated
outputs are archived before regeneration. Original/source hashes are checked first and last.
The venv path and required tools are recorded in RUN_COMMANDS.md.

Use `latex/section4_2_revised.tex` as an independent integration proposal. It does not edit
the paper. Full original main TeX was unavailable; actual global Figure 6–9 numbering cannot
be certified. The local section preview numbers figures 1–4 automatically. The separate
IEEE geometry review PDF checks the requested figures at three actual text widths.

See reports/data_audit.md, missing_results.md, figure_numbering_audit.md and visual_review.md.
''')
    write('RUN_COMMANDS.md','''# Reproduction

```bash
cd '/media/lingyaqi/Lenovo F510/QMF/figures_sec4_2'
bash reproduce.sh
```

Python: `/media/lingyaqi/Lenovo F510/QMF-Motivation-Study/.venv/bin/python`.
Packages: NumPy, pandas, SciPy, Matplotlib, Pillow. External tools: zstd, pdflatex,
pdftoppm, pdffonts, pdfimages; local IEEEtran/fonts and librsvg are reused read-only.
No Seaborn/Plotly, training, database import, benchmark or index rebuild is invoked.

The ordered commands are extract_results.py, plot_fig7.py, plot_fig6.py,
plot_fig8.py, plot_fig9.py, write_reports.py, preview_and_check.py, seal_delivery.py.
Source checks abort on changed protected inputs. Rendering resources are bounded by
one process and one numerical-library thread in the reproduction script.
''')
    write('latex/section4_2_revised.tex',SECTION)

SECTION=r'''
% Standalone Section 4.2 proposal. Original manuscript is not modified.
% Required packages: graphicx. Resolve global numbering by normal insertion order.
% Labels below become Figures 6--9 only if five figures precede this subsection.
\subsection{Overall Index Performance}
\label{sec:overall_performance}
We evaluate range-count queries on GeoLife, Gowalla, NYC Taxi, and Skewed 2D,
containing 181.00M, 183.00M, 181.00M, and 204.99M points, respectively.
The raw-verified comparison covers 27 dataset--method combinations. Each retains
1,000 passed correctness checks and 15,000 timing observations from 3,000 fixed
queries repeated five times. The additional Flood summary for Skewed 2D remains
separate from the raw-verified comparison pending its timing and correctness logs.
% 四个数据集规模分别为181.00M、183.00M、181.00M、204.99M。原始记录核验通过27组，每组有1000条正确性检查及3000条查询重复五轮的15000条计时。另行提供的Flood--Skewed汇总因缺少原始日志而单独保留，不纳入已核验比较。

The labels denote the audited local implementations: BMTree uses a pinned
author implementation with a native query adapter; LISA and Flood use the
measured adapters; Tsunami and LMSFC use local reproductions, with LMSFC
representing a partial reproduction. Q-COST retains its measured construction
implementation. System-level latency differences include data layout, query
execution, cache residency, and full-subtree counting.
% 方法名称对应已审计的本地实现，LMSFC为部分复现，Q-COST保留原实验构建实现。系统级延迟差异同时包含数据布局、查询执行、缓存驻留与完整子树计数的贡献。

\subsubsection{Range Query Latency}
Figure~\ref{fig:qcost_06} presents empirical latency distributions for GeoLife
and Skewed 2D. Every curve retains all 15,000 observations and their long tails.
On GeoLife, Q-COST has a median latency of 0.0223 ms, compared with 3.1301 ms
for BMTree; on Skewed 2D, the corresponding medians are 1.6664 and 5.7428 ms.
The distributions complement aggregate latency by showing how query costs
vary across the fixed workload.
% 图6由每组全部15000条实测计时绘制，保留长尾。GeoLife上Q-COST与BMTree的中位延迟为0.0223和3.1301 ms；Skewed 2D上为1.6664和5.7428 ms。分布展示固定工作负载内的查询成本差异。

\begin{figure*}[t]
    \centering
    \includegraphics[width=0.95\textwidth]{figures/fig6_latency_ecdf.pdf}
    \caption{Range-count latency distributions on large-scale spatial
    datasets. Each empirical step curve contains 15,000 retained observations.
    GeoLife includes seven methods; Skewed 2D includes six methods with
    available raw timings. The latency axis is logarithmic.}
    % 亿级空间数据集的范围计数延迟经验分布，每条阶梯曲线保留15000条计时。GeoLife包含七种方法；Skewed包含有原始计时的六种方法。横轴采用对数尺度。
    \label{fig:qcost_06}
\end{figure*}

Figure~\ref{fig:qcost_07} summarizes mean, P95, and P99 latency and derived
sequential query throughput. Q-COST's mean latencies are 0.8636, 1.3646,
0.1601, and 6.4236 ms in dataset order. Relative to the fastest verified
competitor on each dataset, these correspond to speedups of 34.1, 35.6,
220.8, and 10.3 times. BMTree is the fastest competitor on GeoLife, NYC Taxi,
and Skewed 2D; LISA is the fastest on Gowalla. The comparison includes all
completed LMSFC runs.
% 图7用平均、P95、P99及由均值推算的顺序吞吐率替代原TABLE II。Q-COST平均延迟为0.8636、1.3646、0.1601、6.4236 ms；相对最快已核验竞争方法为34.1、35.6、220.8、10.3倍。Gowalla的比较对象为LISA，其余为BMTree，已纳入全部已完成LMSFC记录。

\begin{figure*}[t]
    \centering
    \includegraphics[width=0.95\textwidth]{figures/fig7_grouped_bar.pdf}
    \caption{Range-count query latency and throughput across four large-scale
    spatial datasets. The panels report (a) mean, (b) P95, (c) P99 latency,
    and (d) derived QPS for 27 raw-verified combinations. Lower latency and
    higher throughput are preferable. Annotated speedups compare Q-COST with
    the fastest verified competing method on each dataset. All vertical axes
    are logarithmic; bar endpoints encode values above positive axis baselines.
    The asterisk denotes the missing verified Flood--Skewed result.}
    % 四个亿级数据集27组已核验结果：平均、P95、P99越低越好，QPS越高越好。倍数相对各数据集最快的有效竞争方法。对数柱形采用正数基线，以端点表示数值；星号表示Flood--Skewed缺少已核验结果。
    \label{fig:qcost_07}
\end{figure*}

Q-COST also has the lowest observed P95 and P99 among the verified methods
on each dataset. Its P95 latencies are 1.2096, 5.2051, 0.1541, and 23.8662 ms,
while P99 values are 9.9793, 36.5269, 4.5635, and 96.8666 ms. Throughput is
computed as $1000/\mathrm{mean\_ms}$, yielding 1158.0, 732.8, 6246.1, and
155.7 queries/s. It describes the same sequential latency observations.
% Q-COST在各数据集已核验方法中具有最低P95与P99；对应数值为1.2096、5.2051、0.1541、23.8662 ms以及9.9793、36.5269、4.5635、96.8666 ms。QPS按1000/平均毫秒延迟计算，为1158.0、732.8、6246.1、155.7，描述相同顺序执行记录。

The prepared request--response boundary and frozen rectangles are retained,
while system execution and memory residency differ. Q-COST preloads a static
index and counts fully covered subtrees from stored intervals; GiST executes
predicates through PostgreSQL relations. The later NYC and Skewed GiST runs
preserve the frozen queries. Skewed uses two sequential timing connections
after a scheduled continuation, with 600 warmups in total. These retained
system measurements motivate the common-kernel control below.
% prepared请求--响应计时边界与冻结矩形一致，但执行路径和内存驻留不同。Q-COST预加载索引并利用完整子树计数；GiST通过PostgreSQL执行谓词。补齐GiST的Skewed实验经历一次计划续接、两次顺序计时连接，共600次预热。下文固定查询内核进一步控制构建策略差异。

\subsubsection{Construction Cost and Storage Efficiency}
Figure~\ref{fig:qcost_08}(a) shows Q-COST's measured construction cost.
GeoLife, Gowalla, NYC Taxi, and Skewed 2D require 13,907.3, 9,374.3, 7,987.6,
and 14,403.2 s, or 3.86, 2.60, 2.22, and 4.00 h. Baseline build records use
different boundaries for input loading, model export, and index creation;
the panel therefore compares Q-COST across datasets.
% Q-COST构建时间依次为13907.3、9374.3、7987.6、14403.2秒，即3.86、2.60、2.22、4.00小时。不同基线加载、模型导出、索引创建的计时范围不同，因此图8(a)仅进行Q-COST跨数据集比较。

\begin{figure*}[t]
    \centering
    \includegraphics[width=0.95\textwidth]{figures/fig8_construction_storage.pdf}
    \caption{Construction cost and storage--latency characteristics on
    large-scale spatial datasets. (a) Q-COST construction time.
    (b) Complete persisted query state versus mean latency, with logarithmic
    axes; colors indicate methods and shapes indicate datasets. Native point
    payloads are included. The two GiST observations include tables and all
    indexes; index-only records and reconstruction archives are excluded.}
    % 构建成本与存储--延迟关系。(a)Q-COST构建时间；(b)完整持久化查询状态与平均延迟，双对数轴，颜色区分方法、形状区分数据集。包括原生点数据与两组GiST表及全部索引，排除仅索引大小和需重建的点归档。
    \label{fig:qcost_08}
\end{figure*}

Q-COST's persisted states occupy 3.37--3.82 GiB. Figure~\ref{fig:qcost_08}(b)
contains 22 complete-state observations: five native methods on four datasets
and two GiST table-plus-index footprints. Similar persistent sizes correspond
to different serving latencies. LISA includes its model, partitions, projected
points, and ID lookup; GiST additionally retains relation bookkeeping. The
comparison accounts for serving-state representation as part of each system.
% Q-COST持久化状态为3.37--3.82 GiB。图8(b)包含五种原生方法的20组完整状态及两组GiST表加索引。相似存储规模对应不同延迟；LISA含模型、分区、点与ID查找，GiST含关系管理开销，系统状态表示属于比较口径的一部分。

\subsubsection{Workload-Dependent Query Performance}
Figure~\ref{fig:qcost_09} compares R4 Greedy, Cost-H1, Recursive Exact, and
Q-COST on retained 20K-point samples using the same native C++ range-count
kernel. Q-COST denotes the original analytic-QMF construction in this
campaign. S1, S2, and S3 specify nominal query areas of 0.01\%, 0.1\%, and
1\% of the full normalized domain before boundary clipping.
% 图9在保留的20K点样本和同一C++范围计数内核上比较四种构建策略。Q-COST为该实验原有解析QMF构建器；S1/S2/S3表示边界裁剪前的0.01%、0.1%、1%名义查询面积，而非实际返回点比例。

Each seed reuses the fixed campaign sample and workload. GeoLife derives
from the retained 100 MiB reproduction; the other samples derive from
bounded 100K-row source prefixes. For each dataset, seed, and area class,
we divide the method's mean latency by the matched R4 mean. Means and 95\%
Student-$t$ intervals are computed from five independent builds; the five
query rounds within a build contribute to its mean latency.
% 各种子复用固定样本和工作负载。GeoLife来自保留的100 MiB复现，其余来自源数据前100K行。对相同数据集、构建种子和面积类别先与R4均值配对求比值，再用五次独立构建计算均值及95% Student-t区间；五轮查询只参与该次构建的均值计算。

\begin{figure*}[t]
    \centering
    \includegraphics[width=0.95\textwidth]{figures/fig9_workload_lines.pdf}
    \caption{Relative range-count latency across query-area classes on four
    spatial datasets. S1/S2/S3 correspond to 0.01\%/0.1\%/1\% nominal
    pre-clipping area. Means and 95\% Student-$t$ intervals use five paired,
    independent builds (four degrees of freedom). The horizontal reference
    is R4 Greedy. Small categorical offsets separate overlapping error bars.}
    % 四个数据集上不同查询面积的相对范围计数延迟。均值与95% Student-t区间来自五次配对独立构建（自由度4），水平线表示R4基准；轻微类别偏移用于分离误差棒，不改变任何数值。
    \label{fig:qcost_09}
\end{figure*}

Q-COST's relative means span 1.008--1.020 on GeoLife, 0.987--0.997 on
Gowalla, 0.973--0.980 on NYC Taxi, and 0.952--0.973 on Skewed 2D. All twelve
confidence intervals contain one. The retained common-kernel measurements
therefore show modest dataset-dependent differences at this scale. This
controlled result complements the full-scale system comparison by keeping
the execution path fixed when evaluating construction strategies.
% Q-COST相对均值范围依次为1.008--1.020、0.987--0.997、0.973--0.980、0.952--0.973，全部12个区间覆盖1。固定执行内核的小规模结果仅显示较小的数据集相关差异，与亿级完整系统比较的口径分开解释。
'''

if __name__=='__main__':main()
