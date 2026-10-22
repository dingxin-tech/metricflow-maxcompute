# MetricFlow 试用版快速上手

本试用版把 MetricFlow 指标定义编译为 MaxCompute SQL，并通过 dbt 连接执行。
dbt 负责构建 SQL 数据模型，MetricFlow 负责依据语义定义规划指标查询。
首次试用可先完成第 1～4 步，查看总量、时间分组和维表关联结果。

本包基于 dbt-labs/metricflow 修改，版本带
`+maxcompute.2` 标识。它尚不是 dbt Labs 官方发布的 MaxCompute 支持版本。

包中包含配套核心和 CLI（命令行工具）的 Python wheel 安装包、安装器、运行依赖约束、入门 dbt 项目和可复跑的
31 项 CLI 云端验收。安装器从 wheel 安装，不需要克隆源码、Hatch 或设置 PYTHONPATH。
第三方 Python 依赖仍需从可访问的包索引下载；这不是完整离线安装包。

试用包固定使用以下主版本，完整第三方依赖版本见 `constraints.txt`：

| 组件 | 版本 |
| --- | --- |
| MetricFlow 核心 | `0.214.0.dev0+maxcompute.2` |
| dbt-metricflow CLI | `0.16.0.dev0+maxcompute.2` |
| dbt-core / dbt-adapters | `1.12.6` / `1.24.5` |
| dbt-maxcompute / PyODPS | `1.11.4` / `0.13.2` |

本文命令使用 macOS/Linux Shell 语法。各次发行的平台验收结果见对应 Release 和仓库验收记录；
Windows 尚未列入验收范围。`sources/` 目录附有两个源码发行包，供开发者重建。

## 1. 安装

