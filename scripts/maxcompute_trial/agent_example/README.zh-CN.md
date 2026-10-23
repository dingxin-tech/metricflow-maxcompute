# 从业务需求生成 MaxCompute 语义配置

操作步骤、安装方式、完整 YAML 和查询结果请参见
[中文快速上手第 8 节](https://github.com/dingxin-tech/metricflow-maxcompute/blob/maxcompute/scripts/maxcompute_trial/QUICKSTART.zh-CN.md#8-使用官方-agent-skill-生成语义配置)。

本目录是独立的 dbt 项目。使用第 1 节安装的 Python 3.12 试用环境和第 2 节的凭据环境变量，
为本次实验重新设置 `MF_MAXCOMPUTE_TABLE_PREFIX`，并将 `DBT_PROJECT_DIR`、`DBT_PROFILES_DIR`
指向本目录。

| 文件 | 作用 |
| --- | --- |
| `dbt_project.yml` | 表物化、一天生命周期和随机表名前缀 |
| `profiles.yml` | 从环境变量读取 MaxCompute 连接参数，使用 UTC |
| `models/orders.sql` | 8 笔订单，含取消、退款、NULL 金额和未知客户 |
| `models/customers.sql` | 3 位客户及地区 |
| `models/time_spine.sql` | 通过 adapter 宏生成四天日期表 |
| `AGENT_PROMPT.zh-CN.md` | 可直接提交给 Agent 的业务需求和验收要求 |
| `reference/semantic.yml` | 已通过云端验证的新版 YAML 参考答案 |

初始 `models/` 中没有语义 YAML，由 Agent 依据业务需求生成。
`reference/` 不在 `model-paths` 中，dbt 不会解析该目录。
如需直接重现参考结果，在本目录执行：

```bash
cp reference/semantic.yml models/semantic.yml
dbt parse
dbt run
dbt test
mf validate-configs
mf query --metrics paid_revenue,paid_orders,paid_aov
mf query --metrics paid_revenue,paid_orders,paid_aov --group-by metric_time__day
mf query --metrics paid_revenue,paid_orders,paid_aov --group-by metric_time__month
mf query --metrics paid_revenue,paid_orders,paid_aov --group-by customer__region
mf query --metrics paid_revenue,paid_orders,paid_aov --group-by metric_time__month,customer__region
mf query --metrics paid_revenue,paid_orders,paid_aov --group-by metric_time__day --start-time 2026-02-02 --end-time 2026-02-02
```

复制参考答案会创建或覆盖 `models/semantic.yml`；保留自己生成的配置后再做对比。
本例只创建三张带前缀的实验表，设置一天生命周期。清理时仅删除本轮前缀对应的 orders、customers、time_spine 三表。

验收日期：2026-10-23。官方 Skill 提交：`b8facde20b7a92c40ce3e6b86b71c4b92aa44040`。
当前对话 Agent 直接读取原版 Skill 完成建模；7 项模型测试、含云端的语义验证、6 组指标查询均通过。
每组查询与事先定义的预期及独立云端 SQL 对账。详细摘要见
[验收记录](https://github.com/dingxin-tech/metricflow-maxcompute/blob/maxcompute/scripts/maxcompute_trial/ACCEPTANCE.zh-CN.md)。
