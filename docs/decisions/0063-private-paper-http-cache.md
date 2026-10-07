# 0063 授权文献 HTTP 条件缓存

- DATE: 2026-10-08
- TAGS: api, library, cache
- STATUS: 当前
- SUPERSEDES: —

## DECISION

PDF、MinerU 分块列表、单块与块图片返回私有 ETag 和 `Cache-Control: private, no-cache`；匹配 `If-None-Match` 时返回 304。每次条件请求先校验用户归属及目标资源存在。PDF 版本取文件哈希，解析产物版本取文件哈希和已发布的 manifest key；旧产物无 manifest 时使用论文更新时间。列表 ETag 包含类型和分页参数。

## REJECTED

不使用 localStorage、IndexedDB 或 Cache Storage 自建文献缓存；不使用 `public` 或长期免验证的缓存策略。

## RATIONALE

浏览器 HTTP 缓存保留已授权响应，重验证时只在版本未变化且资源仍可用时复用字节。旧产物若直接覆盖对象而不更新论文时间，缓存版本无法改变，旧路径写入者需保证更新时间变化。

## OUT OF SCOPE

分段读取与 Range 请求、跨设备离线缓存。

## OPEN

无。
