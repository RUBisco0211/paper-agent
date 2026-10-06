# 0004 LLM API Key 只随请求进入执行器

- DATE: 2026-09-19
- TAGS: security
- STATUS: 已被 0015 取代（改用框架 Credential 系统，Key 落服务端）
- SUPERSEDES: —

## DECISION

LLM API Key 保存在浏览器，随 Agent 启动或恢复请求提交，只进入当前执行器。后端不把它写入数据库、日志、对象存储或任务队列。

## REJECTED

- 把 Key 持久化到用户配置表以便"记住我"：一旦落库就会进入备份、日志与任务队列的扩散路径。
- 在服务端记录 Key 指纹或前缀用于排错：任何派生值都可能在日志里被反推或误报。
- 允许客户端提交 Base URL：等于把请求目标交给前端，绕过模型目录校验。

## RATIONALE

Key 是第三方凭据，最短存活路径就是不落任何持久化介质。代价是每次启动 Agent 都要重新提交，可接受。

## OUT OF SCOPE

服务端托管的共享 Key、Key 轮换、用量计费。

## OPEN

真实 Provider 的浏览器闭环尚未验收，Key 传递路径只在离线用例下验证过。
