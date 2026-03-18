# 2026-03-09 Python Interactive CLI Wizard 实施计划（Coding Agent 可直接执行）

## 1. 计划结论

这不是一个“从零设计新创建器”的任务，而是一个**基于现有 `create` 向导补齐体验缺口**的实现任务。

当前仓库已经具备以下基础能力：

- `optionforge create` 已支持交互式向导与非交互 flags 双路径
- 已有 preset、capability、option、依赖校验、互斥校验、自动修复预览
- 已有目录冲突处理逻辑
- 已有整仓库 scaffold 渲染与最小测试覆盖

因此，本计划的目标不是重写 scaffold，而是围绕以下 4 个缺口做增量改造：

1. 根命令无参数时进入主菜单，而不是直接显示 help
2. 创建向导默认值统一为面向新用户的低摩擦体验
3. 高级模块配置默认折叠，只有用户明确选择自定义时才展开
4. 生成前增加最终确认页，生成后输出更清晰的 next steps

## 2. 本次实现范围

### 2.1 必做项

- 根命令主菜单
- `create` 向导默认项目名改为 `alpha_lab`
- `create` 向导保留默认 preset = `custom`
- 增加“是否自定义模块”分支
- 增加最终确认页
- 优化创建完成后的 next steps 输出
- 补齐对应测试

### 2.2 明确不做

本批**不要**实现以下内容：

- 不自动执行 `python -m venv`
- 不自动执行 `pip install`
- 不自动执行 `optionforge validate`
- 不自动执行 `git init`
- 不把 `run` / `backtest` / `doctor` 改造成问答式流程
- 不引入 Ink、Node 子项目、worktree 实验
- 不新增 facade、coordinator 一类中间层

说明：

自动安装、自动校验、自动初始化 git 都会带来明显环境副作用。本项目当前更适合先把交互引导补齐，把“执行动作”继续保持为显式 next steps。

## 3. 实现约束

- 继续复用现有 Python scaffold 规则，不重复定义 preset / capability 语义
- CLI 层直接调用现有 scaffold 能力
- 非交互终端中保留当前 flags 路径，不强制进入向导
- 如果用户显式传了 `--no-interactive` 或 `-y/--default`，必须保持现有语义
- 目录冲突策略仍然使用现有 `abort` / `clear` / `overwrite`

## 4. 执行任务

### 任务 1：根命令增加主菜单入口

#### 目标

让用户在交互终端中直接执行 `optionforge` 时，不再只看到 help，而是进入主菜单。

#### 要求

- 仅在“交互终端 + 无子命令 + 无参数”时进入主菜单
- 非交互终端仍保持当前 help / CLI 行为
- 主菜单至少包含：
  - 创建策略工作区
  - 查看示例
  - 环境诊断
  - 退出
- 默认选项为“创建策略工作区”
- 选择后直接调用已有命令逻辑，不复制实现

#### 建议修改文件

- `src/cli/app.py`
- 如确有必要，可新增一个很小的 CLI 辅助模块到 `src/cli/`，但不要新增抽象层
- `tests/cli/test_app.py`

#### 实现提示

- 抽一个“是否进入主菜单”的判断函数，便于测试
- 主菜单可以用 `click.prompt` + 数字选项实现，不要求复杂 TUI
- “查看示例”直接进入 `examples`
- “环境诊断”直接进入 `doctor`
- “退出”直接返回

#### 验收标准

- 在交互终端执行 `optionforge` 时出现主菜单
- 直接回车默认进入创建路径
- 非交互环境下执行 `optionforge` 不会卡在问答流程
- 现有 `--help`、`--version` 和显式子命令行为不受影响

---

### 任务 2：统一 `create` 向导默认值

#### 目标

把 `create` 向导改成更接近 `create-t3-app` 的首次使用体验。

#### 要求

- 默认项目名统一为 `alpha_lab`
- 默认 preset 继续为 `custom`
- 如果用户已显式传入 `name` 或 `preset`，继续尊重显式输入
- `-y/--default` 走默认创建路径时，也要使用同一套默认值

#### 建议修改文件

- `src/main/scaffold/catalog.py`
- `src/main/scaffold/project.py`
- `tests/main/scaffold/test_project_scaffold.py`
- `tests/main/scaffold/test_prompt.py`
- `tests/cli/test_app.py`

#### 验收标准

- 交互式 `create` 默认项目名显示为 `alpha_lab`
- 默认 preset 仍是 `custom`
- `optionforge create -y` 在未指定名称时使用 `alpha_lab`
- 所有相关测试同步更新

---

### 任务 3：让高级模块配置默认折叠

#### 目标

缩短首次创建路径，避免用户一开始就被 capability / option 问题轰炸。

#### 要求

- 在选择 preset 之后，新增一步：`是否自定义模块`
- 默认值为“否”
- 当用户选择“否”时：
  - 直接采用当前 preset 的默认 capability / option 组合
  - 不进入逐项 capability / option 确认流程
