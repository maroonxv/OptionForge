# 本项目 CLI 使用指南

本文面向在本地开发环境中使用本项目命令行入口的用户，介绍如何启动 CLI、各子命令的用途，以及一套推荐的日常使用流程。

## 1. CLI 是什么

本项目提供了统一命令行入口 `option-scaffold`，用于完成以下常见工作：

- 初始化新的策略骨架
- 启动策略主程序
- 执行组合策略回测
- 校验配置与契约绑定
- 诊断本地依赖与环境
- 浏览仓库内置示例

CLI 入口对应的模块为：

- 可执行命令：`option-scaffold`
- Python 模块：`python -m src.cli.app`

如果你处于本地开发阶段，推荐优先使用模块方式启动；如果你希望像正式命令一样直接执行，再安装可编辑脚本。

## 2. 环境要求

在使用 CLI 前，建议先准备以下环境：

- Python `3.11+`
- 已创建虚拟环境
- 已安装项目依赖

在仓库根目录执行以下命令：

```powershell
# 进入仓库根目录
cd D:\work_projects\option-strategy-scaffold

# 激活虚拟环境（PowerShell）
.\.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 安装为可编辑模式，生成 option-scaffold 命令
pip install -e .
```

如果你暂时不想安装可执行脚本，也可以直接使用：

```powershell
python -m src.cli.app --help
```

## 3. 两种启动方式

### 3.1 开发态启动（推荐）

这种方式最适合本地开发、调试和断点跟踪：

```powershell
python -m src.cli.app --help
```

优点：

- 不依赖系统 PATH
- 最适合在 IDE 中调试
- 修改源码后可直接再次运行

### 3.2 命令态启动

在执行过 `pip install -e .` 后，可以直接使用项目脚本名：

```powershell
option-scaffold --help
```

如果当前 Shell 没有自动识别该命令，也可以直接调用虚拟环境中的可执行文件：

```powershell
.\.venv\Scripts\option-scaffold.exe --help
```

## 4. 查看 CLI 总帮助

```powershell
option-scaffold --help
```

或：

```powershell
python -m src.cli.app --help
```

当前 CLI 提供以下子命令：

- `init`：生成策略开发骨架
- `run`：运行策略主程序
- `backtest`：执行组合策略回测
- `validate`：校验配置、契约绑定与可选回测参数
- `doctor`：诊断本地环境与依赖
- `examples`：列出并查看内置示例

查看某个子命令的帮助时，只需要追加 `--help`：

```powershell
option-scaffold run --help
option-scaffold validate --help
option-scaffold doctor --help
```

## 5. 推荐的本地使用流程

建议你在本地开发时遵循下面这条顺序：

```powershell
# 1) 看看 CLI 能否正常启动
python -m src.cli.app --help

# 2) 先诊断环境
python -m src.cli.app doctor

# 3) 校验策略配置
python -m src.cli.app validate --config config/strategy_config.toml

# 4) 查看内置示例
python -m src.cli.app examples

# 5) 按需运行策略或回测
python -m src.cli.app run --config config/strategy_config.toml
python -m src.cli.app backtest --config config/strategy_config.toml --start 2025-01-01 --end 2025-03-01 --no-chart
```

如果你已经完成 `pip install -e .`，可以把上面的 `python -m src.cli.app` 全部替换为 `option-scaffold`。

## 6. 各子命令说明

### 6.1 `doctor`：先做环境体检

`doctor` 用于检查本地 CLI 环境、配置文件、依赖安装情况以及部分运行前置条件。

常用命令：

```powershell
option-scaffold doctor
```

严格模式：

```powershell
option-scaffold doctor --strict
```

额外检测数据库连通性：

```powershell
option-scaffold doctor --check-db
```

适用场景：

- 第一次拉起项目时
- 刚切换 Python 环境时
- 命令运行失败但不确定是配置问题还是依赖问题时

### 6.2 `validate`：校验配置是否可运行

`validate` 会检查策略配置、交易标的配置、契约绑定、订阅配置，以及可选的回测参数覆盖值。

最常用的写法：

```powershell
option-scaffold validate --config config/strategy_config.toml
```

带覆盖配置：

```powershell
option-scaffold validate --config config/strategy_config.toml --override-config config/timeframe/5m.toml
```

校验回测参数：

```powershell
option-scaffold validate --config config/strategy_config.toml --start 2025-01-01 --end 2025-03-01 --capital 1000000 --rate 0.0002 --slippage 0.2 --size 10 --pricetick 0.001 --no-chart
```

它适合放在真正运行 `run` 或 `backtest` 之前，作为一层快速前置检查。

### 6.3 `run`：运行策略主程序

`run` 用于启动策略主程序，支持运行模式、日志级别、日志目录、无界面模式、模拟交易模式等参数。

最常用写法：

```powershell
option-scaffold run --config config/strategy_config.toml
```

守护进程模式：

