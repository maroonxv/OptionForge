# CLI 产品化方案规划

## 1. 背景

本项目是一个面向期权策略研发的 Python 脚手架，目标是帮助用户快速搭建、运行、回测和扩展可复用的期权策略代码，而不是直接提供可交易的现成策略。

从提升开源项目吸引力和 `star` 转化率的角度看，CLI 产品化是一个高 ROI 的方向。原因很简单：

- 陌生用户更容易理解“一个可以直接安装和运行的工具”
- 命令统一之后，README、示例、教程、发布版本都更容易组织
- CLI 可以把项目从“源码仓库”提升为“可安装产品”
- 后续发布 PyPI、接入 `pipx`、自动补全、插件生态都会更顺畅

当前仓库已经具备 CLI 产品化的基础，但入口仍然偏“内部脚本调用”，距离“可安装命令行产品”还有一层包装和结构统一工作。

## 2. 当前现状

目前仓库里已经有多类命令入口，但使用方式仍然偏源码内部路径：

- 运行主入口：`src/main/main.py`
- 回测入口：`src/backtesting/cli.py`
- 脚手架桥接脚本：`scripts/scaffold_strategy.py`
- 脚手架 CLI：`src/main/scaffold/cli.py`

这意味着：

- 用户需要记住多个 Python 文件路径
- 入口风格不统一
- 对外展示时更像“工程源码”而不是“命令行工具”
- 后续做安装、发布、版本管理时不够自然

## 3. 产品化目标

CLI 产品化后的目标状态如下：

- 用户安装后，直接通过一个统一命令使用项目能力
- 所有核心动作都挂在该命令下的子命令体系内
- 文档、示例、错误信息、版本号、发布流程围绕统一 CLI 展开
- 核心业务逻辑尽量复用现有代码，避免重写
- 后续能够自然支持 `pip install`、`pipx install`、PyPI 发布与插件扩展

建议采用的顶层命令名：

- `optionforge`

之所以不继续让用户直接运行 `python src/...`，是因为产品化的关键就是隐藏内部目录结构，把“实现细节”转换成“可记忆的产品命令”。

## 4. 核心设计原则

### 4.1 CLI 层要薄

CLI 负责：

- 参数解析
- 子命令分发
- 友好的帮助信息和错误输出
- 调用现有业务模块

CLI 不负责：

- 重写回测逻辑
- 重写策略运行逻辑
- 再增加一层 facade/coordinator 式的大总管对象

这符合项目当前的工程约束：上层直接调用具体服务/基础设施即可，不额外引入不必要的中间层。

### 4.2 先包装，后迁移

第一阶段不追求一次性重构全部模块路径。

应优先新增一个统一 CLI 包装层，把现有入口聚合起来，让用户先获得更好的使用体验；之后再逐步进行包结构收敛和内部导入路径整理。

结合当前仓库结构，第一阶段默认保留现有 `src/` 作为业务源码主目录，不做整体搬迁。更具体地说：

- `src/backtesting`、`src/main`、`src/strategy`、`src/web` 继续保持现状
- 在现有 `src/` 下新增一个轻量的 `cli/` 聚合层
- 不引入 `src/src/...` 这类重复嵌套目录
- 不在第一阶段强行把全部 `from src...` 导入改写为新包名

### 4.3 安装体验优先

CLI 产品化不只是“有命令”，还包括：

- 能被标准 Python 打包工具识别
- 能通过 `pip install` 或 `pipx install` 安装
- 默认依赖尽量轻量
- 可选能力通过 extras 安装

## 5. 顶层命令树设计

建议将命令统一为：

```text
optionforge
├─ init
├─ run
├─ backtest
├─ validate
├─ doctor
├─ examples
└─ version
```

各子命令职责建议如下。

### 5.1 `optionforge init`

用途：生成策略开发骨架。

建议映射现有能力：

- 复用 `src/main/scaffold/cli.py`
- 继续复用 `src/main/scaffold/generator.py`

建议示例：

```bash
optionforge init my_strategy
optionforge init iron_condor --destination example
optionforge init ema_breakout --force
```

