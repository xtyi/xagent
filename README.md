# xagent

一个**从零实现、面向学习**的 code agent。目标不是替代 Codex / Claude Code，而是把它们的内部机制一层层拆开、实现、验证。

工作方式与约定见 [AGENTS.md](AGENTS.md)，整体路线图见 [plan/ROADMAP.md](plan/ROADMAP.md)。

## 当前进度

**Step 1：最小对话循环（流式）** —— 能进入 REPL 多轮对话，自己手写 OpenAI 兼容请求与 SSE 解析，无 SDK、无第三方依赖。

## 快速开始

```bash
cd /home/xtyi/proj/xagent

# 离线跑通（不需要 key、不联网）
python3 -m xagent --mock

# 真实后端（默认 DeepSeek 官方 API；凭据自动从 ~/.codex/config.toml 复用）
python3 -m xagent
python3 -m xagent --show-reasoning
python3 -m xagent --no-stream --once "Reply with exactly: pong"

# 测试（离线，35 个用例）—— 用 conda base，pytest 装在那里
conda run -n base python -m pytest -q
```

REPL 命令：`/help`、`/reset`、`/usage`、`/reasoning`、`/exit`。

## 依赖

运行时**零第三方依赖**，只用标准库 —— 所以 `python -m xagent` 用系统 `python3` 也能跑。
测试用 `pytest`（装在 conda base）。配置在 [pyproject.toml](pyproject.toml)，目前只含 pytest 配置，
项目还没做打包（不需要 `pip install`，从仓库根目录运行即可）。

测试放在 `tests/`，按被测的层分文件：`test_sse.py`（传输解析）、`test_messages.py`（wire 编码）、
`test_agent.py`（循环与回滚）、`test_config.py`（凭据优先级）。

## 代码地图（按阅读顺序）

| 文件 | 层 | 职责 |
| --- | --- | --- |
| `xagent/messages.py` | messages | 对话数据模型 + `to_wire()` 这个 wire 边界 |
| `xagent/backends/base.py` | transport | `Backend` 协议与 `StreamEvent`，不含 HTTP |
| `xagent/backends/openai_compat.py` | transport | `/chat/completions` 请求、SSE 解析、事件翻译 |
| `xagent/backends/mock.py` | transport | 离线脚本化后端，供测试与 `--mock` |
| `xagent/agent.py` | loop | 一轮对话：发出去、拼回来、写回历史 |
| `xagent/config.py` | config | 模型与凭据解析（CLI 之外唯一读环境的地方） |
| `xagent/ui.py` | ui | 流式渲染，只负责显示 |
| `xagent/cli.py` | wiring | 把上面这些接起来，唯一与人对话的模块 |

分层的判断标准：任何一层都不应该知道它上面那一层的事。比如 `openai_compat.py` 完全不知道「工具」是什么。

## 已知的环境约束

DeepSeek 的模型是 thinking 模型：多轮对话必须把上一轮 assistant 的 `reasoning_content` 原样传回，否则 HTTP 400。实测记录见 [probes/000-backend-capabilities.md](probes/000-backend-capabilities.md)。
