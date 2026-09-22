# Step 1：最小对话循环（流式）

日期：2026-09-22
状态：已完成并验证

## 目标

`python -m xagent` 能进入 REPL，输入一句话看到模型**流式**回答，并且能多轮对话。

刻意不做的事：工具调用、文件读写、权限、TUI、上下文压缩、持久化。这一 step 只回答一个问题——
**在还没有工具之前，一个 agent 的骨架是什么样？**

答案：一个消息列表 + 一次 HTTP 请求 + 一个把增量拼回列表的循环。

## 分层结果

```
cli.py            ← 唯一与人对话的模块
  ├── config.py   ← 唯一读环境变量/配置文件的地方
  ├── ui.py       ← 唯一写终端的地方
  └── agent.py    ← 循环，不碰 HTTP、不碰终端
        ├── messages.py            ← 唯一的 wire 编解码点
        └── backends/
              ├── base.py          ← 协议：只定义「事件流」的形状
              ├── openai_compat.py ← HTTP + SSE + JSON
              └── mock.py          ← 同一个协议的离线实现
```

依赖方向单向向下。`agent.py` 拿到的是 `StreamEvent`，交回去的是 `Message`；它不知道事件是怎么来的，
所以把 `openai_compat` 换成 `mock` 时循环一行都不用改。

## 关键设计决策

### 1. 没有 SDK，手写 SSE

用 `urllib` + 手写 SSE 解析（`iter_sse_payloads`），而不是 `openai` SDK。

理由：SDK 把「模型通信」这一层包成一个 `client.chat()` 调用，恰好把本项目最该看清的东西藏起来了。
手写之后能直接看到两件反直觉的事实：

- **思维链和正文是两条独立的流**。delta 里同时有 `reasoning_content` 和 `content`，交替到达，
  不是一个字段里的两部分。所以 `StreamEvent` 把 `reasoning` 和 `text` 分成两种事件，
  UI 也分开渲染。
- **流式和非流式只是传输层选择**。两者在 `OpenAICompatBackend.stream()` 内部收敛成同一串事件，
  上层完全无感 —— 这就是 `--no-stream` 只是一个构造参数的原因。

顺带一个细节：`stream_options.include_usage = true` 必须显式打开，否则最后一个 chunk 不带 token 计数。

### 2. `StreamEvent` 里没有 "done"

最初设计里有 `kind="done"`，写的时候去掉了：生成器耗尽本身就意味着「这一轮结束了」，
多一个 done 事件只会多一个需要保持同步的状态。**能用控制流表达的东西不要用数据表达。**

### 3. `Message.reasoning_content` 从第一天就要有

这是被实测逼出来的，不是预留：DeepSeek 的 thinking 模型要求把上一轮 assistant 的
`reasoning_content` 原样传回，丢掉就 400（错误原文见 `probes/000`）。

`Message.to_wire()` 里那句 `if self.role == "assistant"` 就是这条约束的唯一落点。
这正是「wire 编解码只放在一个地方」的价值：约束只写一次。

### 4. 一轮对话是**事务**

`Agent.checkpoint()` / `Agent.rollback()`：请求失败或用户 Ctrl-C 时，历史回退到这一轮之前，
**失败的轮次不留痕迹**。

这个选择有取舍：坏处是已经流式打印出来的半句话还在屏幕上（我们不做屏幕回滚）；
好处是历史永远处于「要么完整、要么没有」的干净状态，不会出现一条半截的 assistant 消息被带到下一轮
——在 thinking 模型上，半截消息缺少 `reasoning_content`，下一次请求就会直接 400。

### 5. 凭据来源显式化

`config.py` 从项目自己的 `.xagent/config.toml` 取凭据（格式仿照 Codex 的 `config.toml`）。
必须在 stderr 打印一行**来源**（`credential=...`），且永远不打印密钥本身。
便利性和可审计性不冲突，只要把来源说出来。

## 验证

### 离线（可重复，无网络）

```
$ conda run -n base python -m pytest -q
35 passed in 0.06s

$ printf '/help\nhello there\n/exit\n' | python3 -m xagent --mock
[config] backend=mock (offline, no network)
xagent -- /help for commands, /exit to quit
you> commands: ...
you> xagent> echo: hello there
[tokens: 0 in / 0 out]
```

测试覆盖：SSE 解析（多行 data、注释行、`[DONE]`、CRLF、未闭合尾事件）、chunk→event 翻译、
`to_wire` 的 `reasoning_content` 规则、循环的 history 形态、跨轮次回传 reasoning、
失败回滚、`MockBackend.echo`、凭据优先级与 base_url 归一化。

### 真实 API（`deepseek-flash`，实测通过）

多轮记忆 —— 这条同时证明了 reasoning 回传链路是通的（缺它第二跳必然 400）：

```
$ printf 'My name is Tianyi and I work on GPU compilers.\nWhat is my name and what do I work on?\n/exit\n' | python3 -m xagent
you> xagent> Good to meet you, Tianyi. What can I help you with ...
[tokens: 72 in / 53 out]
you> xagent> Your name is Tianyi, and you work on GPU compilers.
[tokens: 119 in / 51 out]
```

`--no-stream`（同一件事走非流式路径）：`xagent> pong`

`--show-reasoning`（思维链流被单独渲染成 dim 文本，之后才是正文 `391`）。

