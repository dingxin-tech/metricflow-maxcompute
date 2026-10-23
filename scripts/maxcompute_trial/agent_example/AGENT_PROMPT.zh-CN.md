# 给 Agent 的业务需求

使用官方 building-dbt-semantic-layer Skill，为当前 MaxCompute dbt 项目生成语义配置。
先读取 models/ 下的 SQL、dbt_project.yml 和 profiles.yml，再根据以下需求生成
models/semantic.yml。不要读取 reference/ 中的参考答案，也不要修改 SQL 中的实验数据。

分析目标：查询已支付订单的营收、订单数、客单价，支持按日、按月和客户地区分组，
以及月份和地区组合分组。

业务口径：

- orders 一行一笔订单，order_id 唯一且非空；customers 一行一个客户，customer_id 唯一且非空。
- 订单通过 customer_id 对应客户；客户表只保存当前地区，不包含历史版本。
- 仅 status = 'paid' 纳入指标，cancelled 和 refunded 均排除。
- NULL 金额按零计入营收；对应已支付订单仍计入订单数。
- 客单价 = 已支付营收 / 已支付订单数，不用忽略 NULL 的 AVG(amount)。
- 以 ordered_at 为业务时间，源数据和会话时区均为 UTC。
- 关联不到客户的订单保留，归入地区为 NULL 的分组。
- 本实验没有 ds 的到达时间契约，不配置自动分区裁剪。

实现要求：

- 指标命名为 paid_revenue、paid_orders、paid_aov；客户实体名为 customer，地区维度为 region。
- 使用当前已安装的试用版 dbt 和 mf，不升级或重新安装依赖。空项目使用 Core 1.12 支持的新版 YAML。
- 将主键唯一性和非空检查写入 YAML；对日期表声明日粒度时间脊柱。
- 状态过滤只引用已声明的维度；普通维表不需要添加订单度量。
- 先解释实体、维度、时间和指标的对应关系，再展示配置修改。
- 使用已有凭据环境变量执行 dbt parse、dbt run、dbt test、mf validate-configs，
  再执行真实 mf query。缺少凭据或查询权限时报告具体阻塞，不把仅编译通过当成云端验证通过。
- 不将访问密钥写入文件或回复。实验表由环境变量 MF_MAXCOMPUTE_TABLE_PREFIX 区分。
- 对照预期核验：总营收 500、订单 6；1 月 120 / 1 单、2 月 380 / 5 单；
  east 320 / 2 单、west 80 / 2 单、south 40 / 1 单、NULL 地区 60 / 1 单。
