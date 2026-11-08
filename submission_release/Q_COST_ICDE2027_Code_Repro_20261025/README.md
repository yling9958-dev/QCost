# Q-COST / Hybrid-QMF — submission code and reproduction materials

本包为 **2026-10-25** 整理的 Q-COST 投稿复现材料，**不包含数据集**。
包含当前代码、冻结 R4 模型、实验参数与种子、节点身份与离线 Exact 参考、
真实测量记录、统计和绘图脚本。解压后先阅读 `REPRODUCE.md`。

- `code/hybrid/`：当前五版本消融实现，选择消融为 **Random Frontier Selection**。
- `code/selection/`：独立 QMF × Feedback 专项实验，包含事件级记录接口。
- `code/fullscale/`：生产索引 Python/C++/PostgreSQL 代码、基线适配器和固定依赖信息。
- `code/gate_prototype/`：门级 QMF 小规模验证代码及原有测试。
- `models/`、`configs/`、`references/`：冻结模型、40+40 节点元数据、30 个种子和离线参考。
- `results/`：已完成实验的标量测量与统计，**不是空间数据集或查询工作负载**。
- `plots/`：当前图6—16及选择机制专项图的真实绘图数据和脚本。
- `tables/`：当前 TABLE II 五版本消融表和 TABLE III 专项分析表。
- `reproduce/`：可在新路径使用的检查、复算、绘图及外部输入实验入口。
- `provenance/`：原文件 SHA-256、版本说明与本次验证记录。

**明确排除**：GeoLife/Gowalla/NYC Taxi/Skewed 2D 点文件、原始轨迹、
节点样本 `input.npz`、训练/评估查询矩形、数据库、索引、数据缓存、构建产物、
虚拟环境、Git 历史、旧备份和完整逐事件实验日志。
`models/r4.pt` 是 7 KB 的已训练模型参数，不是数据集。

## Quick start: no spatial data required

```bash
python3 -m venv /tmp/qcost-artifact-venv
source /tmp/qcost-artifact-venv/bin/activate
python -m pip install -r requirements-analysis.txt
python -B reproduce/check_package.py
python -B reproduce/statistics.py --output /tmp/qcost-statistics
python -B reproduce/figures.py --output /tmp/qcost-figures
```

Use fresh output directories. These commands validate hashes, recompute Table II,
check Table III's point estimates, paired intervals and primary tests, and redraw
the current empirical figures from retained real measurements. They do not run
spatial benchmarks. The figure source includes the confirmed Flood × Skewed 2D
result, its real ECDF, and Figure 7(a) **without multiplier labels**. Figures
12/13/16 retain the removal of the formal Hybrid-BestFirst comparison.

To run optimizers, install `requirements-optimizer.txt` and supply the excluded
node inputs externally; see `REPRODUCE.md`. All new runs are written to a new
output directory. No command changes the recorded paper measurements.

## Scope of the reproduction claims

The export preserves the two distinct optimizer implementations used by Table II
and the selection diagnostics. Their accounting differs: the later diagnostic
Random branch avoids QMF-only priority calculation. They are not interchangeable
timing records. The production full-scale builder is retained separately from
the conditional-node optimizer. Historical standalone configuration budgets,
Hybrid wall-clock budgets and full-index timings remain separate protocols.

Historical BestFirst source branches are retained for provenance, but no current
table or figure export uses their measurements as the Random selection ablation.
The older five-way campaign driver is clearly named `run_ablation_historical.py`;
it is source history, not the current reproduction entry point.

The package contains code and empirical reproduction materials, not a rebuilt
submission manuscript or a claim that large-scale experiments were rerun during
packaging. Existing manuscript files and datasets remain untouched. Publication
measurements should not be replaced with smoke-check timings.

Dependencies and source provenance are retained under `code/fullscale/third_party`
and `LICENSES.md`; no new license is assigned by packaging.