- 当用户选择“是”时：
  - 才进入当前的 capability / option 交互逻辑
  - 继续复用现有自动修复预览能力

#### 建议修改文件

- `src/main/scaffold/prompt.py`
- `tests/main/scaffold/test_prompt.py`

#### 实现提示

- 不要破坏现有 `resolve_capability_options()`、`build_enabled_options_auto_fix_preview()` 等规则函数
- “不自定义”路径可以直接使用 preset 默认推导结果
- “自定义”路径继续复用 `_collect_capability_selection()`

#### 验收标准

- 新用户走默认路径时，不再被逐项 capability / option 提问
- 用户选择自定义后，仍可逐项启停 capability / option
- 自动修复预览只在自定义路径下出现
- 原有非交互 flags 语义不变

---

### 任务 4：生成前增加最终确认页

#### 目标

在真正写文件前，让用户最后确认一次关键配置，减少误生成和误覆盖。

#### 要求

- 在目录冲突策略处理完成后，增加“最终确认”步骤
- 至少展示以下内容：
  - 项目名
  - 目标目录
  - preset
  - 启用 capability 摘要
  - 启用 option 摘要
  - 目录处理策略
  - 生成后建议执行的 next steps 摘要
- 用户确认后才继续生成
- 用户取消时，直接中止，不写入文件

#### 建议修改文件

- `src/main/scaffold/prompt.py`
- `tests/main/scaffold/test_prompt.py`

#### 实现提示

- 现有“配置摘要”可以保留，但要升级为“最终确认页”
- 取消时应返回清晰错误，不要吞掉原因

#### 验收标准

- 生成前一定会出现确认页
- 用户取消时不会生成项目目录
- 目录冲突策略与确认页信息一致

---

### 任务 5：优化创建完成后的 next steps

#### 目标

创建成功后，给用户一条最短可执行路径，而不是只给模糊说明。

#### 要求

- CLI 成功输出至少包含：
  - `cd <project>`
  - `optionforge validate --config config/strategy_config.toml`
  - 一个最小 `optionforge run` 示例
- 生成出的 README / 工作区说明中，也保持一致的 next steps 风格
- 仍然只输出建议，不自动执行

#### 建议修改文件

- `src/cli/commands/create.py`
- `src/main/scaffold/renderer.py`
- 如 README 模板或文案需要同步，则一并更新对应模板文件
- `tests/cli/test_app.py`

#### 验收标准

- `create` 成功后终端输出可直接复制执行的 next steps
- 工作区内文档也能给出一致的 next steps
- 不引入自动执行副作用

---

### 任务 6：补齐测试

#### 目标

为上述交互行为补齐稳定测试，避免后续回归。

#### 至少补的测试点

- 根命令无参数时的主菜单入口行为
- 非交互环境下不进入主菜单
- `create` 默认项目名为 `alpha_lab`
- “是否自定义模块 = 否” 时跳过 capability / option 逐项提问
- “是否自定义模块 = 是” 时进入原有高级模块流程
- 最终确认页出现且可取消
- 创建完成输出包含新的 next steps

#### 建议修改文件

- `tests/cli/test_app.py`
- `tests/main/scaffold/test_prompt.py`
- 仅在确有必要时补充 `tests/main/scaffold/test_project_scaffold.py`

#### 验收标准

- 新增测试覆盖上述核心分支
- 原有相关测试全部通过

## 5. 建议执行顺序

按下面顺序实施，避免返工：

1. 先完成任务 2，统一默认值
2. 再完成任务 3，折叠高级模块配置
3. 再完成任务 4，加入最终确认页
4. 然后完成任务 1，接上根命令主菜单
5. 最后完成任务 5 和任务 6，收尾 next steps 与测试

原因：

- `create` 向导内部行为先稳定，再接根命令主菜单，测试更容易写
- next steps 输出依赖前面流程定型后再统一收口

## 6. 建议验证命令

优先跑最小相关测试，不要一上来全量跑：

```powershell
pytest -c config/pytest.ini tests/main/scaffold/test_prompt.py tests/main/scaffold/test_project_scaffold.py tests/cli/test_app.py
```

如果上述通过，再视情况决定是否补充更大范围测试。

## 7. 建议提交拆分

如果由 coding agent 实际编码，建议按下面粒度提交：

1. `feat: 统一 create 向导默认体验`
2. `feat: 增加 CLI 主菜单与最终确认页`
3. `test: 补充 CLI 向导交互测试`
4. `docs: 同步创建流程说明与 next steps`

如果实际改动量很小，也可以合并为 1 个提交，但要保证 message 能准确描述本轮改动。

## 8. 完成定义（Definition of Done）

当且仅当以下条件同时满足，才算本计划完成：

- `optionforge` 无参数在交互终端进入主菜单
- `create` 默认项目名为 `alpha_lab`
- `create` 默认路径不会展开高级模块提问
- 生成前存在最终确认页
- 创建完成后输出明确的 next steps
- 相关测试通过
- 没有引入自动安装 / 自动校验 / 自动 git 初始化副作用

