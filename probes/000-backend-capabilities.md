# 探测 000：后端能力（DeepSeek 官方 API）

日期：2026-09-22
方式：直接 `urllib` 打 HTTP，不经过任何 SDK。全程未打印密钥。

## 结论（全部为实测）

### 1. 端点可用性

| 端点 | 结果 |
| --- | --- |
| `GET https://api.deepseek.com/v1/models` | 200，返回 `deepseek-flash`、`deepseek-v4-pro` |
| `POST https://api.deepseek.com/v1/chat/completions` | 200 |
| `POST https://api.deepseek.com/v1/responses` | 200（Responses API 也通，但本项目不用） |

### 2. 流式（SSE）形态

- 标准 `data: {...}` 行 + 结尾 `data: [DONE]`。
- `stream_options: {"include_usage": true}` 生效：最后一个 chunk 带 `usage`。
- **每个 delta 里多一个 `reasoning_content` 字段**，与 `content` 交替到达：

```
{"role": "assistant", "content": null, "reasoning_content": ""}
{"content": null, "reasoning_content": "The"}
{"content": null, "reasoning_content": " user"}
...
{"content": "I", "reasoning_content": null}
{"content": "'ll", "reasoning_content": null}
```

也就是说：思维链和正文是**两条独立的流**，不是混在 `content` 里。

### 3. 工具调用

非流式可用，形态与 OpenAI 一致：

```
finish_reason = "tool_calls"
message.tool_calls = [{"index":0,"id":"call_00_...","type":"function",
                       "function":{"name":"get_weather","arguments":"{\"city\": \"Beijing\"}"}}]
```

流式下工具参数是**逐字符分片**到达，必须按 `index` 自行拼装：

```
{"tool_calls":[{"index":0,"id":"call_...","type":"function","function":{"name":"get_weather","arguments":""}}]}
{"tool_calls":[{"index":0,"function":{"arguments":"{"}}]}
{"tool_calls":[{"index":0,"function":{"arguments":"\""}}]}
...
```

注意：首片带 `id` 和 `function.name`，后续片**只有** `function.arguments`。

### 4. 关键约束：thinking 模型必须回传 `reasoning_content`

把 assistant 消息（含 `tool_calls`）放回 `messages` 时，如果丢掉 `reasoning_content`：

```
HTTP 400 {"error":{"message":"The `reasoning_content` in the thinking mode must be passed back to the API.",
                   "type":"invalid_request_error","code":"invalid_request_error"}}
```

`content: null`、`content: ""` 两种写法都一样报错；**只有带上 `reasoning_content` 才 200**。
`deepseek-v4-pro` 同样如此。

实测通过的多轮形态：

```json
{"role":"assistant","content":null,
 "reasoning_content":"I should call the tool.",
 "tool_calls":[{"id":"call_1","type":"function",
                "function":{"name":"get_weather","arguments":"{\"city\":\"Beijing\"}"}}]}
{"role":"tool","tool_call_id":"call_1","content":"{\"temp_c\":21,\"sky\":\"clear\"}"}
```

## 对本项目的直接影响

1. `Message` 必须携带 `reasoning_content`，且 assistant 消息回传时要带上 —— 这是 Step 1 就要有的字段，不是以后再说。
2. 流式解析要区分 `reasoning` 与 `text` 两类事件，UI 分别渲染。
3. 工具参数拼装（Step 2）要按 `index` 聚合分片，不能假设一次到齐。

## 未验证 / 未覆盖

- 内部代理 `mtcode`（`aicode-proxy.devops.mthreads.com`）只提供 Anthropic 系模型，且 `/chat/completions` 返回 500 —— 它走的是别的协议，本项目暂不接入。
- 未测 `logprobs`、`response_format`、图片输入、并发限流、超长上下文截断行为。