错误处理（故意用错 key）：

```
xagent> error: HTTP 401 from https://api.deepseek.com/v1/chat/completions: {"error":{"message":"Authentication Fails ..."}}
```

REPL 不崩、历史已回滚、可以继续输入。

## 未验证 / 已知不足

1. **未验证**：中断（Ctrl-C）路径只做了代码审查，没有实际按下过 Ctrl-C。
2. **未验证**：超长上下文、长时间挂起、并发请求的行为完全没测。
3. `--no-stream` 模式下 `reasoning_content` 与多轮的组合未单独测过（单轮验证过）。
4. 渲染层用 ANSI 转义直接拼字符串，没有做颜色能力检测（`NO_COLOR`、非 tty 场景会输出转义码）。
5. `input()` 的提示符里带 ANSI 码，长行编辑时 readline 的光标计算可能不准。
6. 每轮都全量重发历史，没有任何 token 计数或裁剪 —— Step 6 才处理。

## 下一步（候选）

见 ROADMAP。推荐顺序与理由：

1. **Step 2：工具调用协议**（推荐）—— 这是「chatbot → agent」的分水岭，也是本项目承诺要讲清楚的核心。
   现在 `agent.py` 只有一条直线，加上工具分支后才有真正意义上的「循环」。实测依据（分片拼装、
   `finish_reason == "tool_calls"`）已经在 `probes/000` 里拿到了。
2. Step 5：系统提示词与工作区上下文 —— 便宜且立刻提升可用性，但没工具时 agent 也没事可做，优先级低一些。
3. Step 6：上下文管理 —— 现在每轮全量重发，长对话迟早出问题，但还很远。
4. Step 7：会话持久化 —— 独立性强，哪天想脱离终端也行，但不推进核心理解。

## 变更记录

### 2026-09-22：测试框架 unittest → pytest

起因：确认常见第三方库可以用，要求把测试方式改成 pytest，依赖装进 conda base。

改动：

- `tests/` 三个文件重写为惯用 pytest 风格（模块级函数 + 裸 `assert` +
  `parametrize` / `monkeypatch` / `tmp_path`），删掉 `tests/__init__.py`（不再把 tests 当包）。
- 新增 `pyproject.toml` 承载 pytest 配置（`testpaths` + `pythonpath = ["."]`），
  这样不装包也能 `import xagent`。未配置打包，也没做 `pip install -e .`。
- 新增 `tests/test_config.py`，把此前完全没有测试的 config 层补上（凭据优先级、`/v1` 归一化、
  `ConfigError` 路径），顺带作为 `monkeypatch` / `tmp_path` 的示例。
- AGENTS.md 第 5、7 节同步：测试约定改为 pytest；环境事实写清「测试用 conda base 的
  `/home/xtyi/miniforge3/bin/python`，PATH 里的系统 `python3` 没有 pytest」。

结果：用例数 22 → 35（parametrize 展开 + config 层新增），全部离线通过。

边界：**运行时依赖仍然是零**。pytest 只在开发期需要，且不参与 `python -m xagent` 的运行路径。
这一点是刻意的 —— 想保持「clone 下来不装任何东西就能跑」。

### 2026-09-22：配置来源改为项目自有的 `.xagent/config.toml`

起因：原先凭据是从 `~/.codex/config.toml` 复用 Codex 的 provider 块。这有两个问题：
一是「读别人的配置文件」隐式耦合到一个外部工具，用户改了 Codex 配置这里就会跟着变；
二是别人 clone 这个仓库时既没有那个文件也不该去读它。要求改成项目自己持有配置。

改动：

- 新增 `.xagent/config.toml`（**已 gitignore**，含真实密钥，权限 0600）与
  `.xagent/config.toml.example`（提交的模板）。格式仿照 Codex：顶层 `model_provider` / `model` /
  `temperature` / `max_tokens` / `timeout`，每厂商一个 `[model_providers.<名字>]` 块。
  唯一的字段改名：`experimental_bearer_token` → `api_key`。
- `xagent/config.py` 重写：删掉 `load_codex_credential`，新增 `load_config_file` / `FileConfig` /
  `ProviderConfig`。路径由 `Path(__file__).parent.parent / ".xagent/config.toml"` 推导，
  **不依赖当前工作目录**（实测在 `/tmp` 下运行仍能找到项目配置）。可用 `XAGENT_CONFIG` 覆盖。
- 优先级统一成 **CLI flag > 环境变量 > 配置文件 > 内置默认**，每一项独立生效。

两个刻意选择的错误行为（都做了测试）：

1. **TOML 语法错要报错，而不是静默忽略**。静默会让「配置写了但不生效」变成靠猜的调试题。
2. **`model_provider` 指向文件里不存在的 provider 要报错**。这正是 `deepseel` 这种拼写错误
   最容易埋掉的地方 —— 不报错的话它会静默回退到内置默认，行为诡异且难查。

未复制内部 `mtcode` 代理：它只提供 Anthropic 系模型，且 `/chat/completions` 返回 500
（走的是别的协议），当前客户端连不上。写进配置只会制造一个坏掉的 provider 块。

结果：用例数 35 → 45；真实 API 多轮对话验证通过，凭据来源显示
`credential=/home/xtyi/proj/xagent/.xagent/config.toml [deepseek]`。