### 5.2 `optionforge run`

用途：运行策略主程序。

建议映射现有能力：

- 复用 `src/main/main.py`

建议示例：

```bash
optionforge run --mode standalone --config config/strategy_config.toml --paper
optionforge run --mode daemon --config config/strategy_config.toml
```

### 5.3 `optionforge backtest`

用途：运行回测。

建议映射现有能力：

- 复用 `src/backtesting/cli.py`

建议示例：

```bash
optionforge backtest --config config/strategy_config.toml --start 2025-01-01 --end 2025-03-01 --no-chart
```

### 5.4 `optionforge validate`

用途：校验配置、依赖和最基本的策略契约绑定。

建议第一版至少覆盖：

- `strategy_config.toml` 是否存在、是否能被加载
- `strategy_contract.toml` 中的类路径是否可导入
- 必填配置项是否齐全
- CLI 传入的日期、路径、运行模式是否合法

这是脚手架项目非常关键的命令，因为很多新用户不是卡在“功能不存在”，而是卡在“配置写错却不知道错在哪里”。

### 5.5 `optionforge doctor`

用途：环境诊断。

建议第一版输出：

- Python 版本
- 当前项目版本
- 关键依赖是否安装
- 可选依赖是否缺失
- 环境变量文件是否存在
- 数据库连接配置是否完整
- 如果启用 broker/网关，对应依赖是否可用

这是提升新用户留存和降低 issue 噪音的重要命令。

### 5.6 `optionforge examples`

用途：列出内置示例、复制示例或运行示例。

仓库当前已经有如下示例目录：

- `example/ema_cross_example`
- `example/iv_rank_example`
- `example/delta_neutral_example`

CLI 化后，示例能力会更可见，也更容易转化为 README 的快速体验路径。

## 6. Python 技术方案选择

### 6.1 命令框架建议：`Typer`

当前仓库已经在使用 `argparse`，如果只追求最低改造成本，可以继续沿用；但从“CLI 产品”角度，推荐新增统一 CLI 层时使用 `Typer`。

推荐理由：

- 更适合组织多级子命令
- 帮助信息更清晰
- 类型提示更自然
- 自动补全支持更友好
- 与 Python typing 配合更顺畅

建议策略：

- 统一对外 CLI 层使用 `Typer`
- 内部现有模块暂时保持不动
- 通过包装函数调用既有逻辑，减少一次性重构风险

### 6.2 CLI 包结构建议

基于当前项目结构，建议在现有 `src/` 包下新增 `cli/` 子包作为统一对外入口，而不是在第一阶段重做整个源码目录布局，也不是继续依赖 `scripts/` 下的桥接脚本。

建议结构如下：

```text
OptionForge/
├─ pyproject.toml
├─ README.md
├─ requirements.txt
├─ config/
├─ deploy/
├─ docs/
├─ example/
├─ scripts/
│  └─ scaffold_strategy.py
├─ src/
│  ├─ __init__.py
│  ├─ cli/
│  │  ├─ __init__.py
│  │  ├─ app.py
│  │  ├─ common.py
│  │  └─ commands/
│  │     ├─ __init__.py
│  │     ├─ init.py
│  │     ├─ run.py
│  │     ├─ backtest.py
│  │     ├─ validate.py
│  │     ├─ doctor.py
│  │     └─ examples.py
│  ├─ backtesting/
│  ├─ main/
│  ├─ strategy/
│  └─ web/
└─ tests/
   ├─ cli/
   ├─ backtesting/
   ├─ main/
   ├─ strategy/
   └─ web/
```

职责划分：

- `src/cli/app.py`：注册顶层命令和子命令
- `src/cli/common.py`：放置共享输出、异常转换、路径解析等轻量公共逻辑
- `commands/*.py`：每个文件负责一个子命令
- 业务实现继续调用现有模块，不在 CLI 层堆积复杂逻辑

这种结构的关键点在于：

