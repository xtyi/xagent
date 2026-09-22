# AGENTS.md

本文件是本仓库的协作约定。任何人（包括 AI agent）在改动本仓库之前，先读完这一页。

## 1. 项目定位

`xagent` 是一个**从零实现、面向学习**的 code agent。

目标不是做一个能替代 Codex / Claude Code 的生产工具，而是把这类工具**为什么这么设计、内部究竟在做什么**一层层拆开，每一层都用读得懂、跑得起来、验得了的代码实现一遍。

阅读对象：已经会写代码、想理解 agent 内部机制的工程师。

因此本项目的取舍与产品项目几乎相反：

| 维度 | 本项目 | 生产项目 |
| --- | --- | --- |
| 依赖 | 尽量零依赖，优先标准库 | 用成熟 SDK |
| 抽象 | 不到需要时不抽象 | 提前抽象 |
| 单文件规模 | 尽量 < 200 行 | 无限制 |
| 覆盖范围 | 一个特性一个特性加 | 一次做全 |
| 变更方式 | 小步、可讲、可回退 | 大步、追求吞吐 |
| 讲解 | 每个特性必须配讲解 | 不需要 |

## 2. 与真实 agent 的对照

我们实现的概念在真实工具里的位置（随时用它校准「我们在学什么」）：

| 本项目模块 | Codex | Claude Code | 概念 |
| --- | --- | --- | --- |
| `backends/` | `core` 的 model client | Anthropic SDK 封装 | 传输层 / wire protocol |
| `messages.py` | `ResponseItem` 一类对话项 | message blocks | 对话数据模型 |
| `agent.py` | turn loop | agent loop | 主循环：模型 → 工具 → 模型 |
| `tools/`（后续） | tool registry + handler | tools | 工具契约、分发、结果回填 |
| `policy/`（后续） | sandbox + approval | permission modes | 权限与安全边界 |
| `ui.py` | TUI | TUI | 流式渲染与人机交互 |

## 3. 工作方式：一次一个 step

**每一次改动 = 一个 step。** 每个 step 必须同时交付四件事，缺一不算完成：

1. **代码**：能运行的最小增量，只加这一个特性。
2. **讲解**：说清「这段代码在做什么」「为什么这样设计」「对应真实工具里的哪一部分」。讲代码时指向具体文件与行，不要泛泛而谈。
3. **验证**：给出可复现的验证方式（`unittest` 通过 + 至少一条真实跑通的命令），并显式说明哪些**没有**验证。
4. **下一步建议**：给 2–4 个候选方向 + 推荐哪个 + 为什么，而不是替用户做决定。

## 4. 分层边界

改动前必须先说清自己动的是哪一层，不要把两层的职责塞进一个函数：

- **transport / wire**：HTTP、SSE、JSON 编解码。只懂字节和字典，不懂「对话」。
- **messages**：对话数据模型及其 wire 表达（`Message.to_wire`）。
- **agent loop**：决定「何时再问一次模型」，不关心某个工具怎么实现。
- **tools**：工具 schema、参数校验、执行、结果序列化。
- **policy**：能不能做（审批 / 沙箱 / 路径限制），**不负责怎么做**。
- **ui**：只负责显示与输入，不参与决策。

依赖方向只允许 `cli → agent → tools/policy → backends`，反向依赖禁止。

## 5. 代码约定

- 语言：**讲解、commit message 用中文；标识符、日志、代码内注释用英文。**
- Python ≥ 3.12，核心代码**只用标准库**。新增第三方依赖必须先在 `plan/` 里写清理由。
- 类型标注齐全，数据结构优先用 `dataclass`。
- 不做「以后可能用到」的抽象；同一模式第三次出现时再抽。
- 新行为都要有对应测试；测试用标准库 `unittest`，不引入 pytest。
- 测试必须离线可跑。真实 API 的探测放 `probes/`，不进 `tests/`。

## 6. 记录约定

- `plan/ROADMAP.md`：整体路线图，唯一权威的「我们要往哪走」。
- `plan/step-NN-*.md`：每个 step 的设计笔记（目标、决策、取舍、验证结果、遗留问题）。**step 做完必须写**，这是本项目最重要的产物之一。
- `probes/`：对环境与 API 的真实探测记录，必须写明日期与结论，区分「实测」与「推测」。
- 未验证的东西一律显式标注「未验证」，不要包装成结论。

## 7. 环境事实

- 工作目录：`/home/xtyi/proj/xagent`
- Python 3.12.3；无 pytest、无 uv，用标准库 + system pip。
- 默认后端：DeepSeek 官方 API（OpenAI 兼容 `/chat/completions`），默认模型 `deepseek-flash`。
  - 凭据优先级：`--api-key` > `XAGENT_API_KEY` > `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` > `~/.codex/config.toml`。
  - 从 `~/.codex/config.toml` 取用凭据时，必须往 stderr 打一行来源提示（不打印密钥本身）。
- 该后端是 **thinking 模型**：多轮时上一层 assistant 的 `reasoning_content` 必须原样回传，否则 400。见 `probes/000-backend-capabilities.md`。
- 真实 API 调用需要网络；离线验证一律走 `backends/mock.py`。

## 8. 明确不做的

- 不追求生产可用、不追求性能、不追求覆盖所有模型厂商。
- 不在 ROADMAP 排到之前引入 MCP / RAG / 多 agent 编排。
- 不提交没有讲解和验证的大块代码。
