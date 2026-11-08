import csv,json,re,shutil,sys
from pathlib import Path
import numpy as np
from initial_audit import ROOT,FLOOD,KIT,sha,write
def read(p,default=None):return json.loads(p.read_text()) if p.exists() else default
def rows(p):return list(csv.DictReader(p.open())) if p.exists() else []
def export(p,fields,data):
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
def main():
    cfg=read(ROOT/'01_environment/frozen_protocol.json');queries=rows(ROOT/'03_validation/frozen_queries/skewed_2d_queries.csv');bounds={q['query_id']:[q[x] for x in ['xmin','ymin','xmax','ymax']] for q in queries}
    wanted=[q['query_id'] for q in queries if q['split']=='performance'];cwanted=[q['query_id'] for q in queries if q['split']=='correctness']
    cr=rows(ROOT/'06_correctness/raw_correctness.csv');correct=[dict(Query_ID=r['query_id'],Flood_Count=r['count_result'],Reference_Count=r['truth_count'],Match=int(r['exact']=='1' and r['count_exact']=='1' and r['missing']=='0' and r['extra']=='0'),Query_Bounds=json.dumps(bounds[r['query_id']])) for r in cr]
    export(ROOT/'FLOOD_SKEWED2D_CORRECTNESS.csv',['Query_ID','Flood_Count','Reference_Count','Match','Query_Bounds'],correct)
    ordered=[];raw=[];rounds=0;errors=[];summaries=[]
    for rep in range(5):
        p=ROOT/'05_queries'/f'latency.r{rep}.csv';p=p if p.exists() else Path(str(p)+'.part')
        rr=rows(p)
        for r in rr:
            if len(r)!=7 or any(v is None for v in r.values()):errors.append('Truncated latency row');continue
            raw.append(r);ordered.append(dict(Round=int(r['repetition'])+1,Query_ID=r['query_id'],Latency_ms=int(r['latency_ns'])/1e6,Result_Count=r['result_count'],Query_Class=r['selectivity_group']))
        ready=read(ROOT/'05_queries'/f'latency.r{rep}.csv.ready')
        if ready and [r['query_id'] for r in rr]==wanted and len(rr)==3000 and all(r['method']=='flood' and int(r['repetition'])==rep and int(r['ordinal'])==i for i,r in enumerate(rr)):
            rounds+=1;summaries.append(ready)
        elif rr:errors.append(f'Round {rep+1} incomplete or order invalid')
    export(ROOT/'FLOOD_SKEWED2D_LATENCIES.csv',['Round','Query_ID','Latency_ms','Result_Count','Query_Class'],ordered)
    full=read(ROOT/'03_validation/full_input_validation.json',[])
    b=rows(ROOT/'04_build/build.csv');artifact=read(ROOT/'04_build/artifact.json');br=read(ROOT/'04_build/full_build_receipt.json',{})
    build_ok=bool(b and artifact and br.get('returncode')==0 and not br.get('stop_reason'))
    if build_ok:
        p=Path(artifact['path']);build_ok=p.exists() and sha(p)==artifact['sha256'] and p.stat().st_size==9+12*204986702
        if build_ok:
            with p.open('rb') as f:build_ok=int.from_bytes(f.read(8),'little')==204986702
    corr_ok=len(cr)==1000 and [r['query_id'] for r in cr]==cwanted and all(r['Match']==1 for r in correct) and all(r['method']=='flood' and r['truth_count']==r['result_count']==r['count_result'] for r in cr)
    protected=read(ROOT/'01_environment/protected_results.json',{})
    preserved=all(Path(p).exists() and sha(p)==h for p,h in protected.items())
    receipts=[read(ROOT/'06_correctness/correctness_receipt.json',{}),read(ROOT/'05_queries/timing_receipt.json',{})]
    phase_ok=all(r.get('returncode')==0 and not r.get('stop_reason') for r in receipts)
    fairness=[read(ROOT/'06_correctness/summary.json',{}),*summaries]
    fair_ok=len(fairness)==6 and all(s.get('fairness',{}).get('load_count')==1 and all(s.get('fairness',{}).get(k)==0 for k in ['query_rebuild_count','query_reload_count','query_training_count','query_external_process_count','query_python_count','query_quantum_count']) for s in fairness)
    counter_ok=len(fairness)==6 and [s.get('fairness',{}).get('query_count') for s in fairness]==[2000,3300,6300,9300,12300,15300]
    counts={}
    classes={q['query_id']:q['selectivity_group'] for q in queries}
    for r in raw:
        if r['selectivity_group']!=classes.get(r['query_id']) or int(r['latency_ns'])<0 or not 0<=int(r['result_count'])<=204986702:errors.append('Invalid class, count or latency: '+r['query_id'])
        if r['query_id'] in counts and counts[r['query_id']]!=r['result_count']:errors.append('Nondeterministic COUNT: '+r['query_id'])
        counts[r['query_id']]=r['result_count']
    checks=dict(source_version_verified=(ROOT/'01_environment/binaries.json').exists(),full_input_points=len(full)==2 and all(d['points']==204986702 for d in full),frozen_queries=sha(ROOT/'03_validation/frozen_queries/skewed_2d_queries.csv')==cfg['queries'][-1]['SHA256'],full_build=build_ok,correctness_1000=corr_ok,timed_rounds_5=rounds==5,latencies_15000=len(raw)==15000,warmup_completed=phase_ok,phase_receipts=phase_ok,fairness_counters=fair_ok,prior_results_preserved=preserved,no_record_errors=not errors)
    grid=read(ROOT/'04_build/grid_integrity.json',{})
    checks['grid_records_complete']=grid.get('sum_bucket_counts')==204986702 and grid.get('point_ids_exact_source_ordinals') is True
    binaries=read(ROOT/'01_environment/binaries.json',{})
    checks['unchanged_binary_hashes']=bool(binaries) and all(Path(p).exists() and sha(p)==v['expected'] for p,v in binaries.items())
    source_manifest=read(ROOT/'01_environment/source_manifest.json',{})
    source_root=Path(source_manifest.get('source_root','/nonexistent'))
    checks['unchanged_source_files']=bool(source_manifest.get('files')) and all((source_root/name).is_file() and sha(source_root/name)==digest for name,digest in source_manifest.get('files',{}).items())
    qverify=read(ROOT/'03_validation/query_verification.json',{})
    checks['all_frozen_query_files']=bool(qverify.get('files')) and all(sha(ROOT/'03_validation/frozen_queries'/name)==digest for name,digest in qverify.get('files',{}).items())
    checks['diagnostic_tests_passed']=all(read(ROOT/'03_validation'/f'validation_{n}/PASS.json',{}).get('checks')==4808 for n in [16384,1000000])
    count_edge_runs=[read(p,{}) for p in (ROOT/'03_validation').glob('count_kernel_edges_*/PASS.json')]
    checks['count_kernel_edge_diagnostics']=any(r.get('status')=='PASS' and r.get('exact_COUNT_and_ID_checks')==4928 and r.get('verification_script_sha256')==sha(ROOT/'tools/verify_count_edges.py') for r in count_edge_runs)
    checks['reference_full_point_count']=read(ROOT/'06_correctness/load_pass.json',{}).get('points')==204986702
    checks['reference_gist_built']=read(ROOT/'06_correctness/reference_pass.json',{}).get('index_bytes',0)>0
    checks['reference_cluster_verified']=read(ROOT/'06_correctness/reference_cluster_pass.json',{}).get('audit',{}).get('points')==204986702
    bundle=read(ROOT/'01_environment/native_bundle_manifest.json',{})
    try:
        from native_artifacts import verify as verify_native_snapshot
        verify_native_snapshot()
        checks['reproduction_native_snapshot']=bool(bundle)
    except (OSError,AssertionError,ValueError,ImportError) as exc:
        checks['reproduction_native_snapshot']=False
        errors.append('Native reproduction snapshot: '+str(exc))
    actual_helpers={str(p.relative_to(ROOT)):sha(p) for p in [*sorted((ROOT/'tools').glob('*.py')),*sorted((ROOT/'tools').glob('*.cpp')),ROOT/'FLOOD_SKEWED2D_REPRODUCE.sh']}
    checks['reproduction_helpers_manifest']=bundle.get('helper_sha256')==actual_helpers
    checks['exact_warmup_and_query_counters']=counter_ok
    complete=all(checks.values());status='EXPERIMENT_COMPLETED' if complete else 'EXPERIMENT_INCOMPLETE'
    metrics=dict(Dataset='Skewed 2D',Method='Flood-V2',Points=204986702 if checks['full_input_points'] else 'N/A',Build_Time_s=int(b[0]['total_ns'])/1e9 if build_ok else 'N/A',Index_Size_MiB='N/A',Mean_Latency_ms='N/A',P95_Latency_ms='N/A',P99_Latency_ms='N/A',QPS='N/A',Peak_RSS_MiB='N/A',Correctness=f'{sum(r["Match"] for r in correct)}/{len(correct)} exact' if cr else 'NOT_RUN',Status=status)
    peak_parts={}
    if build_ok:peak_parts['build_getrusage_bytes']=int(b[0]['peak_rss_kib'])*1024
    for name,receipt in [('build',br),('correctness',receipts[0]),('timing',receipts[1])]:
        if receipt:peak_parts[name+'_guard_historical_bytes']=receipt.get('historical_peak_rss_bytes',0)
    for i,s in enumerate(fairness):
        if 'backend_peak_rss_kib' in s:peak_parts[f'query_summary_{i}_bytes']=(s['backend_peak_rss_kib']+s['client_peak_rss_kib'])*1024
    if complete:
        ns=np.array([int(r['latency_ns']) for r in raw],dtype=np.float64)
        metrics.update(Mean_Latency_ms=float(ns.mean()/1e6),P95_Latency_ms=float(np.quantile(ns,.95)/1e6),P99_Latency_ms=float(np.quantile(ns,.99)/1e6),QPS=float(1e9/ns.mean()),Peak_RSS_MiB=max(peak_parts.values())/2**20)
    export(ROOT/'FLOOD_SKEWED2D_METRICS.csv',list(metrics),[metrics]);write(ROOT/'07_metrics/acceptance.json',dict(status=status,checks=checks,errors=errors,completed_rounds=rounds,records=len(raw),memory_components=peak_parts))
    buildlog=''
    for name in ['full_build_command.json','full_build.log','ownership.csv','build.csv','full_build_receipt.json','artifact.json']:
        p=ROOT/'04_build'/name
        if p.exists():buildlog+='\n### '+name+'\n'+p.read_text()
    for relative in ['03_validation/full_input_validation.json','03_validation/query_verification.json','01_environment/binaries.json','01_environment/environment_comparison.json']:
        p=ROOT/relative
        if p.exists():buildlog+='\n### '+relative+'\n'+p.read_text()
    (ROOT/'FLOOD_SKEWED2D_BUILD_LOG.txt').write_text(buildlog or 'Full build has not completed. See 04_build/controller.log.\n')
    diagnosis=ROOT/'08_reports/FLOOD_SKEWED2D_DIAGNOSIS.md'
    if diagnosis.exists():shutil.copyfile(diagnosis,ROOT/diagnosis.name)
    bullets='\n'.join(f'- [{"x" if v else " "}] {k}' for k,v in checks.items())
    table='\n'.join(f'| {k} | {v} |' for k,v in metrics.items())
    data='\n'.join(f'- `{d["path"]}`: {d["points"]} points, SHA-256 `{d["sha256"]}`, range {d["min"]} to {d["max"]}.' for d in full)
    deliverables=[ROOT/('FLOOD_SKEWED2D_'+suffix) for suffix in ['METRICS.csv','LATENCIES.csv','BUILD_LOG.txt','CORRECTNESS.csv','DIAGNOSIS.md','REPORT.md','REPRODUCE.sh']]
    deliverable_links='\n'.join(f'- [{p.name}](<{p}>)' for p in deliverables)
    integrity=read(ROOT/'07_metrics/post_run_integrity.json',{})
    integrity_note=('正式计时结束后再次逐字节校验原始与规范化全量输入，SHA 与构建前全量扫描一致；点档案已复制到独立输出目录并核对 SHA。详见 `07_metrics/post_run_integrity.json`。持久副本仅为点档案，不改变 Index Size=N/A。' if integrity.get('status')=='PASS' else '本次全量输入的点数、范围及 SHA 校验凭证见 `03_validation/full_input_validation.json`。')
    report=f'''# Flood-V2 / Skewed 2D

状态：**{status}**。完成正式查询轮次 {rounds}/5，原始延迟记录 {len(raw)}/15000，正确性 {metrics['Correctness']}。

## 一、实验目标
仅补齐 Flood-V2 × 全量 Skewed 2D；禁止模拟、预测、删去长尾、修改冻结矩形或覆盖其他实验结果。

## 二、实验环境
Intel Core i7-10700，16 logical CPUs，约 31.2 GiB RAM；环境原始输出见 `01_environment`。Python 3.10.12、NumPy 1.26.4、GCC 11.4.0、PostgreSQL 14.24。独立 systemd slice 的 memory.high/max 为 22/24 GiB，swap.max=0，host reserve=3.5 GiB。主机仍运行用户桌面应用，未停止无关进程。参考库如已建立，其存储布局及设置见 `01_environment/postgres_storage.json`。

## 三、数据集完整性
{data or '完整校验尚未完成。'}
使用冻结 min-max 规范化 CSV，zero-based source ordinal IDs；native Point 为 float32 x/y + uint32 ID，double 模型坐标精确提升。原始数据无采样、过滤、去重。

## 四、原 Flood 实现及版本
源码根 `{KIT / 'implementations/shared/repro'}`。源码 digest `0b4b36b8a48df80b070bf9d011a870bf026dc445dd05da94c9f8bf880a8ecba2`，Git HEAD `066ae7bab987183451ee180ff1020705528533d3`。原 V2 构建器/runtime/query driver/PG extension SHA 与历史版本一致，未修改算法。`Flood<2,32,64,1>`，训练矩形决定 orientation，冻结网格/模型参数；没有新增参数搜索。

## 五、历史失败原因
V1 的 map ID ownership 造成大量逐点分配；历史 V2 已改 compact ownership，但另一次 Build 在主机其他应用占用较高时触发 host reserve。对应停止阶段 oom/oom_kill 增量为 0；不称为已证实 OOM。详见 `FLOOD_SKEWED2D_DIAGNOSIS.md` 及原始 receipts。

## 六、修复及优化方案
使用原 V2 二进制，独立输出和运行目录，全局锁串行运行；分块校验避免额外全量内存。保留安全阈值。参考库需独立存储时使用外接 tablespace，并在报告中披露与历史 NVMe reference 的差别。没有修改输入精度或 Flood 查询行为。辅助采样修复记录见诊断文档。外置参考表首次检查因离散读取过慢而主动停止，完整保留部分证据；采用原生 CLUSTER points USING points_gist 重排参考表后重新从第 1 条检查全部 1000 条，行数/ID 域/ID 和及索引状态另行验证。该物理布局调整不改变原始 ID、坐标、SQL 谓词或 Flood 算法，也不计入 Flood 构建与正式查询耗时。

## 七、构建过程
先通过 16,384 与 1,000,000 点各 4,808 次诊断验证，再完成全量文件校验才允许 Build。Build Time 取原程序 `total_ns`，等于 index build + archive save，排除 CSV read；阶段时间、资源和时间戳见 `FLOOD_SKEWED2D_BUILD_LOG.txt`。构建成功：{build_ok}。点档案：{artifact if artifact else '尚无完成档案'}。

本次 Build 外层控制器随会话中断，辅助 host/cgroup trace 在结束前约 62 秒缺失。原始 native `getrusage` 与 `/usr/bin/time -v` 完整记录整个构建进程峰值，systemd journal 证实成功退出；恢复 receipt 明确标记，不伪造最终 memory.events。详见诊断报告。现有成功构建没有重跑。

## 八、正式查询协议
冻结 query SHA `66fc69a347738af95f89f800f5894c9356b79ff8b036a840c7e280966b8d58dd`，6300 条中 train/validation/correctness 各 1000、warmup 300、performance 3000。prepared SQL COUNT，单一持久连接/worker，最低可用 CPU affinity，jit off，parallel query workers=0，300 warmup 后 5×3000；计时包含参数格式化及 PQexecPrepared 往返，不含 preload/构建/结果写盘。没有删去长尾或改变执行顺序。

## 九、正确性验证
SQL PostGIS truth 与 Flood 返回 IDs 双向 EXCEPT，另检查 COUNT kernel；必须 1000/1000、missing=extra=0。当前：{metrics['Correctness']}。诊断验证额外覆盖重复坐标、精确/nextafter 边界、稠密/稀疏/空区域及保存重载。正式参考 SQL 不使用伪造或改写答案。完整明细见 `FLOOD_SKEWED2D_CORRECTNESS.csv`。

## 十、七项性能指标
| Field | Value |
|---|---|
{table}

Index Size 为 N/A：点档案 preload 会重建 learned/query state，不能将原始点存储、reported_index_bytes 或 Peak RSS 当成可比较的持久化索引大小。Mean/P95/P99 只在全量正式验证完成后计算，使用全部 15000 条记录及 NumPy 默认 linear 分位数；QPS=1000/Mean_ms。Peak RSS 沿用历史 hybrid estimator，详情见 `07_metrics/acceptance.json`；cgroup peak/进程树总 RSS 仅作诊断。

## 十一、与历史 Flood 实验的口径对照
数据处理、代码二进制、训练方向策略、构建计时、COUNT SQL、预热/轮次/冻结查询、分位数、正确性与 RSS estimator 保持一致。新输出与 runtime 路径、运行日期、实际主机背景负载、独立 slice 名称、reference tablespace 位置、参考表经 GiST 物理重排及磁盘保护预留不同；不能宣称完全同一运行环境。NVMe 剩余空间不足以满足旧整管线 80 GiB gate，采用独立存储且不更改正式算法/指标定义。其他三个数据集的既有数字保持原样。

本次 MemTotal 比历史锁少 8 KiB；kernel/CPU/Python 对照见环境文件。Build 最后约 62 秒辅助监控缺口已披露，正式峰值 RSS 的完整进程测量仍有原始凭证。

## 十二、结果可信度检查
{bullets}

附加错误：{errors}。{'全部关键检查通过；Index Size 按已核实的历史口径明确填 N/A，其余六项均为真实测量。' if complete else '未完成指标填写 N/A；部分构建或查询结果不代表完整实验成功。'}所有阶段原日志保留，复现脚本默认创建新目录，防止覆盖。

独立审计 `07_metrics/independent_audit.json` 使用 Python 标准库 math.fsum 与显式 linear 分位数插值复算，核对全部原始/导出延迟与正确性记录，并保存七个交付文件的 SHA。{integrity_note} 复现依赖和恢复测试的适用范围见 `01_environment/REPRODUCTION_DEPENDENCIES.md`；不宣称已在全新机器上再次执行全量实验。

## 十三、论文表格可用结果
{'可使用 FLOOD_SKEWED2D_METRICS.csv；Index Size 必须保留 N/A，环境差异和历史 RSS 定义需披露。' if complete else '本次尚无通过完整验收的论文行，不得用部分结果填补主表。缺失环节详见上述验收及各阶段日志。'}

实际输出根：`{ROOT}`。运行流程与恢复说明见 `FLOOD_SKEWED2D_REPRODUCE.sh` 和 `08_reports/PROGRESS.md`。

七个交付文件的实际保存位置：

{deliverable_links}
'''
    report=re.sub(r'(?m)^(## .+)\n(?=\S)',r'\1\n\n',report)
    (ROOT/'FLOOD_SKEWED2D_REPORT.md').write_text(report);shutil.copyfile(ROOT/'FLOOD_SKEWED2D_REPORT.md',ROOT/'08_reports/FLOOD_SKEWED2D_REPORT.md')
    for name,sub in [('FLOOD_SKEWED2D_METRICS.csv','07_metrics'),('FLOOD_SKEWED2D_LATENCIES.csv','05_queries'),('FLOOD_SKEWED2D_CORRECTNESS.csv','06_correctness')]:shutil.copyfile(ROOT/name,ROOT/sub/name)
    print('Flood-V2 / Skewed 2D')
    for label,key in [('Build Time (s)','Build_Time_s'),('Index Size (MiB)','Index_Size_MiB'),('Mean Latency (ms)','Mean_Latency_ms'),('P95 Latency (ms)','P95_Latency_ms'),('P99 Latency (ms)','P99_Latency_ms'),('QPS','QPS'),('Peak RSS (MiB)','Peak_RSS_MiB'),('Dataset Points','Points'),('Correctness','Correctness')]:print(label+':',metrics[key])
    print('Completed Query Rounds:',rounds,'\nRaw Latency Records:',len(raw),'\nExperiment Status:',status,'\nReports:',ROOT)
    for path in deliverables:print('Report:',path)
if __name__=='__main__':main()