```powershell
option-scaffold run --mode daemon --config config/strategy_config.toml
```

无界面 + 模拟交易：

```powershell
option-scaffold run --config config/strategy_config.toml --no-ui --paper
```

指定日志级别与目录：

```powershell
option-scaffold run --config config/strategy_config.toml --log-level DEBUG --log-dir data/logs
```

常用参数说明：

- `--mode`：`standalone` 或 `daemon`
- `--config`：策略配置文件，默认 `config/strategy_config.toml`
- `--override-config`：附加覆盖配置
- `--log-level`：`DEBUG` / `INFO` / `WARNING` / `ERROR`
- `--log-dir`：日志目录，默认 `data/logs`
- `--no-ui`：无界面运行
- `--paper`：启用模拟交易模式

### 6.4 `backtest`：执行组合策略回测

`backtest` 用于运行组合策略回测，并支持日期区间、初始资金、滑点、手续费率等回测参数。

示例：

```powershell
option-scaffold backtest --config config/strategy_config.toml --start 2025-01-01 --end 2025-03-01 --capital 1000000 --rate 0.0002 --slippage 0.2 --size 10 --pricetick 0.001 --no-chart
```

常见用途：

- 校验策略在历史区间内的行为
- 对比不同参数组合效果
- 在正式接入运行模式前先做策略验证

### 6.5 `init`：生成新的策略骨架

`init` 用于生成新的策略开发目录。

默认写入到仓库根目录下的 `example/`：

```powershell
option-scaffold init ema_breakout
```

指定输出目录：

```powershell
option-scaffold init ema_breakout --destination temp
```

允许覆盖已有文件：

```powershell
option-scaffold init ema_breakout --destination temp --force
```

适合在你要新建一套策略试验骨架时使用。

### 6.6 `examples`：浏览仓库内置示例

列出所有内置示例：

```powershell
option-scaffold examples
```

查看某个示例详情：

```powershell
option-scaffold examples some_example_name
```

该命令会读取 `example/` 目录下各示例子目录的 `README.md` 内容并展示。

## 7. 本地开发时如何调试 CLI

如果你要调试 CLI 本身，而不是只使用它，推荐以下方式：

### 7.1 直接跑模块

```powershell
python -m src.cli.app run --help
```

这样最适合在 IDE 中设置断点，例如断在：

- `src/cli/app.py`
- `src/cli/commands/run.py`
- `src/cli/commands/validate.py`
- `src/cli/commands/doctor.py`

### 7.2 先看帮助，再缩小范围

通常建议按下面顺序定位问题：

1. `python -m src.cli.app --help`
2. `python -m src.cli.app doctor`
3. `python -m src.cli.app validate --config config/strategy_config.toml`
4. 再执行 `run` 或 `backtest`

这样可以先排除 CLI 入口、依赖安装、配置解析等基础问题。

## 8. 常见问题

### 8.1 `option-scaffold` 命令找不到

通常是因为还没有执行：

```powershell
pip install -e .
```

或者当前 Shell 没有使用正确的虚拟环境。

你可以先退回模块方式：

```powershell
python -m src.cli.app --help
```

### 8.2 运行时报依赖缺失

先执行：

```powershell
pip install -r requirements.txt
pip install -e .
```

然后运行：

```powershell
option-scaffold doctor
```

### 8.3 `validate` 校验失败

优先检查以下内容：

- `config/strategy_config.toml` 是否存在且可解析
- `config/general/trading_target.toml` 是否存在且 `targets` 非空
- `--start` / `--end` 日期格式是否为 `YYYY-MM-DD`
- 回测参数是否为正数或非负数
- 契约绑定指向的 Python 导入路径是否正确

### 8.4 `examples` 没有列出任何内容

说明仓库下的 `example/` 目录中没有可识别的示例子目录，或者对应示例没有按预期组织。

## 9. 推荐命令速查

```powershell
# 查看总帮助
python -m src.cli.app --help

# 环境诊断
python -m src.cli.app doctor

# 严格诊断
python -m src.cli.app doctor --strict

# 配置校验
python -m src.cli.app validate --config config/strategy_config.toml

# 启动策略
python -m src.cli.app run --config config/strategy_config.toml

# 守护模式运行
python -m src.cli.app run --mode daemon --config config/strategy_config.toml

# 运行回测
python -m src.cli.app backtest --config config/strategy_config.toml --start 2025-01-01 --end 2025-03-01 --no-chart

# 浏览示例
python -m src.cli.app examples

# 创建策略骨架
python -m src.cli.app init my_strategy
```

## 10. 建议

如果你是第一次接触本项目，推荐按下面顺序入手：

1. 先跑 `doctor`
2. 再跑 `validate`
3. 看 `examples`
4. 用 `init` 生成自己的策略骨架
5. 最后再跑 `run` 或 `backtest`

这样能更快确认“环境是否正常、配置是否可用、项目的推荐组织方式是什么”。