- 现有 `src/` 继续作为项目主代码目录
- 新增的只是 `src/cli/`，用于统一对外命令体验
- 第一阶段不做全量源码搬迁，因此改动面和风险都更可控

### 6.3 与现有代码的衔接方式

建议第一阶段通过在现有 `src/` 包下新增 CLI 包装层来完成过渡：

- `init` -> 调用 `src/main/scaffold/cli.py` 或更底层的 `src/main/scaffold/generator.py`
- `run` -> 调用 `src/main/main.py`
- `backtest` -> 调用 `src/backtesting/cli.py`
- `validate` -> 复用现有配置加载和契约装配逻辑
- `doctor` -> 新增环境检查逻辑，但只依赖现有配置与依赖信息
- `examples` -> 直接面向 `example/` 目录提供列出、复制、运行入口

这样做的好处：

- 立刻获得统一命令入口
- 内部逻辑复用最大化
- 风险更低
- 可以逐步把旧入口废弃，而不是一次性大迁移
- 不会破坏当前 `src` 下已经存在的大量业务代码和导入关系

## 7. 打包与安装方案

### 7.1 引入 `pyproject.toml`

CLI 产品化必须补齐标准 Python 打包元数据。

建议采用基于 `pyproject.toml` 的现代打包方式，避免继续依赖零散脚本式运行模式。

建议至少包含：

- 项目名
- 版本号
- Python 版本要求
- 基础依赖
- 可选依赖 extras
- CLI 暴露命令

建议命令暴露方式：

```toml
[project.scripts]
optionforge = "src.cli.app:app"
```

### 7.2 安装方式建议

README 和后续对外宣传建议同时支持两种安装：

- `pip install optionforge`
- `pipx install optionforge`

其中更推荐 `pipx` 用于 CLI 工具安装，因为：

- 对用户来说更接近“安装一个应用”
- 依赖隔离更清晰
- PATH 暴露更自然
- 不污染已有项目虚拟环境

## 8. 依赖拆分方案

当前项目依赖比较重，若直接把全部依赖作为默认安装内容，会明显增加首次安装成本，也会放大平台兼容问题。

建议拆分为以下层次。

### 8.1 基础依赖 `core`

用于最轻量的 CLI 体验：

- CLI 框架
- 配置加载
- 示例管理
- 基础校验
- 文本输出

### 8.2 回测依赖 `backtest`

用于运行回测相关能力：

- 回测引擎所需依赖
- 数据处理类依赖

### 8.3 Web 依赖 `web`

用于监控页面和接口：

- Flask
- SocketIO 等 Web 能力

### 8.4 交易/网关依赖 `broker`

用于实盘相关、可选网关能力：

- `vnpy_ctp`
- `vnpy_sopt`
- 其他 broker/gateway 相关依赖

### 8.5 开发依赖 `dev`

用于仓库开发和发布：

- `pytest`
- `build`
- 格式化与静态检查工具
- 发布工具

拆分后的好处：

- 新用户安装成本更低
- CLI 更容易被试用
- 平台兼容问题隔离得更清楚
- 可以更自然地向 PyPI 发布

## 9. `validate` 与 `doctor` 的价值

从产品视角看，脚手架最重要的不是“能跑”，而是“出错时能快速知道哪里错了”。

因此 `validate` 和 `doctor` 两个命令应被视为 CLI 产品化的一等能力，而不是附加功能。

### 9.1 `validate` 解决的问题

- 配置文件路径写错
- TOML 内容格式不合法
- 策略类路径无法导入
- 参数缺失
- 时间区间非法
- 示例复制后没有正确绑定契约

### 9.2 `doctor` 解决的问题

- Python 版本不符合要求
- 关键包未安装
- 可选依赖缺失
- `.env` 或部署配置缺失
- 本地数据库/网关环境不完整

这两个命令会显著提升首次体验质量，也能减少未来 issue 中大量重复性的环境排查问题。

## 10. 示例与体验路径优化

CLI 产品化之后，README 中最理想的体验路径应从“部署完整栈”转向“先感受到价值”。

建议的第一屏体验顺序：

