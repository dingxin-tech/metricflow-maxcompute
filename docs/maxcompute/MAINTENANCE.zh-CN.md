# MaxCompute fork 维护与发布

本 fork 维护 MaxCompute 的指标查询支持。dbt 模型构建继续由
[dbt-maxcompute](https://github.com/aliyun/dbt-maxcompute) 负责。
仓库默认分支为 `maxcompute`，`main` 保留上游分支；上游基线记录在根目录 `UPSTREAM_BASE`。

## 开发与兼容范围

首次交付固定 Python 3.12，以及快速上手中的运行依赖组合。其他 Python 版本的上游支持范围
不等于本 fork 的交付验收范围。Linux CI 使用 Ubuntu 24.04 / x86_64。

开发环境使用 Hatch，依次运行 `make lint`、`make test PARALLELISM=2`，然后在
`dbt-metricflow/` 中运行 `hatch run maxcompute-env:pytest tests_dbt_metricflow -q`。
PR 必须检查方言 SQL、分区映射、时区与迟到数据边界，以及非 MaxCompute 引擎回归。

核心和 CLI 必须配套发布。当前保留上游发行名及模块名，使用 `+maxcompute.N` 区分版本，
通过 GitHub Releases 分发；不要安装到已有官方 MetricFlow 的环境，也不要发布到官方包名的 PyPI 项目。
后续更改发行名时，需要同时处理模块、CLI 冲突检测和依赖约束。

## CI 与云端验收

`.github/workflows/maxcompute-trial.yml` 在默认分支 push 和 PR 时运行 lint、完整本地回归、
构建和仓库外安装。两个 wheel 和两个源码包封装为同一份试用包，生成 SHA256 校验和。
`manifest.json` 记录源码提交、上游基线、版本和是否存在未提交改动。

云端任务仅允许从 `maxcompute` 分支手动触发，使用 GitHub Environment `maxcompute`：

| 类型 | 名称 | 用途 |
| --- | --- | --- |
| Secret | `MAXCOMPUTE_PROJECT` | 专用测试项目 |
| Secret | `MAXCOMPUTE_ENDPOINT` | 项目 Endpoint |
| Secret | `ALIBABA_CLOUD_ACCESS_KEY_ID` | 测试身份 |
| Secret | `ALIBABA_CLOUD_ACCESS_KEY_SECRET` | 测试身份密钥 |
| Variable | `MAXCOMPUTE_SCHEMA` | Schema，默认 `default` |

测试身份需能建表、写入、读取、EXPLAIN 和删除测试表。由仓库所有者配置受限身份，
本仓库不保存密钥。外部 PR 不获得这些凭据。原始 SQL、云端执行日志不作为公开构建产物上传。
31 项验收通过独立虚拟环境中的实际 `dbt`、`mf` 命令执行；每轮使用独立前缀，并在 finally
中删除本轮十张表、检查前缀残留。异常退出时仍需检查测试项目，一天生命周期作为兜底。

## 发布流程

1. 同时递增核心、CLI 和配套依赖中的 `+maxcompute.N`，更新快速上手与发行说明。
2. 合并 PR，通过默认分支 CI，检查生成的试用包及源码提交。
3. 在 Actions 手动触发 `MaxCompute trial`，选中 `live`、`publish`，填写未使用的
   `maxcompute-trial-YYYYMMDD.N` Tag。云端验收失败会阻止发布；发布复用本轮 CI 验证过的包。
4. 从 Release 下载试用包，校验 SHA256，核对 Tag 和 manifest 指向同一源码提交。

首次发行可由维护者下载 CI 产物，在本地 Linux 容器中注入运行时凭据进行完整验收，
通过后将同一份产物上传到 GitHub prerelease；记录 CI 链接、平台和验收摘要。
使用 `scripts/maxcompute_trial/prepare_pip.py` 从该包生成并发布配套 wheel、`constraints.txt`
和 `requirements.txt`，让用户通过 `pip install -r <Release requirements 地址>` 安装。
现有归档包保持不变，单独提供的 wheel 必须与归档包中的字节一致。
云端 Environment 未配置前，CI 的无凭据验证仍可运行，云端及自动发布需要先完成配置。

## 同步上游

每月检查一次上游 release 与安全修复。在专用分支同步，禁止直接覆盖 `maxcompute`。
更新 `UPSTREAM_BASE`，检查编译计划和 SQL 差异，重新执行完整回归、干净安装与云端验证，
通过后发布新的兼容组合。已有发行包保持不变。

通用优化器修复优先拆为上游 PR；新增引擎和公开配置先通过上游 Issue 讨论。
MaxCompute 分区映射集中在对应模块，避免依赖 monkey patch 或复制整份编译器。
维护者负责核对上游变更、云端成本与残留、依赖升级和发行记录。
