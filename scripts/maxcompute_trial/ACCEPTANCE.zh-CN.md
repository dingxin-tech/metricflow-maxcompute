# 试用版交付验收记录

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
