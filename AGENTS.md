# AGENTS.md

## 项目定位

`xagent` 是一个**从零实现、面向学习**的 code agent。

目标不是做一个能替代 Codex / Claude Code 的生产工具，而是把这类工具**为什么这么设计、内部究竟在做什么**一层层拆开，每一层都用读得懂、跑得起来、验得了的代码实现一遍。

因此本项目的取舍与产品项目几乎相反：

| 维度 | 本项目 | 生产项目 |
| --- | --- | --- |
| 依赖 | 尽量零依赖，优先标准库 | 用成熟 SDK |
| 抽象 | 不到需要时不抽象 | 提前抽象 |
| 单文件规模 | 尽量 < 200 行 | 无限制 |
| 覆盖范围 | 一个特性一个特性加 | 一次做全 |
| 变更方式 | 小步、可讲、可回退 | 大步、追求吞吐 |
| 讲解 | 每个特性必须配讲解 | 不需要 |

## 与真实 agent 的对照

我们实现的概念在真实工具里的位置（随时用它校准「我们在学什么」）：

| 本项目模块 | Codex | Claude Code | 概念 |
| --- | --- | --- | --- |
| `backends/` | `core` 的 model client | Anthropic SDK 封装 | 传输层 / wire protocol |
| `messages.py` | `ResponseItem` 一类对话项 | message blocks | 对话数据模型 |
| `agent.py` | turn loop | agent loop | 主循环：模型 → 工具 → 模型 |
| `tools/`（后续） | tool registry + handler | tools | 工具契约、分发、结果回填 |
| `policy/`（后续） | sandbox + approval | permission modes | 权限与安全边界 |
| `ui.py` | TUI | TUI | 流式渲染与人机交互 |

## 工作方式：一次一个 step

**每一次改动 = 一个 step。** 每个 step 必须同时交付四件事，缺一不算完成：

1. **代码**：能运行的最小增量，只加这一个特性。
2. **讲解**：说清「这段代码在做什么」「为什么这样设计」「对应真实工具里的哪一部分」。讲代码时指向具体文件与行，不要泛泛而谈。
3. **验证**：给出可复现的验证方式（`pytest` 通过 + 至少一条真实跑通的命令），并显式说明哪些**没有**验证。
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
- Python ≥ 3.12。**运行时代码尽量只用标准库**；开发/测试工具（pytest 这类常见库）允许直接用。
  新增**运行时**第三方依赖必须先在 `plan/` 里写清理由。
- 类型标注齐全，数据结构优先用 `dataclass`。
- 不做「以后可能用到」的抽象；同一模式第三次出现时再抽。
- 新行为都要有对应测试；测试用 `pytest`，写惯用 pytest 风格（模块级函数 + 裸 `assert` +
  `parametrize` / `monkeypatch` / `tmp_path`），不要写 `unittest.TestCase`。
- 测试必须离线可跑。真实 API 的探测放 `probes/`，不进 `tests/`。
- **绝不提交密钥**：含密文件一律进 `.gitignore`，仓库里只放 `.example` 模板。

## 6. 记录约定

- `plan/ROADMAP.md`：整体路线图，唯一权威的「我们要往哪走」。
- `plan/step-NN-*.md`：每个 step 的设计笔记（目标、决策、取舍、验证结果、遗留问题）。**step 做完必须写**，这是本项目最重要的产物之一。
- `probes/`：对环境与 API 的真实探测记录，必须写明日期与结论，区分「实测」与「推测」。
- 未验证的东西一律显式标注「未验证」，不要包装成结论。

## 7. 环境事实

- 工作目录：`/home/xtyi/proj/xagent`
- **解释器用 conda base**：`/home/xtyi/miniforge3/bin/python`（Python 3.12.11）。
  PATH 里的 `python3` 是系统 Python（`/usr/bin/python3`，3.12.3），**没有 pytest**，不要拿它跑测试。
  - 跑测试：`conda run -n base python -m pytest -q`（或 `conda activate base` 后 `python -m pytest -q`）。
  - 新依赖装到 conda base。
- 运行时核心代码零第三方依赖，所以 `python -m xagent` 用哪个解释器都能跑；只有测试需要 conda base。
- 默认后端：DeepSeek 官方 API（OpenAI 兼容 `/chat/completions`），默认模型 `deepseek-flash`。
- **配置只从项目自己的 `.xagent/config.toml` 读**，不依赖任何外部工具的配置。该文件含密钥，
  已被 gitignore；仓库里只提交 `.xagent/config.toml.example` 模板。
  - 优先级（每项独立生效）：CLI flag > 环境变量 > `.xagent/config.toml` > 内置默认。
  - 环境变量：`XAGENT_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`、`XAGENT_BASE_URL`、
    `XAGENT_MODEL`、`XAGENT_PROVIDER`、`XAGENT_CONFIG`（指向别的配置文件）。
  - 必须往 stderr 打一行凭据**来源**提示，且永远不打印密钥本身。
  - 加配置项要同时改三处：`.xagent/config.toml.example`、`load_config_file`、`tests/test_config.py`。
- 该后端是 **thinking 模型**：多轮时上一层 assistant 的 `reasoning_content` 必须原样回传，否则 400。见 `probes/000-backend-capabilities.md`。
- 真实 API 调用需要网络；离线验证一律走 `backends/mock.py`。

## 8. 明确不做的

- 不追求生产可用、不追求性能、不追求覆盖所有模型厂商。
- 不在 ROADMAP 排到之前引入 MCP / RAG / 多 agent 编排。
- 不提交没有讲解和验证的大块代码。
