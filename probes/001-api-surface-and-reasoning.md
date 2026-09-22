# 探测 001：API 端点全景、思考控制与 finish_reason（DeepSeek 官方 API）

日期：2026-09-23
方式：直接 `urllib` 打 HTTP，不经过任何 SDK。全程未打印密钥。
环境：`base_url = https://api.deepseek.com/v1`，模型 `deepseek-flash`（未特别说明时）。
关联：`probes/000-backend-capabilities.md`。本文件补充其未覆盖的部分，并修正其中一处措辞。

## 结论（除明确标注「未验证」外，全部为实测）

### 1. 端点不止 `chat/completions`

判断方法：`404` = 无此路由；`405` = 路由存在但方法不对；`200` = 可用。

| 端点 | 结果 | 说明 |
| --- | --- | --- |
| `GET /models` | 200 | 模型列表（带能力元数据，见 §6） |
| `GET /models/{id}` | 200 | 单个模型 |
| `POST /chat/completions` | 200 | 本项目使用的主接口 |
| `POST /responses` | 200 | OpenAI 新面对应物，形状见 §4 |
| `POST /completions` | 400 | legacy 补全，**只在 `/beta` base 下开放** |
| `GET /files` | 200 | 返回 `{"object":"list","data":[],"has_more":false}` |
| `GET /user/balance` | 200 | 返回 `is_available` + `balance_infos`（币种/余额），OpenAI 没有 |
| `/embeddings` `/moderations` `/batches` `/images/*` `/audio/*` `/assistants` `/threads` `/fine_tuning/*` `/beta` | 404 | 不存在 |

`POST /completions` 的错误原文：

```
completions api is only available when using beta api (set base_url="https://api.deepseek.com/beta")
```

另外 `/models` 返回里带 `api_capabilities.anthropic_messages`，说明服务还提供一套 Anthropic 风格的端点（未进一步探测）。

### 2. 思考是否发生：默认由模型决定，可手动关闭

默认（不传任何参数）思考长度**不确定**：同一句 prompt 连跑三次，`reasoning_content` 长度 = `[241, 108, 214]`。

| 参数 | 结果 |
| --- | --- |
| `thinking={"type":"disabled"}` | reasoning 清零，3/3 稳定为 0 |
| `thinking={"type":"enabled"}` | 正常思考 |
| `thinking=False`（布尔） | HTTP 422：`expected struct ThinkingOptions` |
| `reasoning_effort="none"` | reasoning 清零，3/3 稳定为 0 |
| `reasoning_effort="minimal"` / `"low"` / `"high"` | 仍会思考 |
| `enable_thinking=False` | 被静默忽略，仍会思考 |
| `effort="low"` / `"max"` | HTTP 200 接受，但**效果未验证** |

两个要点：

1. `thinking` 必须是对象（`{"type": "disabled"}`），传布尔值报 422。
2. `effort` 参数被接受，但思考长度本身波动大，单次采样证明不了它真的改变强度 —— 所以只能说「参数被接受」，不能说「效果已验证」。

### 3. `finish_reason`

含义：本次生成「为什么停下」，是调用方决定下一步的依据。

| 取值 | 含义 | 实测 |
| --- | --- | --- |
| `stop` | 模型自然说完 | 是 |
| `length` | 撞到 `max_tokens` / 上限，输出被截断 | 是 |
| `tool_calls` | 模型要求调用工具 | 是（此时 `message` 多出 `tool_calls` 键） |
| `content_filter` | 输出被安全过滤 | **未验证** |

位置：`choices[0].finish_reason`。流式下**中间帧为 `null`，只有最后一帧才有值**。

`tool_calls` 实测形态（非流式）：

```json
{"role":"assistant","content":null,"reasoning_content":"...",
 "tool_calls":[{"index":0,"id":"call_00_...","type":"function",
                "function":{"name":"get_weather","arguments":"{\"city\": \"Beijing\"}"}}]}
```

### 4. `POST /responses` 的形状

请求字段改名：`messages` → `input`、system 消息 → `instructions`、`max_tokens` → `max_output_tokens`。

实测响应（`{"model":"deepseek-flash","input":"Reply with exactly: hi","max_output_tokens":200}`）：

```json
{"object": "response", "status": "completed",
 "output": [
   {"type": "reasoning", "status": "completed",
    "content": [{"type": "reasoning_text", "text": "The user wants me to reply ..."}],
    "summary": [], "encrypted_content": "32decae7-..."},
   {"type": "message", "role": "assistant", "phase": "final_answer",
    "content": [{"type": "output_text", "annotations": [], "text": "hi"}]}
 ],
 "usage": {"input_tokens": 35, "output_tokens": 15,
           "input_tokens_details": {"cached_tokens": 0},
           "output_tokens_details": {"reasoning_tokens": 13}, "total_tokens": 50}}
```

