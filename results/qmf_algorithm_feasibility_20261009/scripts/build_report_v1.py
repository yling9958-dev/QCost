"""Aggregate immutable diagnostic outputs and write the Chinese research report."""
from pathlib import Path
import ast,csv,hashlib,importlib.metadata,json,math,os,pickle,statistics,sys
RUN=Path(__file__).resolve().parents[1];ROOT=RUN.parents[1]
PKG=ROOT/'QMF_PostGIS_100M_Repro_20260910'
sys.path.insert(0,str(PKG/'src/common/python'))
import numpy as np

def readjson(p):return json.loads(Path(p).read_text())
def writejson(p,x):
    with Path(p).open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2)
def writecsv(name,rows):
    with (RUN/'report'/name).open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def mdtable(headers,rows):
    def clean(x):return str(x).replace('|','／').replace('\n','<br>')
    return '\n'.join(['| '+' | '.join(map(clean,headers))+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(clean,r))+' |' for r in rows])
def fnum(x,d=6):return f'{float(x):.{d}f}'
def med(xs):return statistics.median(xs)
def avg(xs):return statistics.mean(xs)
def short(node):return node.replace('geolife100m_','')

plan=readjson(RUN/'local_experiment_plan.json')['jobs']
assert len(plan)==56
local=[]
for task in plan:
    job=RUN/'jobs'/task['job_name'];receipt=readjson(job/'receipt.json');r=readjson(job/'result.json')
    assert receipt['status']=='PASS' and r['status']=='PASS',(task,receipt,r)
    resources=list(csv.DictReader((job/'resources.csv').open()))
    samples=[int(x['rss_bytes']) for x in resources if r['local_start_monotonic']<=float(x['monotonic'])<=r['local_end_monotonic']]
    r.update(repetition=task['repetition'],job_path=str(job),
        peak_process_rss_mib=max(receipt['peak_sampled_rss_bytes'],receipt['peak_observed_hwm_bytes'])/1024**2,
        peak_sampled_local_rss_mib=max(samples)/1024**2 if samples else None)
    local.append(r)

all_search=[];profiles=[]
for node in [0,121,251]:
    job=RUN/'jobs'/f'search_node{node}_20seeds_v1'
    assert readjson(job/'receipt.json')['status']=='PASS'
    all_search+=list(csv.DictReader((job/'search_results.csv').open()))
    profiles+=list(csv.DictReader((job/'qmf_time_components.csv').open()))
assert len(all_search)==1224 and len(profiles)==240
search_summary=[];paired=[]
for node in [0,121,251]:
    name=f'geolife100m_node{node}'
    for factor in [.5,1.,2.,4.]:
        for method in ['feasible_greedy_proxy','random','beam16','beam_budget_width','exact_enumeration_scan','qmf','argmin']:
            rows=[r for r in all_search if r['node']==name and r['method']==method and float(r['budget_factor'])==factor]
            summary={'node':name,'method':method,'budget_factor':factor,'budget':int(rows[0]['budget']),
                'N':int(rows[0]['N']),'runs':len(rows),'mean_selected_cost':avg(float(r['selected_cost']) for r in rows),
                'best_cost':min(float(r['selected_cost']) for r in rows),'optimal_cost':float(rows[0]['optimal_cost']),
                'mean_normalized_gap':avg(float(r['normalized_gap']) for r in rows),
                'median_normalized_gap':med(float(r['normalized_gap']) for r in rows),
                'exact_hits':sum(r['exact_optimum_hit']=='True' for r in rows),
                'mean_inspected_candidates':avg(int(r['inspected_candidates']) for r in rows),
                'mean_unique_inspected':avg(int(r['unique_inspected_candidates']) for r in rows),
                'median_search_ms':1000*med(float(r['search_seconds']) for r in rows),
                'mean_search_ms':1000*avg(float(r['search_seconds']) for r in rows),
                'mean_abstract_total_calls':avg(int(r['abstract_total_calls']) for r in rows) if method=='qmf' else None,
                'mean_threshold_calls':avg(int(r['abstract_threshold_calls']) for r in rows) if method=='qmf' else None,
                'mean_verification_calls':avg(int(r['verification_cost_calls']) for r in rows) if method=='qmf' else None,
                'improvement_rate':avg(r['improved_over_initial']=='True' for r in rows) if method in ['qmf','random'] else None,
                'source':f'jobs/search_node{node}_20seeds_v1/search_results.csv'}
            search_summary.append(summary)
        q={r['seed']:r for r in all_search if r['node']==name and r['method']=='qmf' and float(r['budget_factor'])==factor}
        rd={r['seed']:r for r in all_search if r['node']==name and r['method']=='random' and float(r['budget_factor'])==factor}
        wins=sum(float(q[s]['selected_cost'])<float(rd[s]['selected_cost']) for s in q)
        ties=sum(float(q[s]['selected_cost'])==float(rd[s]['selected_cost']) for s in q)
        paired.append({'node':name,'budget_factor':factor,'qmf_wins':wins,'ties':ties,'random_wins':20-wins-ties})

local_summary=[]
methods=['greedy','random','beam16','beam_budget_width','exact_enumeration','recursive_exact','qmf','argmin']
for node in [0,121,251]:
    name=f'geolife100m_node{node}'
    for method in methods:
        rows=[r for r in local if r['node']==name and r['method']==method]
        out={'node':name,'method':method,'repetitions':len(rows)}
        for key in ['candidate_scoring_seconds','configuration_generation_seconds_excluding_scoring','cost_evaluation_seconds',
            'search_seconds','total_local_seconds','peak_process_rss_mib','mean_unused_placeholder']:
            if key=='mean_unused_placeholder':continue
            out['median_'+key]=med(r[key] for r in rows)
        out.update(mean_selected_cost=avg(r['selected_cost'] for r in rows),
            mean_normalized_gap=avg(r['normalized_gap'] for r in rows),
            score_calls=rows[0]['score_calls'],complete_configurations_materialized=rows[0]['complete_configurations_materialized'],
            selected_roots=','.join(sorted(set(r['selected_root'] for r in rows))),
            total_min_s=min(r['total_local_seconds'] for r in rows),total_max_s=max(r['total_local_seconds'] for r in rows))
        local_summary.append(out)

