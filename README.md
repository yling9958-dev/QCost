# QMF / Hybrid-QMF 源码

本仓库只保留项目自身的索引与优化算法源码、必要模型和测试。
不包含外部对比索引、实验记录、日志、绘图目录、论文、数据集或重复发布快照。
本文件是项目唯一的 README。

## 目录

```text
src/
  python/
    qmapli/                         # R4 评分、QMF 构建、静态索引和查询支持
    hybrid_qmf/                     # 共享缓存、递归求值、QMF 调度与 incumbent feedback
    qmf_quantum_circuit_prototype.py # 可选的小规模门级原型
  cpp/                              # C++17 查询核心、C API 和查询命令行
  postgres/                         # 可选的 PostgreSQL 扩展
models/r4.pt                        # 原有 R4 参数，非数据集
tests/                              # 使用临时合成输入的源码测试
requirements.txt
requirements-circuit.txt             # 仅门级原型需要
```

## 环境

使用 Python 3.10、C++17 编译器和 CMake 3.20 或更新版本。Python 依赖沿用原项目版本：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PYTHONPATH="$PWD/src/python"
```

## 构建与查询

输入坐标须采用一致的归一化口径。点 CSV 的列名为 `x,y,id`；训练查询需包含
`xmin,ymin,xmax,ymax`。ID 须在 uint32 范围内。

```bash
python -m qmapli.wg_qmf.build_static_qw_index \
  --mode uniform_qmf --r4-checkpoint models/r4.pt \
  --points /path/to/points.csv --train-queries /path/to/train.csv \
  --index /path/to/output/qmf.idx --metadata /path/to/output/metadata.json \
  --context-seed 20260910 --beta-leaf 1.2779084295340111e-09 \
  --beta-point 3.428255707467659 --max-depth 8 --min-leaf-size 256 \
  --max-leaves 128 --budget-factor 2.0

cmake -S src/cpp -B build
cmake --build build --parallel 2
build/bin/qmf_query --method qmap_uniform_qmf \
  --index /path/to/output/qmf.idx --queries /path/to/queries.csv \
  --output /path/to/output/query_ids.csv
```

C++ 查询 CSV 的列顺序为
`query_id,selectivity_group,split,xmin,ymin,xmax,ymax`。
也可使用构建模式 `wg_qmf`，对应查询方法 `qmap_qw`。

Hybrid-QMF 通过 `from hybrid_qmf import optimize` 调用，输入为 N×2 点数组、
Q×4 查询数组及提供 `score_actions(points, queries, actions)` 的 R4 scorer。
默认 H=3、K=4，保留完整 Hybrid-QMF，不包含外部对比实现。

## 测试

```bash
PYTHONPATH=src/python python -m pytest -q -p no:cacheprovider tests
```

测试在临时目录生成小规模输入并编译原生查询核心，不依赖原工作站的实验目录。
门级测试仅在安装 `requirements-circuit.txt` 后执行，否则自动跳过。
生产 QMF 和 Hybrid-QMF 的调度在 CPU 上执行；门级原型仅验证小规模量子电路，
不代表端到端量子加速。

PostgreSQL 扩展为可选组件，需要 PostgreSQL 服务端开发头文件。
先完成上述 C++ 构建，再运行 `make -C src/postgres with_llvm=no`，仅构建共享库，
不要求额外的 LLVM C++ 工具链，也不自动安装到数据库。

## 数据集

数据集、预处理文件和查询工作负载不进入 Git 仓库，只通过外部下载获取。

统一下载链接：**待项目作者提供**。

源码中沿用的 GeoLife、Gowalla、NYC Taxi 和 Skewed 2D 预处理数据未发现统一的
公开下载地址，因此这里不以其他原始数据链接冒充论文实验所用的数据。

## 许可

此整理不为研究源码新增授权。未附明确许可时，公开再分发前需取得项目作者许可；
NumPy、PyTorch、PostgreSQL 等外部依赖仍遵循各自的许可证。
