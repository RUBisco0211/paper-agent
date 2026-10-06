# 0013 不做 Node BFF，前端直连两个 origin

- DATE: 2026-10-05
- TAGS: api, frontend
- STATUS: 当前
- SUPERSEDES: —

## DECISION

删掉 `web_ui/backend` 空壳（它只有 `GET /api/health`，依赖仅 express + cors），不建 Node BFF。前端直连两个 origin：业务服务（论文库 / 项目 / 摄取 / 检索）与 agent_service（会话 / SSE），都带业务服务签发的同一个 JWT。CORS 在两个服务各配一次。**认证只有一套，用户库只有一个。**

## REJECTED

- Node BFF 统一入口：两套语言与部署，收益只有「统一 origin」。
- 业务服务反代 `/agent/*` 并注入 `X-User-ID`：SSE 过代理要单独处理缓冲与超时，且退回 header 占位身份。
- 前端只连 BFF、由 BFF 转发 SSE：延迟增加，且要自己实现 SSE 转发。

## RATIONALE

业务 API 本身就是 FastAPI，能直接提供 REST；BFF 的聚合收益不足以抵消多一个运行时。SSE 长连接过反代是常见坑，绕开它。

## OUT OF SCOPE

服务端渲染、API 网关、请求聚合层。

## OPEN

两个 origin 的地址如何配置（构建期环境变量 vs 运行时探测页）；开发环境 CORS 与生产同源部署的差异。