validation=[];spaces=[];root_hits=[]
for node in [0,121,251]:
    name=f'geolife100m_node{node}';art=RUN/'artifacts'/name
    v=readjson(art/'validation.json');validation.append(v)
    assert v['literal_cost_equal'] and v['full_configuration_equal'] and v['scorer_traces_identical']
    with (art/'universe.pkl').open('rb') as f:universe=pickle.load(f)
    with np.load(art/'costs.npz') as z:costs=z['costs']
    geometries={tuple(sorted((l.point_count,l.bounds) for l in cfg.leaves)) for cfg in universe.configurations}
    optimal_roots={universe.configurations[i].root_action.key for i in np.flatnonzero(costs==costs.min())}
    spaces.append({'node':name,'N':len(costs),'unique_action_configurations':v['unique_configuration_signatures'],
        'unique_terminal_leaf_layouts_ignoring_order':len(geometries),'distinct_float_costs':len(set(map(float,costs))),
        'optimal_configuration_count':v['exact_tie_count'],'optimal_root_actions':sorted(optimal_roots),
        'greedy_root_action':universe.greedy_configuration.root_action.key,
        'exact_root_action':universe.configurations[int(np.argmin(costs))].root_action.key})
    for factor in [.5,1.,2.,4.]:
        rows=[r for r in all_search if r['node']==name and r['method']=='qmf' and float(r['budget_factor'])==factor]
        root_hits.append({'node':name,'budget_factor':factor,'optimal_root_hits':sum(r['selected_root'] in optimal_roots for r in rows),'runs':20})
    del universe

frozen_before=readjson(RUN/'formal_files_before.json');changes=[]
for rel,meta in frozen_before.items():
    p=ROOT/rel
    if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=meta['sha256']:changes.append(rel)
assert not changes,changes
writejson(RUN/'formal_files_after_verification.json',{'checked_files':len(frozen_before),'changed_files':changes,'status':'PASS'})

formal_paths=[
ROOT/'results/four_dataset_paper_protocol_20260911/06_qmf_diagnostics/geolife_2d_4p2G/build_r0.json',
ROOT/'results/four_dataset_paper_protocol_20260911/qmf_only_20260919/gowalla_2d_4p2G/attempt-20260919T200540-f8ef2f1a/06_qmf_diagnostics/gowalla_2d_4p2G/build_r0.json',
ROOT/'results/four_dataset_paper_protocol_20260911/qmf_only_20260919/nyc_taxi_2d_4p2G/attempt-20260920T000829-b817046e/06_qmf_diagnostics/nyc_taxi_2d_4p2G/build_r0.json',
ROOT/'results/four_dataset_paper_protocol_20260911/qmf_only_20260919/skewed_2d/attempt-20260920T043052-dff7dd00/06_qmf_diagnostics/skewed_2d/build_r0.json']
formal=[]
for name,path in zip(['GeoLife181M','Gowalla183M','NYCTaxi181M','Skewed204986702'],formal_paths):
    d=readjson(path);formal.append({'dataset':name,'build_seconds':d['index_build_seconds'],
        'candidate_scoring_seconds':d['prior_scoring_seconds'],'configuration_generation_seconds':d['configuration_generation_seconds'],
        'cost_evaluation_seconds':d['oracle_cost_seconds'],'qmf_total_seconds':d['quantum_search_simulator_seconds'],
        'qmf_percent_of_build':100*d['quantum_search_simulator_seconds']/d['index_build_seconds'],
        'fallback_nodes':d['fallback_nodes'],'source':str(path.relative_to(ROOT)),
        'formal_sorting_seconds':'NOT_RECORDED','formal_sampling_seconds':'NOT_RECORDED'})

writecsv('TABLE1_SEARCH_QUALITY.csv',search_summary)
writecsv('TABLE2_LOCAL_TIME_MEMORY.csv',local_summary)
writecsv('TABLE3_QMF_RANDOM_PAIRED.csv',paired)
writecsv('ALL_SEARCH_RUNS.csv',all_search)
writecsv('ALL_QMF_TIME_COMPONENTS.csv',profiles)
writecsv('FORMAL_BUILD_TIME_CONTEXT.csv',formal)
writejson(RUN/'report/LOCAL_TRIALS_WITH_RESOURCES.json',local)
writejson(RUN/'report/CANDIDATE_SPACE_DETAILS.json',spaces)
writecsv('QMF_OPTIMAL_ROOT_HIT_RATE.csv',root_hits)

receipts=[readjson(p) for p in (RUN/'jobs').glob('*/receipt.json')]
assert all(r['status']=='PASS' for r in receipts)
max_mem=max(max(r['peak_sampled_rss_bytes'],r['peak_observed_hwm_bytes']) for r in receipts)/1024**2
max_task=max(r['elapsed_seconds'] for r in receipts)
assert max_mem<4096 and max_task<600
local_get=lambda node,m:next(r for r in local_summary if r['node']==f'geolife100m_node{node}' and r['method']==m)
search_get=lambda node,m,factor:next(r for r in search_summary if r['node']==f'geolife100m_node{node}' and r['method']==m and r['budget_factor']==factor)