1. 安装 CLI
2. 列出示例
3. 初始化一个新策略骨架
4. 运行一次最小回测或校验

示意流程：

```bash
pipx install optionforge
optionforge examples
optionforge init my_strategy
optionforge validate --config config/strategy_config.toml
optionforge backtest --config config/strategy_config.toml --start 2025-01-01 --end 2025-03-01 --no-chart
```

这条路径比直接要求用户先启动数据库、监控页面和完整容器栈，更适合作为开源项目首页的引导。

## 11. 插件化方向

CLI 产品化之后，下一步非常值得考虑的是插件化。

目标是允许第三方通过单独的 Python 包扩展：

- 新策略模板
- 新示例
- 新数据源
- 新校验器
- 新报告器

推荐方向是使用 Python entry points 实现自动发现。

这样未来可以形成：

- 主仓库提供脚手架和标准契约
- 外部仓库发布策略扩展包
- CLI 自动识别并加载扩展

这会让项目从“一个仓库”升级为“一个生态入口”。

## 12. 分阶段落地方案

### 第一阶段：最小可用产品化

目标：尽快形成统一命令。

建议动作：

- 新增 `pyproject.toml`
- 新增统一 CLI 包
- 暴露 `optionforge` 命令
- 接入 `init`、`run`、`backtest` 三个子命令
- 为 CLI 增加 `--help` 和 `--version`

这一阶段的重点不是大重构，而是把分散入口统一起来。

### 第二阶段：补足产品体验

建议动作：

- 增加 `validate`
- 增加 `doctor`
- 增加 `examples`
- 优化错误信息和退出码
- 更新 README 的安装与快速开始方式

### 第三阶段：发布与分发

建议动作：

- 本地构建 wheel/sdist
- GitHub Actions 自动构建
- 发布到 TestPyPI/PyPI
- 增加 `pipx` 安装说明
- 为 Release 编写变更说明模板

### 第四阶段：内部结构收敛

建议动作：

- 视实际收益再决定是否需要进一步收敛模块布局
- 逐步清理旧的桥接脚本和重复入口
- 统一模块路径、版本管理方式与 CLI 入口规范

这一阶段是可选优化，而不是第一阶段的前置条件。当前更优先的目标仍然是保留现有 `src` 业务结构、尽快打通统一 CLI 产品入口。

### 第五阶段：插件生态

建议动作：

- 定义插件协议
- 暴露 entry points
- 补充插件开发文档
- 提供一个官方示例插件仓库

## 13. 对开源增长的直接价值

CLI 产品化对项目增长的帮助，主要体现在以下几点：

- README 第一屏更容易展示“可立即使用”的能力
- 用户更容易完成首次成功体验
- 更容易被博客、教程、视频、社区帖子引用
- `pipx install` 这种一行命令更适合传播
- 发布版本之后，项目会更像一个真正的开源工具，而不是仅供参考的源码模板

对这个项目来说，CLI 产品化是“把工程能力产品化输出”的关键一步。

## 14. 当前推荐结论

基于当前仓库情况，推荐采用以下决策：

1. 使用 `Typer` 构建统一 CLI 外壳
2. 新增 `pyproject.toml`，暴露 `optionforge` 命令
3. 第一阶段只接入 `init`、`run`、`backtest`
4. 第二阶段补上 `validate`、`doctor`、`examples`
5. 同步拆分依赖为 `core/backtest/web/broker/dev`
6. 后续逐步推进插件化与 PyPI 发布

这是当前最稳妥、收益最高、又不会过度打断现有工程结构的 CLI 产品化路径。

## 15. 下一步实施建议

建议按下面顺序继续推进：

1. 编写 `pyproject.toml`
2. 搭建统一 CLI 包目录
3. 接入 `init`、`run`、`backtest`
4. 跑通本地安装与命令调用
5. 更新 README 的安装与快速开始说明
6. 继续实现 `validate` 与 `doctor`

如果进入实际开发阶段，应优先遵循“最小改动先打通命令”的原则，而不是一开始就做全量目录重构。
