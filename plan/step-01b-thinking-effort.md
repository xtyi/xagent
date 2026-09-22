# Step 1b：思考强度与会话状态行

日期：2026-09-23
状态：已完成并验证

> 说明：这不是 ROADMAP 里原有的 Step 2（工具调用）。它是用户指定的插入 step，
> 编号取 `1b` 以避免打乱后面所有 step 的编号与交叉引用。

## 目标

两件事：

1. 让用户能控制模型的思考强度：`none`（禁止思考）/ `low` / `medium` / `high` / `max`。
2. 把「当前会话的配置」——模型、思考强度等——显示在一行 **status line** 里，
   并为以后加入权限控制等设置留好扩展点。

## 分层结果

改动严格顺着依赖方向，每层只碰自己的职责：

```
config.py         ← 新增 reasoning_effort 的设置项与校验（CLI>env>file>默认）
  └─ cli.py       ← 拼 status line 的字段；新增 --reasoning-effort 与 /status
       ├─ ui.py   ← 新增 status()（stdout）与 diagnostic()（stderr），只负责显示
       └─ backends/
            ├─ base.py          ← ModelParams 多一个 reasoning_effort 字段（后端无关）
            └─ openai_compat.py ← 把该字段翻译成 wire 上的 reasoning_effort
```

一个刻意的分工：`cli.py` 负责**决定**状态行里放哪些 (key, value)，`ui.py` 只负责**渲染**。
ui 不知道 `reasoning_effort` 是什么，也不需要知道。

## 关键设计决策

### 1. 先用实测定参数名和取值，再写代码

动手前先探了 API（记录在 `probes/001`），因为用户说的是 `low/medium/high`，
而 `/models` 声称支持 `low/high/max`，两者对不上。实测结论：

- `reasoning_effort` **接受** `none / minimal / low / medium / high / max`，全部 200；
- `reasoning_effort="none"` **稳定禁用**思考（5/5 次 reasoning 长度为 0）；
- `effort="..."` 同样被接受，但**无法证明它真的改变行为**（各档都照常思考）。

因此选择 `reasoning_effort` 这个 **OpenAI 标准字段名**：它既被实测证明有效（`none` 能关），
又不是 DeepSeek 私有参数。取值收敛为 `none / low / medium / high / max`——用户在 `low/medium/high`
之外多拿到一个 `max`（`/models` 声明的最高档）。

一个诚实标注：**各档位的强度差异没有验证**。`low`/`medium`/`high` 的 reasoning 长度在
重复采样下波动极大（见 `probes/001` §2），单次测量分不出信号。我们只保证「参数被发出且被接受」，
不保证「medium 一定比 high 想得少」。

### 2. 默认不发送（`None`），而不是默认某个档位

`reasoning_effort` 缺省是 `None` = 「不发送这个字段，交给模型自己的默认」。

理由：现状就是不发这个字段，默认值应保持行为不变；而「模型自己的默认」是会变的
（`/models` 现在说 `default_level=high`），写死一个档位反而制造了「配置说 high、实际是模型默认」
的假象。状态行把它显示成 `thinking=default`——**如实显示我们发了什么**，而不是猜模型在想什么。

### 3. 状态行的形状：`list[tuple[str, str]]`

状态行不是固定结构，而是一串 (key, value)。`ui.Renderer.status(fields)` 只管把它们连成一行。

用户明确说了以后还要加权限控制等会话配置。但这里**没有**提前造一个 `SessionStatus` dataclass：
目前需要的就是「一组键值对」，一个列表够用且立刻能扩展；等到出现第三种**结构不同的**会话信息
（而不是第三个键值对）再抽象。

### 4. 附带修复：凭据来源行移到 stderr

AGENTS.md 要求「必须往 stderr 打一行凭据来源提示」。原实现用 `renderer.note()` 打到了 stdout，
不满足要求。既然这次要重写这行，就顺手拆开：

