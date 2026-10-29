# 0099 统一的聊天入口取代独立引用接口

- DATE: 2026-10-29
- TAGS: agent, api, security
- STATUS: 当前
- SUPERSEDES: 0079 中「引用另走一条独立入口」的实现方式（引用校验与提示词规则不变）

## DECISION

- 只保留一个聊天入口 `POST /chat/`，请求体在 AgentScope 的 `ChatRequest` 上增加可选的 `references` 与 `mentions`；两者都为空时行为与上游完全一致。
- 有引用时由本项目 `chat_entry` 先向业务服务核验（`quote-reference/resolve`，`kind` 区分 `paper` / `parsed_block` / `pdf_selection`），再构造 `UserMsg` 交给同一个 `ChatService.run`，不新增第二条执行链路。
- 实现方式是被动接管而非改写上游：调用 `create_app` 前从上游 `chat_router` 移除内置 `POST /chat/` 路由，随后挂载本项目入口。上游包文件不改，升级后需复核 `ChatRequest` 字段与 handler 依赖签名。
- `mentions` 在正文里以 `@{{n}}` 占位，服务端替换为 `@《标题》(paper:用户条目 id)`；模型据此直接调用 `read_paper`，不靠标题匹配。
- 删除 `/quoted-chat`：无外部使用者，前端改为统一调用 `/chat/`。

## REJECTED

- 直接修改 `site-packages` 里的上游路由：重装依赖即丢失，且违反 0033。
- 整车重写上游 handler：它同时承载 HITL 恢复、外部工具结果回填与子 Agent 路由，重写等于重复实现流式与中断。
- 继续保留两条入口只改名：校验逻辑会分散在两处，前端也要维护两条发送路径。

## RATIONALE

引用校验属于「发送前」的服务端职责，放在唯一入口让纯文本与引用共享同一套会话校验、模型配置与执行链路。

## OUT OF SCOPE

输入框 `@` 交互、`$` Skill、`/` 流程模板。

## OPEN

上游升级后 `ChatRequest` 或 `chat` handler 签名变化时的兼容检查清单。
