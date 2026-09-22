# ROADMAP

这是本项目的教学大纲，也是唯一权威的「我们要往哪走」。

排序原则：**后一阶段必须依赖前一阶段的产物**。每个阶段单独可运行、可验证、可讲解。
状态标记：`[ ]` 未开始，`[~]` 进行中，`[x]` 已完成。

---

## Step 0：约定与骨架 `[x]`

- 产出：`AGENTS.md`、`ROADMAP.md`、`probes/000-backend-capabilities.md`
- 学到：这类项目为什么需要分层；为什么先钉死后端能力再写代码

## Step 1：最小对话循环（流式） `[x]`

- **目标**：`python -m xagent` 能进入 REPL，输入一句话，看到模型流式回答，并且能多轮对话。
- **关键点**：
  - 自己手写 OpenAI 兼容的 `/chat/completions` 请求与 SSE 解析（不依赖 SDK，看清「没有魔法」）。
  - `Message` 数据模型，以及 `to_wire()` 这层「模型 ↔ wire」的边界。
  - `Agent.turn()`：循环只有一个形态 —— 把对话发给模型、把增量拼成一条 assistant 消息、放回对话。
  - 处理 DeepSeek thinking 模型的 `reasoning_content` 回传约束（见 `probes/000`）。
- **产出**：`xagent/{config,messages,agent,ui,cli}.py`、`xagent/backends/*`、`tests/*`
- **学到**：agent 的最小内核其实只是「消息列表 + 一次 HTTP + 一个 while」。

## Step 2：工具调用协议 `[ ]`

- **目标**：模型能调用 `read_file` / `list_dir`，agent 把结果回填后再问一次模型。
- **关键点**：
  - tools 层：JSON Schema 定义、注册表、参数校验、执行、结果序列化。
  - 流式 tool_calls 按 `index` 分片拼装（`probes/000` 第 3 节）。
  - loop 里出现第一个分支：`finish_reason == tool_calls` → 执行 → 继续；否则结束本轮。
  - 引入 `max_iterations` 防止无限循环。
- **学到**：所谓「agent」和「chatbot」的差别，就是这个分支。

## Step 3：文件编辑 `[ ]`

- **目标**：能读能改代码，改动以 diff 形式展示。
- **关键点**：`apply_patch` 式编辑（上下文锚点 vs 行号）、失败回退、大文件读取的截断策略。
- **学到**：为什么 Claude Code / Codex 都用「搜索-替换块」而不是「整文件重写」。

## Step 4：命令执行与安全边界 `[ ]`

- **目标**：能跑 shell 命令；危险操作需要审批。
- **关键点**：`subprocess` 的流式输出、超时、输出截断；`policy/` 层独立于工具实现；审批交互。
- **学到**：权限模型为什么必须独立成层，而不是散落在各工具里。

## Step 5：系统提示词与工作区上下文 `[ ]`

- **目标**：agent 知道自己是谁、在哪、有哪些约定。
- **关键点**：系统提示词工程、自动加载 `AGENTS.md`、cwd/目录树注入、`.gitignore` 过滤。
- **学到**：为什么真实工具的 prompt 大部分在讲「环境信息」而不是「行为规则」。

## Step 6：上下文管理 `[ ]`

- **目标**：长对话不炸上下文窗口。
- **关键点**：token 估算、历史裁剪策略、自动压缩（compaction）、保留哪些「不可丢」消息。
- **学到**：Codex/Claude Code 的 compaction 在工程上为什么这么麻烦。

## Step 7：会话持久化与恢复 `[ ]`

- **目标**：退出后能 `--resume` 接着聊。
- **关键点**：transcript 落盘格式、session id、回放与重建。

## Step 8：终端 UI `[ ]`

- **目标**：从裸 stdout 升级到可用的 TUI。
- **关键点**：diff 着色、tool call 折叠、流式渲染的刷新节奏、中断（Ctrl-C）语义。

## Step 9：子 agent 与任务委派 `[ ]`

- **目标**：主 agent 能把子任务派给独立上下文的子 agent。
- **关键点**：上下文隔离、结果回传、并发控制、失败处理。

## Step 10：扩展机制 `[ ]`

- **目标**：把「加能力」从「改核心代码」变成「挂扩展」。
- **关键点**：MCP 协议、skills 装载、hooks 生命周期。

---

## 贯穿始终的问题清单

每做完一个 step，回头问一次：

1. 这一层现在是**谁**在负责？有没有偷偷跨层？
2. 真实工具（Codex / Claude Code）在这一层做了哪些我们没做的取舍？为什么？
3. 我们的验证覆盖到什么程度？哪些只是「看起来对」？
