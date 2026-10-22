# MaxCompute 试用版 maxcompute.2

本版本将 MaxCompute 方言、dbt 连接和分区裁剪封装为可安装的成套试用包。
核心版本 `0.214.0.dev0+maxcompute.2`，CLI 版本 `0.16.0.dev0+maxcompute.2`；
使用 Python 3.12，完整运行依赖固定在包内 `constraints.txt`。

支持单表聚合、时间分组、维表与多跳关联、跨事实指标、累计与滚动指标、转化指标、
SCD 有效期关联和百分位数。自动分区裁剪需显式声明业务时间与 ds 的映射、时区及到达时间上下界。
配置规则与结果示例见包内 `QUICKSTART.zh-CN.md`。

下载 `.tar.gz` 和 `.sha256`，先运行 `sha256sum --check *.tar.gz.sha256`
（macOS 使用 `shasum -a 256 --check *.tar.gz.sha256`），再解压并运行：

```bash
unset PYTHONPATH PYTHONHOME
python3.12 install.py --venv "$HOME/.venvs/mf-maxcompute-trial"
source "$HOME/.venvs/mf-maxcompute-trial/bin/activate"
mf --version
```

目录必须尚不存在。第三方运行依赖需要访问 Python 包索引；这是社区 fork 的试用发行，
请使用独立虚拟环境。生产规模性能、Windows 和托管语义服务尚未列入验收范围。
每次发行的实际验收平台和 CI 链接由发行者追加在本说明之后。