从 [GitHub Releases](https://github.com/dingxin-tech/metricflow-maxcompute/releases) 下载成套 `.tar.gz` 和同名 `.sha256`，
在 Linux 执行 `sha256sum --check *.tar.gz.sha256`（macOS 使用 `shasum -a 256 --check *.tar.gz.sha256`）。
准备 Python 3.12，解压试用包。在新的终端进入解压目录，执行以下命令，
避免源码开发环境的 Python 路径覆盖已安装的包：

```bash
unset PYTHONPATH PYTHONHOME
python3.12 install.py --venv "$HOME/.venvs/mf-maxcompute-trial"
source "$HOME/.venvs/mf-maxcompute-trial/bin/activate"
python -m pip check
mf --version
dbt --version
```

安装目录必须尚不存在，安装器不会覆盖旧环境。安装前会校验 SHA256，安装后检查
核心和 CLI 版本配套、依赖一致性，以及模块确实来自该虚拟环境。
若需要内网镜像，使用标准的 `PIP_INDEX_URL` 等 pip 配置；不要把镜像或云凭据写入本包。
本试用版已验证 Python 3.12；其他 Python 版本尚未列入交付验收范围。

## 2. 配置 MaxCompute

在当前终端设置下列环境变量。访问密钥建议通过组织现有的凭据注入方式提供：

```bash
export MAXCOMPUTE_PROJECT='<project_name>'
export MAXCOMPUTE_SCHEMA='default'
export MAXCOMPUTE_ENDPOINT='<endpoint>'
export ALIBABA_CLOUD_ACCESS_KEY_ID='<accessKeyId>'
export ALIBABA_CLOUD_ACCESS_KEY_SECRET='<accessKeySecret>'
export MF_MAXCOMPUTE_TABLE_PREFIX="mf_trial_$(date +%Y%m%d%H%M%S)_$$"
```

将尖括号占位符替换为实际值。Endpoint 按项目所在地域选择 HTTPS 地址，
例如上海地域使用 `https://service.cn-shanghai.maxcompute.aliyun.com/api`。
`example/profiles.yml` 从环境变量读取认证信息，
使用 `maxcompute` adapter 和 UTC 会话时区。示例需要建表、写入和读取权限；自动验收
还需要删除本轮测试表。请选择适合创建测试表的项目或 schema。

## 3. 构建三个示例表

```bash
cd example
export DBT_PROFILES_DIR="$PWD"
export DBT_PROJECT_DIR="$PWD"
dbt debug
dbt run
dbt parse
mf list metrics
```

`dbt run` 创建订单事实表、客户维表和时间脊柱。表名使用上一步的独立前缀，
生命周期为一天。表在生命周期清理前保留，便于重复查询；需要时可按前缀核对后删除
`<前缀>_orders`、`<前缀>_customers`、`<前缀>_time_spine` 三张表。

`dbt parse` 生成 `target/semantic_manifest.json`，`mf` 据此读取模型、实体、维度和
指标定义，生成 MaxCompute SQL，再通过同一 dbt adapter 执行。

## 4. 查询指标

```bash
# 总营收 100，订单数 6，去重客户数 3，平均订单金额 100/6
mf query --metrics revenue,order_count,customer_count,average_order_value

# 按月：2026-01 为 10 / 1，2026-02 为 90 / 5
mf query --metrics revenue,order_count --group-by metric_time__month

# 按客户区域：east 为 30 / 2，west 为 30 / 2，NULL 为 40 / 2
mf query --metrics revenue,order_count --group-by customer__region

# 时间过滤：结果为营收 40、订单数 1
mf query --metrics revenue,order_count --start-time 2026-02-02 --end-time 2026-02-02

# 只查看生成的 SQL；--explain 不执行指标查询
mf query --metrics revenue --start-time 2026-02-02 --end-time 2026-02-02 --explain

# 导出结果
mf query --metrics revenue --group-by metric_time__month --csv monthly.csv
```

维度通过实体路径引用，例如 `customer__region`；`metric_time__month` 表示月粒度。
月份和日期输出可能带 `00:00:00`，取决于 CLI 对 TIMESTAMP 的展示方式。

## 5. 自动分区裁剪

示例订单表按字符串 `ds` 物理分区；语义配置位于 `models/semantic.yml`：

```yaml
config:
  meta:
    maxcompute_partition_mapping:
      time_dimension: ordered_at
      partition_dimension: ds
      time_zone: UTC
      partition_time_zone: Asia/Shanghai
      max_early_arrival_seconds: 32400
      max_lateness_seconds: 86400
      partition_format: yyyy-mm-dd
```

这里声明业务时间按 UTC 解释，`ds` 是上海时区的到达日期，允许提前 9 小时、
迟到 24 小时。因此查询 UTC 的 2 月 2 日，会自动添加：

```sql
ds >= '2026-02-01' AND ds <= '2026-02-04'
```

原有业务时间过滤仍然保留。示例中会扫描五个分区中的四个。
这一配置是覆盖回灌的硬性数据约束，不能用平均或 P99 延迟代替。无法保证迟到上界时，
应删除整个映射配置；只设置 `is_partition: true` 不会自动推导业务时间映射。
支持 `yyyy-mm-dd`、`yyyymmdd` 两种日期格式和 IANA 时区。DST 边界保守扩展，
累计/窗口指标按计划中扩展后的输入时间范围计算分区条件。

`time_zone` 描述已求值业务时间维度的墙上时间和查询入参；它不会改写该维度的时区
表达式或修改 warehouse 会话配置。原始 TIMESTAMP 列的时区应与会话解释一致。
如需其他业务时区，先在时间维度表达式中实现对应的业务时间语义，再声明相符的映射。

## 6. 接入自己的 dbt 项目

保留自己的模型和 `profiles.yml`。在语义 YAML 中用 `model: ref('事实模型名')`
绑定模型，以主键/外键实体连接维表，再声明维度、度量和指标。可从示例中复制
`orders`、`customers` 和 `revenue` 的定义，替换字段名。

执行 `dbt run` 构建模型，再执行 `dbt parse` 更新语义 manifest。在项目根目录运行
`mf`，或通过 `DBT_PROJECT_DIR`、`DBT_PROFILES_DIR` 指向项目和 profile 目录。
累计、偏移等指标还需要在项目中配置覆盖查询日期的时间脊柱。

不要把本示例的测试前缀和一天生命周期直接复制给业务表。

## 7. 重跑完整 CLI 云端验收

回到试用包根目录，使用安装后的 Python 运行：

```bash
python -I verify_cli.py --live --output-root /tmp/mf-maxcompute-evidence
```

脚本使用真实的 `dbt parse`、`dbt run`、`mf list metrics`、`mf query --explain`、
`mf query --csv` 控制台命令，逐项比对 CSV。它会创建带独立 UUID 前缀的十张表，
验证单表、分组、关联、跨事实、自动裁剪、累计/窗口、转化、SCD 和分位数，
并在结束时删除这十张表、检查前缀残留。日志、SQL、CSV、原生执行计划和报告
写入指定的包外目录；凭据只从环境读取。

## 常见问题与支持边界

- 找不到 manifest：在同一项目执行 `dbt parse`，确保存在 `target/semantic_manifest.json`。
  当前读取路径固定为默认 `target`；不要为试用项目改用自定义 target-path。
- VECTOR 元数据解析报错：检查 `python -m pip show pyodps`，确认使用本试用环境的 0.13.2。
- HTTP 连接被重置：使用项目地域对应的 HTTPS Endpoint。
- 前日偏移缺少第一天：上游默认 INNER 时间脊柱关联，没有匹配前日数据的日期会被排除。
- 开启映射仍全扫：使用结构化 `--start-time` / `--end-time`；原始 SQL `--where` 字符串
  不会被解析成自动裁剪范围。用 MaxCompute 原生 EXPLAIN 的 `Data source` 核对实际分区。
- 近似离散分位数、微/纳秒截断明确不支持。图形化 `--display-plans` 需另装可选 Graphviz。
- 当前交付验收是单机 CLI 和小数据云端链路；未包含托管 dbt Semantic Layer、BI 接口、
  多用户服务、生产规模性能或组织权限治理。不能用一次试用验收替代业务数据验收。
- 两个带 `+maxcompute.2` 的包应配套升级；不要直接用官方上游包覆盖其中一个。
  试用期间也不要单独升级 dbt-core；当前验收基于 dbt Core v1，不包含 v2。
