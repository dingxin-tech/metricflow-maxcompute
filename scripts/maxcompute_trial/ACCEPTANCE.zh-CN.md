# 试用版交付验收记录

## 官方 Agent Skill 建模验收（2026-10-23）

使用官方 `building-dbt-semantic-layer`，提交 `b8facde20b7a92c40ce3e6b86b71c4b92aa44040`。
当前对话 Agent 直接读取原版 Skill，在全新 dbt 项目与独立 Python 3.12.7 环境中，
从明确的实验业务需求生成新版语义 YAML。核心与 CLI 使用 `+maxcompute.2`，
dbt-core 1.12.6、dbt-maxcompute 1.11.4、PyODPS 0.13.2；82 项依赖兼容检查通过。

- `dbt parse` 首次通过，MetricFlow 正确读取两个语义模型与三个指标。
- `dbt run` 构建客户、订单、日期三表，行数分别为 3、8、4。日期表首次连接重置，原样重试后通过。
- `dbt test` 7/7 通过；`mf validate-configs` 包含云端验证，错误、未来错误、警告均为 0。
- 6 组真实 `mf query --explain` 与 `mf query --csv`：总量、按日、按月、地区关联、月份与地区组合、日期范围。
  每组同时检查营收、订单数、客单价，与固定预期和独立云端 SQL 对账，全部通过。
- 总营收 500、订单 6、客单价 500/6；NULL 金额订单计数、取消和退款排除、未匹配客户的 60 元营收保留。
- 官方日期参考中的 `DATEADD(year, -5, CURRENT_DATE())` 云端探针报 `ODPS-0130071`；
  MaxCompute 参数顺序及 adapter 的日期表宏可用。
- 官方 Skill、adapter 和 MetricFlow 均未修改；三张实验表已删除，前缀残留为 0。

完整可复现输入见 [agent_example/](agent_example/)，操作步骤与完整生成结果见
[快速上手第 8 节](QUICKSTART.zh-CN.md#8-使用官方-agent-skill-生成语义配置)。
原始运行日志和实例 ID 由维护者本地保留，不随公开示例发布。
本轮仅验收上述基本场景，未重测高级指标、自动分区裁剪或不同客户端的 Skill 自动触发率。

## 初始试用包验收（2026-10-22）

验收日期：2026-10-22。环境：macOS arm64 / Python 3.12.7。

- 两套仓库外全新虚拟环境完成安装，`pip check` 通过。
- 核心和 CLI 从虚拟环境的 site-packages 导入，非 editable 安装，PYTHONPATH 为空。
- MetricFlow 核心 0.214.0.dev0+maxcompute.1；CLI 0.16.0.dev0+maxcompute.1。
- dbt-core 1.12.6、dbt-adapters 1.24.5、dbt-maxcompute 1.11.4、PyODPS 0.13.2。
- 安装器使用的完整第三方运行依赖版本见 constraints.txt。
- 实际 dbt parse、dbt run 成功构建十个模型；mf list metrics 成功。
- 实际 mf query --explain 和 mf query --csv 的 31 项查询全部通过，CSV 与预期逐项比对。
- 六份 MaxCompute 原生执行计划采集成功；自动裁剪、窗口扩展的分区集合断言通过。
- 快速上手项目的 dbt debug/run/parse、四类 mf query 查询均通过。
- 快速上手的原生计划确认扫描五个现有 ds 分区中的四个。
- 测试结束后十表/三表均删除，按独立前缀检查无残留。
- 两个源码发行包在仓库外单独重建 wheel，SHA256 均与交付 wheel 一致。
- 本地回归 1,970 项通过（60 项跳过），CLI 测试 45 项通过（2 项跳过）。
- 本次未进行 Linux/Windows 独立平台验收、生产规模性能验收或托管语义服务验收。

原始云端 SQL、CSV、日志和执行计划保留在维护者本地验收目录，交付包仅包含示例数据和摘要，
不包含访问密钥、运行时 profile 凭据或签名 LogView 地址。此包是 MaxCompute 试用构建，
不代表 dbt Labs 官方发布。