- **stderr**（`diagnostic()`）：`[config] base_url=... credential=...` —— 接线与凭据来源；
- **stdout**（`status()`）：`[model=... thinking=... stream=...]` —— 面向用户的会话设置。

这一条是行为变化：原先把 `[config]` 当普通输出的人（比如脚本）会看到它跑到 stderr 去了。

## 验证

### 离线（可重复，无网络）

```
$ conda run -n base python -m pytest -q
69 passed in 0.11s

$ printf '/status\nhello there\n/exit\n' | python -m xagent --mock
[config] backend=mock (offline, no network)      # stderr
[model=mock thinking=default stream=on]          # stdout
xagent -- /help for commands, /exit to quit
you> [model=mock thinking=default stream=on]     # /status 重印同一行
you> xagent> echo: hello there
[tokens: 0 in / 0 out]
```

新增用例（45 → 69）：`reasoning_effort` 的文件解析 / 环境变量 / flag 优先级 / 大小写归一 /
未知取值报错（flag 与文件两条路径）；`build_payload` 在设置时发出、缺省时不发；`Renderer.status`
的单行与空列表；`Renderer.diagnostic` 只写 stderr；`status_fields` 的 `default` 标注；
parser 接受已知档位、拒绝未知档位。

### 真实 API（`deepseek-flash`，实测通过）

```
$ python -m xagent --once "What is 17*23? Think step by step." --reasoning-effort none --show-reasoning
[model=deepseek-flash thinking=none stream=on]
xagent> 17 × 23 = 17 × 20 + 17 × 3 = 340 + 51 = 391.
[tokens: 46 in / 26 out]          ← 没有 [thinking] 输出，token 明显更少

$ python -m xagent --once "What is 17*23? Think step by step." --reasoning-effort max --show-reasoning
[model=deepseek-flash thinking=max stream=on]
[thinking] We need answer simple. ... 391.
xagent> ... = **391**
[tokens: 71 in / 82 out]         ← 有思考块，token 更多
```

stdout/stderr 归属用重定向到文件单独确认：stdout 只有状态行/欢迎语/对话，stderr 只有 `[config]` 行。

环境变量路径也跑了一次真实请求（顺带证明优先级：环境变量压过文件）：

```
$ XAGENT_REASONING_EFFORT=none python -m xagent --once "What is 17*23? Think step by step." --show-reasoning
[model=deepseek-flash thinking=none stream=on]     ← 来自环境变量
xagent> 17 × 23 = ... = 391.                       ← 无 [thinking]
```

## 未验证 / 已知不足

1. **未验证**：`low/medium/high/max` 各档位对思考长度、延迟、答案质量的真实影响（采样太少，被波动盖过）。
2. **未验证**：`deepseek-v4-pro` 上的行为；所有真实 API 实验只跑了 `deepseek-flash`。
3. `/status` 只在 `--mock` 下手动看过，没在真实后端会话里按过。
4. 思考强度**只能在启动时设定**，会话中不能改（没有 `/effort` 之类的运行时命令）。加它会牵动
   `ModelParams` 的可变性与重发语义，留给以后。
5. `ModelParams` 现在同时被 mock 与真实后端使用，但 mock 忽略 `reasoning_effort`——
    mock 走的是同一份参数，只是不消费它。
6. `--mock` 路径**完全绕过** `config.py`，所以 `XAGENT_REASONING_EFFORT` 等设置对 mock 无效
   （这是既有行为：mock 不需要任何配置）。

## 下一步（候选）

见 ROADMAP。推荐：

1. **Step 2：工具调用协议**（ROADMAP 原定的下一步）——`probes/000`/`001` 已经拿到实测形态
   （`tool_calls` 分片按 `index` 拼装、`finish_reason == "tool_calls"` 分支）。
2. 会话中的 `/effort` 运行时切换——现在只能启动时定，改了要动 `ModelParams` 重发语义，比看起来大。
3. 权限控制（`policy/` 层）——用户已预告会加到状态行；那会是状态行第一次装进「非键值对」信息，
   可能触发 `SessionStatus` 抽象。