quality_rows=[]
for node in [0,121,251]:
    for m in ['feasible_greedy_proxy','random','beam16','beam_budget_width','exact_enumeration_scan','qmf','argmin']:
        r=search_get(node,m,2.)
        quality_rows.append([f'node{node}',m,fnum(r['mean_selected_cost']),fnum(r['mean_normalized_gap']),
            f"{r['exact_hits']}/{r['runs']}",fnum(r['median_search_ms'],4),fnum(r['mean_inspected_candidates'],1),
            fnum(r['mean_abstract_total_calls'],0) if m=='qmf' else 'N/A'])
    v=next(v for v in validation if v['node']==f'geolife100m_node{node}')
    quality_rows.append([f'node{node}','recursive_exact（本地优化）',fnum(v['selected_cost']),'0.000000','精确验证通过','N/A','73 states / 512 leaves','N/A'])
quality_table=mdtable(['节点','方法','平均所选成本','平均归一化gap','最优命中','搜索中位ms','实际候选检查','抽象oracle'],quality_rows)

time_rows=[]
for r in local_summary:
    time_rows.append([short(r['node']),r['method'],r['repetitions'],fnum(r['median_total_local_seconds'],4),
        fnum(r['median_candidate_scoring_seconds'],4),fnum(r['median_configuration_generation_seconds_excluding_scoring'],4),
        fnum(r['median_cost_evaluation_seconds'],4),'融合递归' if r['method']=='recursive_exact' else fnum(r['median_search_seconds'],6),
        fnum(r['median_peak_process_rss_mib'],2),r['complete_configurations_materialized']])
time_table=mdtable(['节点','方法','重复','总秒','R4秒','生成秒','cost秒','search秒','进程峰值MiB','完整配置物化数'],time_rows)

budget_rows=[]
for node in [0,121,251]:
    for factor in [.5,1.,2.,4.]:
        q=search_get(node,'qmf',factor);rd=search_get(node,'random',factor)
        pp=next(p for p in paired if p['node']==q['node'] and p['budget_factor']==factor)
        budget_rows.append([f'node{node}',factor,q['budget'],fnum(q['best_cost']),fnum(q['optimal_cost']),
            fnum(q['mean_normalized_gap']),f"{q['exact_hits']}/20",f"{rd['exact_hits']}/20",fnum(q['improvement_rate'],2),
            fnum(q['median_search_ms'],3),fnum(q['mean_threshold_calls'],1)+' + '+fnum(q['mean_verification_calls'],1),
            f"{pp['qmf_wins']}/{pp['ties']}/{pp['random_wins']}"])
budget_table=mdtable(['节点','√N倍数','预算','QMF best cost','最优cost','QMF mean gap','QMF hit','Random hit','改善率','QMF ms','threshold + verify','Q/T/R胜'],budget_rows)