与 `chat/completions` 的关键差别：

- 输出是**类型化 item 的数组**（`reasoning` / `message`，将来还有 `function_call`），不是 `choices[].message`。
- 没有 `finish_reason`，用 `status: "completed"`。
- usage 用 `input_tokens` / `output_tokens`，不是 `prompt_tokens` / `completion_tokens`。
- 顶层字段里有 `previous_response_id` / `store` / `background` / `service_tier` / `truncation` 等（支持服务端保存会话状态）。
- reasoning item 这里**同时**给了完整正文（`content[].text`）和一个不透明的 `encrypted_content`。

**未验证**：`/responses` 的流式事件名（OpenAI 是 `response.output_text.delta` / `response.completed` 一类），以及 `previous_response_id` 接续的实际行为。

### 5. 流式 chunk 的层级（并修正 `probes/000` 的一处措辞）

一行 `data:` 里是一整个 **chunk**，顶层键：

```
id, object(=chat.completion.chunk), created, model, system_fingerprint, choices, usage
```

`delta` 藏在 `choices[0].delta` 里。第一帧原样：

```json
{"id":"cc4b6528-...","object":"chat.completion.chunk","created":1790099775,
 "model":"deepseek-flash","system_fingerprint":"aeb5...",
 "choices":[{"index":0,"delta":{"role":"assistant","content":null,"reasoning_content":""},
             "logprobs":null,"finish_reason":null}],
 "usage":null}
```

要点：

- `delta` 内三个键：`role`（仅第一帧）、`content`、`reasoning_content`。后两个**键总在，值可能是 `null` 或 `""`**。
- `usage` 在 **chunk 顶层**（不在 delta 内），平时 `null`，开了 `include_usage` 的最后一帧才有值。
- `finish_reason` 在 `choices[0]` 里，与 delta 平级。

**修正 `probes/000`**：那里写「与 `content` 交替到达」，容易误读为一个 token 思考、一个 token 回答那样细粒度交错。实测更接近**先后相接的两段**——先一整段 reasoning，再一整段 content。112 个 delta 的归属序列是：

```
-RRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRCCCCCCCCCCCCCCCCCCCCCCCCCCCCC-
```

统计（该次实测）：两者同时非空 = 0，「只有 reasoning」= 81，「只有 content」= 29，「都为空」= 2。含义不变（两路独立、必须分别累积），但「交替」这个词不准。

### 6. `/models` 的元数据

DeepSeek 的 `/models` 比 OpenAI 的多出能力信息：

```json
{"id": "deepseek-flash", "name": "DeepSeek-V4.1-Flash",
 "context_window": 1048576, "max_output_tokens": 393216,
 "input_modalities": ["text", "image"], "output_modalities": ["text"],
 "effort": {"supported_levels": ["low", "high", "max"], "default_level": "high"}}
```

`deepseek-v4-pro` 的 `input_modalities` 只有 `["text"]`（无 image）。`effort.default_level` 是 `high`，解释了 §2 里默认「会思考」。

### 7. 非流式 `message`：两字段可同时有值

非流式把 `delta` 换成 `message`，字段一样。实测一次「思考 + 回答」：

```
message 键 = ['role', 'content', 'reasoning_content']
reasoning_content 长度 = 159   content 长度 = 51
```

边界：若 `max_tokens` 太小，思考会把预算吃光，出现 **`reasoning_content` 有值、`content` 为空**、`finish_reason=length` 的情况。所以「两者都有值」是常见情况，不是保证。

### 8. `n` 只支持 1

传 `n=2` 报错，`choices` 永远是 1 个：

```
HTTP 400 {"error":{"message":"Invalid n value (currently only n = 1 is supported)", ...}}
```

但 `choices` 结构上仍是数组，代码应遍历而非硬写 `[0]`。

### 9. `max_tokens` 与 `reasoning_tokens` 共用预算

`usage.completion_tokens_details.reasoning_tokens` 单列，但它**算进 `completion_tokens`**。`max_tokens=64` 时思考消耗了全部 64，`content` 为空、`finish_reason=length`。

## 未验证 / 未覆盖

- 上述大部分实验只跑了 `deepseek-flash`；`deepseek-v4-pro` 只确认了它出现在模型列表中，参数行为未单独测。
- `reasoning_effort` / `effort` 各档位对输出质量、长度的真实影响（采样太少，被波动盖过）。
- `finish_reason="content_filter"` 未触发到。
- `/responses` 的流式事件名与 `previous_response_id` 的接续行为。
- Anthropic 风格端点（`api_capabilities.anthropic_messages`）未探测。
- 与 OpenAI 官方行为的逐条对照均**凭知识**，本项目无 OpenAI key，未实测。