validation_table=mdtable(['节点','点数／查询','N','最优cost','成本／root／配置','内部访问／不同状态','叶访问／不同状态','最优ties'],[
    [short(v['node']),f"{v['input_manifest']['points']:,} / {v['input_manifest']['queries']}",v['configuration_count'],fnum(v['optimal_cost']),
     '完全一致',f"{v['recursive_stats']['conditional_internal_visits']} / {v['recursive_stats']['unique_internal_states']}",
     f"{v['recursive_stats']['leaf_evaluations']} / {v['recursive_stats']['unique_leaf_states']}",v['exact_tie_count'] for v in validation])

qprofile_rows=[]
for node in [0,121,251]:
    ps=[r for r in profiles if r['node']==f'geolife100m_node{node}' and float(r['budget_factor'])==2.]
    qprofile_rows.append([f'node{node}',fnum(1000*med(float(r['standalone_same_mergesort_seconds']) for r in ps),4),
        fnum(1000*med(float(r['oracle_constructor_including_sort_seconds']) for r in ps),4),
        fnum(1000*med(float(r['qmf_loop_seconds']) for r in ps),4)])
profile_table=mdtable(['节点','同款mergesort / ms','oracle构造含排序 / ms','QMF循环 / ms'],qprofile_rows)

formal_table=mdtable(['正式数据','总构建s','R4评分s','配置生成s','全部costs','QMF控制器s','占比%','fallback'],[
    [r['dataset'],fnum(r['build_seconds'],3),fnum(r['candidate_scoring_seconds'],3),fnum(r['configuration_generation_seconds'],3),
     fnum(r['cost_evaluation_seconds'],3),fnum(r['qmf_total_seconds'],6),fnum(r['qmf_percent_of_build'],6),r['fallback_nodes']] for r in formal])

complexity_table=mdtable(['模块','真实复杂度','当前证据／实际成本'],[
    ['候选与R4','Σ_s [T_candidate(D_s)+T_R4(D_s,Q)]','两种精确方法均73次条件评分；根数据规模使此项占主要时间。'],
    ['完整配置枚举','Ω(N·2^H)输出；另计条件数据划分','每节点16,384个完整配置，动作签名均不同。'],
    ['全表cost','缓存约O(Uq+N·2^H)','当前QMF和枚举式经典策略都预先付此成本。'],
    ['排序','O(N log N)时间、O(N)辅助内存','生产代码执行mergesort；下表给独立计时。'],
    ['QMF解析循环','O(RN+R log N)，R≤B','每轮normalized_prior/array_equal线性；逻辑调用数不能代表这些CPU访问。'],
    ['Direct Argmin','O(N)扫描已物化成本表','当前C/NumPy实现的搜索阶段比解析QMF快，并精确。'],
    ['Recursive Exact','Σ状态评分/划分成本 + O(U_leaf q + L_cond + KS)','完整展开73个内部访问、512个终端访问；输出1个完整最优配置。'],
    ['理论QMF','标准黑盒模型O(√N) oracle queries','不是当前总CPU复杂度；须另算状态制备、可逆oracle和成功概率。']])

routes=[
['A. Existing QMF-inspired Search','联合前瞻＋解析搜索；QMF仅保留为机制/理论对照','保持正式实现；改善审计与计时；不把模拟称量子加速','H1/H3、same-kernel greedy/exact；预算/seed；补数据集','高：全表已知、可分解DP、独立搜索价值不足','已有系统与复现资产可保留；搜索本身无CPU效率证据','低—中；以补实验和改写贡献为主','作为QMF核心路线风险高；作为附属策略有条件保留'],
['B. Recursive Exact Joint Optimization','条件状态上的精确联合优化与滚动构建','验证器已有；未来需集成隔离分支、缓存状态、预算语义、内存生命周期','same-kernel R4-greedy/ExactH1/RecursiveH3；构建和在线收益；H/K；fallback','中：Bellman递推是经典方法，不能直接声称理论新颖','最贴近数据库价值；精确、避免完整配置物化；评分瓶颈仍存在','中；完整系统整合与因果实验为主要工作','当前优先路线；投稿竞争力取决于实测价值和文献差异'],
['C. Genuine Quantum Oracle-Based Search','明确oracle模型下的量子资源/复杂度或混合机制','可行配置编码、相干数据访问、可逆cost/CNN、uncompute、资源估计；门级小验证','成功率/误差/门/深度/qubit；全预处理；对强经典DP；真实数据库目标','很高：数据访问与状态制备可能抵消优势；可分解性仍在','有条件的长期方向；不能由小电路推出大规模系统价值','高—很高；不建议作为近期投稿前置项','需出现明确独立理论或系统证据后再立为主贡献']]
routes_table=mdtable(['Research Route','Core Contribution','Required Implementation','Required Experiments','Theoretical Risk','System Value','Estimated Workload','CCF-A Suitability'],routes)

innovation_table=mdtable(['当前创新候选','本次证据','仍未证明','安全表述'],[
['Workload-conditioned joint optimization','真实候选、同评分轨迹；精确规划局部成本优于R4 rollout','在线查询增益、与cost目标变化的归因、外部首次性','采用条件有限深度子树优化；效果限于已验证局部目标。'],
['QMF-inspired search','3张真实成本表、20种子×4预算；12/12组合平均gap优于Random','CPU优势、量子设备优势、跨数据集稳定性','解析模拟中观察到预算—质量优势；经典预处理明确计入。'],
['Recursive Exact','3节点成本/root/完整配置一致；不可行边界一致；小节点耗时下降','全局树最优性、亿级构建提速、跨数据集泛化','当前固定Q及加性成本下精确；不物化全部联合配置。'],
['Root-only与经典服务','原代码和既有正式结果支持实现','root-only独立优势、统一count内核公平性','离线重规划并经典服务；本次未重跑系统查询。']])

# Text sections are generated from these measured values, not hand-filled results.
ratios={node:local_get(node,'exact_enumeration')['median_total_local_seconds']/local_get(node,'recursive_exact')['median_total_local_seconds'] for node in [0,121,251]}
q2=[r for r in search_summary if r['method']=='qmf' and r['budget_factor']==2.]
r2=[r for r in search_summary if r['method']=='random' and r['budget_factor']==2.]
speed_search={node:search_get(node,'qmf',2.)['median_search_ms']/search_get(node,'argmin',2.)['median_search_ms'] for node in [0,121,251]}
q2hit=sum(r['exact_hits'] for r in q2);r2hit=sum(r['exact_hits'] for r in r2)
roots2=[r for r in root_hits if r['budget_factor']==2.]
space_table=mdtable(['节点','完整动作配置','不同终端叶布局','不同float成本','R4 greedy root','exact root'],[
    [short(r['node']),r['unique_action_configurations'],r['unique_terminal_leaf_layouts_ignoring_order'],r['distinct_float_costs'],r['greedy_root_action'],r['exact_root_action']] for r in spaces])

report=f'''# QMF-Index 算法可行性与研究路线报告

日期：2026-10-09。项目：QMF-Inspired Joint Subtree Optimization for Multidimensional Learned Indexes。

## 核心结论与范围

**建议 PIVOT：以结构化联合子树优化为主线，把当前 QMF 解析模拟降为辅助搜索/理论对照。** 这不是替换正式代码的操作建议：本次没有修改正式源代码、配置、权重或已有结果。

当前成本在固定规划查询上下文下可加，Recursive Exact 可以精确求解相同条件候选空间。三个恢复的真实 reproduction 节点上，最优成本、根动作和完整配置均与现有 Exact H3 一致；一个独立不可行边界探针也一致。QMF 在本次解析模拟预算比较中比 Random 有较好解质量，但全成本表已经备好时，Argmin 更快且精确；本次没有量子硬件加速证据。

实验仅使用已有 **GeoLife100MiB reproduction**，不是正式四个亿级数据集的重跑。规范化输入4,197,223点，SHA校验通过；恢复节点0、121、251。原训练查询1200个，节点上下文分别1200、51、13个。node121是按点数/id确定的最小内部节点（depth=7），node251是最小叶（depth=8）。后者在原全局构建中已达深度上限，本次只研究其局部H3问题。

预先指定随机种子20261009—20261028，共20个；预算0.5、1、2、4倍√N；未按结果挑种子。三个节点实际N均为16,384；没有取得N>0但候选受限的保存节点，这一类型标 **NOT AVAILABLE**。Gowalla、NYC、Skewed的可直接复用精确节点快照/成本表也未找到，未扫描全量数据来补齐。本次结论不能外推为跨四数据集的量化提升。

隔离测试使用CPU affinity=[0,1]、数值库与Torch各1个计算线程、4 GiB RSS上限、每任务600秒限制。已完成{len(receipts)}个有回执任务，全部PASS；最大观测进程峰值{max_mem:.2f} MiB，最长任务{max_task:.2f}秒。小节点完整优化每方法3次，根节点每方法1次，根计时仅是诊断。另有1,224条Search-only结果（其中QMF 240条）和240条QMF分段计时。

## 1. 当前 QMF 算法的真实工作机制

正式配置为uniform_qmf，H=3、K=4。先枚举全部联合配置，计算全部两项成本，再构造包含全量mergesort的经典oracle后端。初始incumbent均匀抽样，τ=C(incumbent)，m=1，B=ceil(2√N)。每轮从0至min(ceil(m)−1,remaining−1)均匀抽j；标记C(z)<τ的配置；p=M/N，θ=asin√p，P_marked(j)=sin²((2j+1)θ)。按该解析概率抽配置，严格改善则更新τ并令m=1，否则m=min((8/7)m,√N)。预算结束返回当前配置索引，没有最优性保证。

这采用Dürr–Høyer/BBHT风格思想，实际执行是CPU解析概率模拟。理论黑盒O(√N) oracle queries、当前模拟CPU成本与完整索引构建必须分别报告。候选tie按(-R4_score,action.key)；枚举按根/左/右次序；Exact与Argmin取第一个最小值；QMF相等成本不替换incumbent。阈值判断严格小于，因此并列最优只要成本等于最小值均记最优。

依据：`PY/wg_qmf/index.py:125,146,157,166,184`；`search.py:50,59,71,99,173,191,216`；`quantum.py:18`。PY前缀与完整路径见附录。

## 2. 当前联合子树 cost 的可加性判断

**严格分类：CONDITIONALLY ADDITIVE。** 给定一个规划根的D、Q，其成本本身是ADDITIVE；条件性在于父划分改变子数据、MBR、Top-K与完整深度可行性。

令h(B,Q)=Σ_q 1[q∩B≠∅]，q=|Q|，叶点数m：

```
g(D,B,Q) = β_leaf·h(B,Q)/q + β_point·m·h(B,Q)/q
C(z) = Σ_(l∈leaves(z)) g(D_l,B_l,Q)
β_leaf = 1.2779084295340111e−09
β_point = 3.428255707467659
```

C_leaf是平均相交叶数，C_scan是平均相交叶点数总和。后者不是实际短轴过滤后的扫描数量。cross_partitions仅诊断，不是第三项。左右子树在固定父动作后没有目标耦合；当前K、min_leaf、固定H均为局部规则。

同一H3递归始终传同一个context_queries（configuration.py:185,196）。工作负载影响R4评分，但不破坏叶代价可加性。实际子节点日后出堆才重新筛选Q_n（index.py:271）。固定节点的局部均值可乘|Q_n|/|Q_train|转换为全训练集贡献，正因子不改变该节点最优解；但这不意味着滚动构建的最终整棵树全局最优。

缓存cost先累加整数叶命中数/扫描点数，再除q、乘权重。诊断保留这两个整数总量；逐叶直接浮点加总的恒等式另做ULP核验。每张表所有16,384个配置均通过可加性核验。没有改目标或加权以制造结论。

## 3. 经典动态规划递推是否成立

```
F_0(D,B,Q)=g(D,B,Q)
F_h(D,B,Q)=min_(a∈A_K(D,Q), full-depth feasible)
    [F_(h−1)(D_L(a),B_L(a),Q)+F_(h−1)(D_R(a),B_R(a),Q)]
```

不具备完整规划时F=+∞。证明按h归纳：固定a后的合法配置空间是左右合法空间笛卡尔积，目标为两项之和，故分别取最优；再在合法根动作中取最优。必须与生产代码保持一致：先过滤合法/min_child，再R4排序截Top-K，之后检查深层可行性；不能补第5个候选。

保存最佳动作和左右子解可以恢复完整最优配置。当前验证器不做memoization，但确实观察到重复状态；73次内部访问分别只有69、71、71个不同(h,点数,MBR)条件状态。对于同一根点集上稳定轴阈值过滤，这些MBR决定相同成员集合；一般数据结构中不能只凭任意摘要认定状态相同。未来缓存须同时包含Q、h、K、规则与模型版本。

满展开访问数S=Σ_(d=0)^(H−1)(2K)^d；终端访问数=(2K)^H。K4/H3为73和512，不是K^(2^H−1)的DP复杂度。实际时间还包含各状态候选/特征/评分/数据划分，以及叶查询相交。此验证器仍访问完整条件展开，避免的是16,384个完整联合配置的笛卡尔积物化，不能把它称为只访问7个内部节点。

全局max_depth=8、max_leaves=128约束正式root-only提交，但未作为H3规划的共享容量约束；故本递推精确的是当前局部问题。未来若让左右分配全局叶预算，需加预算维度做资源分配DP，不能假定现有递推自动覆盖。

## 4. Recursive Exact H3 的正确性验证

独立实现：`scripts/feasibility_v1.py::RecursiveExact`。直接复用生产enumerate_actions、split_positions、FrozenR4Prior、_bounds及相同softmax排序/可行性规则；不修改正式模块。恢复方案再交给生产evaluate_subtree_costs验算，并检查它实际属于枚举空间。

{validation_table}

三节点共49,152个完整枚举配置的叶加性恒等式通过；条件评分调用的动作、阈值与分数轨迹逐项完全相同。cost、root和完整配置的字面一致均通过，未仅以宽容差掩盖不一致。node251有4个最优配置，严格访问次序仍恢复了同一个配置。

1024点探针取已有输入前1024行，明确不是保存的正式节点；不满足8×256最小叶容量，枚举与递归均返回无完整规划，评分轨迹一致。它证明不可行性处理一致，不能用来解释NYC历史fallback的实际异常原因。

{space_table}

不同动作配置可能产生相同终端叶布局，因此“动作配置数”“叶布局数”“不同cost数”不能互换。详见 `report/CANDIDATE_SPACE_DETAILS.json`。

## 5. QMF 与经典搜索方法比较

### 表1：解质量与 Search-only 对照（B=2√N=256）

{quality_table}

说明：QMF/Random为20个种子；Beam为确定性单次；Exact/Argmin/Greedy重复计时20次不代表20个不同质量样本。成本是代理工作量单位，gap=(C−C*)/max(Cmax−C*,1e−12)，不是相对最优成本误差百分比。Random无放回，使用同一个预先指定种子协议；QMF抽象调用与数组访问物理成本不等价。

当前Beam是生产prior-mass前缀Beam，不是成本引导Beam。额外包含width=B对照，避免只让Beam16检查16个候选而让QMF消耗256预算。它在这三张表中质量仍较差，但不能推论所有Beam算法都弱于QMF。

Greedy proxy在三节点均与相同Q下的不回溯R4 H3 rollout完全一致。它不是重新构建整棵greedy索引。Recursive Exact需要条件节点数据/结构，不能被虚构成“只在flat cost table上运行的同一个DP”；因此该行Search-only时间为N/A，真实时间在表2。

### 表2：End-to-End Local Optimization 时间与内存

{time_table}

“总秒”从节点数据与已加载模型出发，包含候选、条件构造、cost与搜索；数据IO和模型加载另记在原始JSON，不混入局部优化时间。QMF/Random/Beam/Exact/Argmin均计入完整枚举与全cost预计算。RecursiveExact的比较操作融合在递归阶段，未伪称search物理成本为零；对应列标“融合递归”。峰值为独立进程RSS（含Python/Torch、输入及验证），不是纯算法工作区；25 ms监测的局部RSS另存原始汇总。

小节点121、251的精确枚举/递归中位耗时比分别为{ratios[121]:.3f}×、{ratios[251]:.3f}×。根节点比为{ratios[0]:.3f}×，但仅一次，不能据此做稳健加速结论或推广到亿级构建。Argmin在节点121的总时间可能因评分/枚举噪声高于Python Exact；这不矛盾于其单独搜索更快。不要从数毫秒搜索差异反推总秒的因果差异。

## 6. 搜索质量和实际耗时分析

### 表3：20种子、四档预算的QMF结果

{budget_table}

“改善率”为最终成本严格小于该次初始incumbent的比例；“Q/T/R胜”为相同种子下QMF成本更低／成本相同／Random更低。每次原始记录、所选配置/root、检查数和成本表SHA在 `report/ALL_SEARCH_RUNS.csv`。预算变化时随机采样轨迹不保证嵌套，有限样本最优命中数不必逐档单调。

在B256上，QMF合计最优命中{q2hit}/60，Random为{r2hit}/60；12个节点×预算组合中QMF平均gap均更小。这支持“这些已冻结真实成本表上，解析QMF具有预算化质量优势”；不支持跨数据集普遍稳定性或CPU优势。QMF仍有搜索失败：默认预算在node0只命中6/20，在node121命中8/20，node251命中17/20。

默认预算的最优root命中分别为 {', '.join(short(r['node'])+': '+str(r['optimal_root_hits'])+'/20' for r in roots2)}；完整最优配置命中与最优root命中不是同一指标，root-only系统应同时关注二者。

成本表已有时，QMF相对Argmin的搜索中位耗时比分别为node0 {speed_search[0]:.1f}×、node121 {speed_search[121]:.1f}×、node251 {speed_search[251]:.1f}×。Argmin是精确最优，而QMF默认预算尚有失败，所以当前CPU额外搜索控制器没有已证的计算效率优势。

### 表4：复杂度及实际分段成本

{complexity_table}

同一张表、同一随机种子的分段计时如下。mergesort是在相同输入上另行测量的同款排序；oracle构造和_qmf循环由原函数直接计时，并核对selected_index与uniform_qmf一致。它们来自配对重跑，不是从正式总时间反算，不能机械相减作为精确闭合分解。

{profile_table}

既有正式亿级构建的时间上下文（只读，未重跑）：

{formal_table}

正式日志只保存合计quantum_search_simulator_seconds，内部cost排序/采样分量是NOT RECORDED。本次不能补造亿级阶段分项。QMF控制器占比仅约0.001%—0.0075%；总体瓶颈在R4评分和配置生成。NYC仍有143次fallback，未因本诊断删除或改写。正式分项对失败规划的覆盖不完整，不能保证相加完全等于总构建时间。

## 7. 是否存在更高效的经典精确算法

存在：当前条件可加目标下，Recursive Exact省去完整配置组合和全配置成本表，得到与现有Exact H3相同的最优解。小节点计时显示更快；根节点的评分/划分工作仍占主导，没有依据宣称数量级提速。已物化成本表的情形则直接Argmin最合理，不需要再做近似最小值搜索。

本次递归法未使用memoization，未实现正式构建器替换，也未运行在线查询。下一步应在隔离分支对条件状态共享、重复R4评分和数据划分开销做等价优化，再用统一serving kernel验证完整树质量与构建成本。新的算法价值需要来自真实数据库效果，不能仅把标准Bellman递推包装成独立理论创新。

## 8. 当前 QMF 作为核心创新的主要问题

1. 经典后端已经知道全部成本并排序；在当前CPU程序中，最优值已有廉价精确提取方式。
2. 搜索空间不是没有结构的黑盒：固定父动作后的子问题独立，递归精确法是必须比较的强基线。
3. QMF在逻辑预算内的质量优势有实验支持，但解析oracle利用完整成本表计算marked质量；这种比较不是相同CPU资源下少量成本读取的证明。
4. 无可逆cost oracle、相干数据读取、门深度/门数/ancilla及噪声资源分析。已安装Qiskit 1.2.4与PennyLane 0.42.3，不等于正式路径调用了它们；本次没有运行电路或QPU。
5. 当前平均成本与真实短轴过滤、covered-subtree count shortcut仍有差距；局部surrogate改善没有直接证明在线latency改善。
6. 只有GeoLife reproduction三节点，全是N16,384，不能据此建立N伸缩曲线、四数据集泛化或全局索引最优性。

对十个核心问题的回答：Q1/Q2 当前CPU QMF不优于直接Argmin，成本表完成后无已证效率优势；Q3 在本次三表20种子的预算比较中优于Random，但跨数据集稳定性未证；Q4 优于当前prior-mass Beam实现的局部质量，不代表优于所有Beam；Q5/Q6 RecursiveExact避免完整组合并恢复精确最优配置；Q7 不宜继续把当前模拟搜索作为论文最强核心；Q8 是理论搜索思想的解析模拟；Q9 不支持实际量子加速；Q10 需独立量子oracle/资源/成功概率贡献，并在强经典结构化算法前保持价值。

## 9. 保留或调整量子路线的利弊

### 表5：三条路线决策矩阵

{routes_table}

路线A可保存当前可复现资产，保留QMF作为辅助算法比较；需要诚实改写定位。继续以当前QMF主打CCF-A的主要风险不是缺少“量子”图示，而是同一目标存在简单且精确的经典利用结构方式。

路线B最贴近当前证据。递归只处理条件状态，减少完整配置输出和成本组合；依然要减少特征、评分与数据拷贝开销，不能把DP状态数降低等同于所有构建成本等比例降低。投稿需证明lookahead在统一查询内核下的数据库价值、代价质量与构建开销权衡，并与外部相关工作比较。

路线C各方向的现实边界：

| 方向 | 接近程度／改动 | 假设与判断 |
|---|---|---|
| Lazy Configuration Generation | 最接近；可按条件计数建立配置编号/反编号 | 是经典生成优化；若完整条件图已建好，可直接DP求优，本身不是量子贡献。 |
| On-demand Cost Evaluation | 中等；改变搜索接口，避免完整cost表 | 必须实现真实按需语义并记读取/计算代价；当前解析后端靠全表知道marked质量，无法原样变成廉价懒oracle。 |
| Reversible Cost Oracle | 重大重构 | 需可逆分割/MBR/查询相交/整数累计、有限精度比较、uncompute；R4与数据访问成本必须计入，不能假定QRAM免费。 |
| Structured Quantum Search | 理论与结构实现均有工作量 | 利用结构后还须与结构化经典DP比；在小K上作量子min未必抵消制备开销。 |
| Quantum–Classical Hybrid | 范围可大可小 | 明确哪个子问题实际量子执行、数据如何进入与返回、总资源；仅把CPU概率计算命名hybrid不形成贡献。 |
| Small Qiskit Circuit Validation | 已有依赖，可隔离做小真值表实验 | 能验证相位/扩幅/测量语义；预编译全cost小oracle无法证明大数据可逆cost可扩展，更不等于QPU加速。 |

如研究非可加目标，只能从真实执行模型出发。例如全局叶/内存预算可能用预算DP解决；内部节点访问或covered shortcut有时仍能写成局部加性项，不应称“自然不可分解”。缓存冲突、共享页面布局、跨子树并发资源等若导致耦合，需先证明该成本实际存在、可测且影响数据库执行，再定义目标，并与相应的经典资源DP、branch-and-bound、整数规划或启发式优化公平比较。不能为了量子优势随意加入交叉惩罚。

## 10. 推荐的最终论文研究方向

近期主线建议：**Workload-Conditioned Structured Joint Subtree Optimization with Root-Only Receding-Horizon Construction**。QMF保留为搜索策略/理论对照或独立后续量子研究，不直接删除正式实现。

最关键下一实验是小规模完整索引的受控链条：R4-greedy → Exact H1（分离cost目标）→ Recursive Exact H3（分离前瞻）→ QMF H3（分离搜索）。共享候选与权重，使用同一个静态查询内核，分别测count和完整ID返回，再分析root-only与fallback。这比继续扩大相同N成本表上的随机种子更能证明数据库论文价值。本次测试已经足以确认局部精确递推，无需为这一核心假设重跑亿级构建。

### 表6：创新点与实验证据

{innovation_table}

**GO：否，当前证据不支持把现有CPU QMF模拟继续作为最核心的计算效率创新。** Argmin快且精确；RecursiveExact利用相同目标结构并恢复同一最优配置；控制器在既有总构建中占比极低。

**CONDITIONAL GO：可以保留QMF作为辅助方法或独立理论方向。** 条件是完整披露解析模拟、预计算与排序成本，保留强经典对照，补多数据集预算质量，并仅在建立真实oracle/资源/成功概率证据后提升量子主张。

**PIVOT：建议转向结构化联合子树优化。** 当前数学和真实局部实验支持该路线；优先验证统一内核下的完整索引价值，而不是立即替换生产代码或宣称DP本身是新理论。

**BLOCKER：核心是贡献归因和证据不足。** 需要证明前瞻本身的在线价值，公平处理count内核，解决来源/权重校准与fallback记录，完成必要对照，并核实相对外部数据库索引优化文献的新颖性。

## 导师汇报摘要（500字以内）

当前QMF在已枚举并计算全部成本的联合子树配置上，用CPU解析公式模拟振幅放大和阈值改善，并不执行量子硬件。本次核实两项cost在固定查询上下文下可加，独立实现递归精确优化，在三个恢复的GeoLife reproduction节点上得到与现有Exact H3完全相同的最优成本、根动作和配置，同时避免物化16,384个完整组合；不可行边界也一致。20种子、四预算实验显示解析QMF的解质量优于Random，但成本表已备好时，Argmin更快且精确；默认预算QMF仍会漏掉最优解。递归法在小节点更快，根节点仍受相同评分和数据划分成本限制，不能宣称亿级提速。建议把结构化联合优化作为主线，保留QMF作对照，下一步在统一查询内核下比较R4-greedy、Exact H1、Recursive H3与QMF，确认收益来自成本目标、前瞻还是搜索。

## 复现、文件与证据索引

本目录：`{RUN}`。ROOT=`{ROOT}`；PKG=`ROOT/QMF_PostGIS_100M_Repro_20260910`；PY=`PKG/src/common/python/qmapli`。

- `protocol.json`：资源、种子、预算、比较规则；`local_experiment_plan.json`：预先排列的独立任务与重复。
- `inputs/node_manifest.json`：输入来源、SHA、恢复祖先划分、点数/MBR精确验证；`node_availability.json`：缺失节点类型。
- `scripts/guard.py`：每任务CPU/RSS/timeout；`scripts/prepare_nodes.py`：恢复已有节点；`scripts/feasibility_v1.py`：独立递归、原枚举验证、A/B对照。
- `jobs/<task>/command.json`：完整argv、shell命令、环境、CPU亲和；`receipt.json`：退出、耗时与内存；`resources.csv`：25 ms采样；stdout/stderr完整保留。
- `artifacts/<node>/validation.json`：精确成本、root、完整配置、评分轨迹和恒等式；`universe.pkl`与`costs.npz`为本次新建的真实成本表快照。
- `report/ALL_SEARCH_RUNS.csv`：1224条原始搜索记录；`ALL_QMF_TIME_COMPONENTS.csv`：240条排序/循环计时；`LOCAL_TRIALS_WITH_RESOURCES.json`：56条完整优化记录。
- `report/TABLE1_SEARCH_QUALITY.csv`、`TABLE2_LOCAL_TIME_MEMORY.csv`、`TABLE3_QMF_RANDOM_PAIRED.csv`：可追溯汇总；`FORMAL_BUILD_TIME_CONTEXT.csv`保留原正式结果路径。
- `formal_files_before.json`与`formal_files_after_verification.json`：{len(frozen_before)}个正式代码/配置/权重/关键结果文件SHA一致。

可复现单个任务的命令示例（`--name`必须换成新的唯一名称，避免覆盖）：

```bash
python -B scripts/guard.py --name NEW_UNIQUE_NAME -- \
  python -B scripts/feasibility_v1.py local geolife100m_node121 \
  --method recursive_exact --seed 20261009
```

生产代码关键定位：

| 判断 | 文件／函数／行号 |
|---|---|
| 条件候选与Top-K | PY/workload_action_interaction/actions.py::enumerate_actions:35；PY/wg_qmf/configuration.py::_enumerate:133，排序:163，递归:185/196，组合:236 |
| 冻结评分 | PY/wg_qmf/prior.py::FrozenR4Prior:23、score_actions:38 |
| 两项cost与缓存 | PY/wg_qmf/cost_oracle.py::evaluate_subtree_costs:35、_cost_table:88；cached_oracle.py::cached_work_metrics:7 |
| 全表、排序、阈值搜索 | PY/wg_qmf/search.py::AbstractPhaseCostOracle:50、排序:59、measure:71、_qmf:99、uniform_qmf:173 |
| 概率公式 | PY/wg_qmf/quantum.py::analytic_distribution:18 |
| exact、beam和tie | PY/wg_qmf/search.py::_classical_result:191、exhaustive_search:216、beam_search:224 |
| root-only、全局限制、fallback | PY/wg_qmf/index.py::_select_joint_root_action:84、全部成本:146、root:184、heap:240、限制:262、Q_n:271、fallback:300/308、commit:328 |
| count与ID内核边界 | PKG/src/qmap/cpp/src/qmap_nai/static_qmap_index.cpp::range_query:231、range_count:235、query_impl:240；include/qmapli/range_index.hpp:30 |

独立代码的函数精确行号另见 `report/DIAGNOSTIC_CODE_INDEX.csv`。更完整理论审计为 `PHASE_A_THEORY_AUDIT.md`。

理论参考：[Dürr–Høyer, A Quantum Algorithm for Finding the Minimum](https://arxiv.org/pdf/quant-ph/9607014)；[Boyer et al., Tight Bounds on Quantum Searching](https://arxiv.org/pdf/quant-ph/9605034)。这些文献支持理想查询模型，不提供当前CPU端到端加速证据。外部“首次提出”新颖性在本次不作未经核验的声明。
'''

with (RUN/'report/QMF_ALGORITHM_FEASIBILITY_REPORT_ZH.md').open('x') as f:f.write(report)
index=[]
for path in (RUN/'scripts').glob('*.py'):
    tree=ast.parse(path.read_text())
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.ClassDef)):
            index.append({'file':str(path.relative_to(RUN)),'symbol':n.name,'line':n.lineno})
writecsv('DIAGNOSTIC_CODE_INDEX.csv',index)
writejson(RUN/'report/REPORT_FACTS.json',{'validated_real_nodes':3,'infeasibility_probe':1,'local_jobs':56,'search_rows':1224,
    'qmf_runs':240,'qmf_default_hits':q2hit,'random_default_hits':r2hit,'total_default_seed_trials':60,
    'maximum_rss_mib':max_mem,'maximum_task_seconds':max_task,'enumeration_over_recursive_time_ratios':ratios,
    'qmf_over_argmin_search_time_ratios':speed_search,'formal_files_unchanged':len(frozen_before)})
print(json.dumps(readjson(RUN/'report/REPORT_FACTS.json'),ensure_ascii=False,indent=2))
