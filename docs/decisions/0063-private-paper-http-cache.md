# 0063 授权文献缓存与阅读页短时复用

- DATE: 2026-10-08（2026-10-09 合并整理）
- TAGS: api, library, frontend, cache
- STATUS: 当前
- SUPERSEDES: 0065

## DECISION

PDF、MinerU 分块列表、单块与块图片返回私有 ETag 和 `Cache-Control: private, no-cache`；匹配 `If-None-Match` 时返回 304。每次条件请求先校验用户归属与资源存在。PDF 版本取文件哈希，解析产物版本取文件哈希和已发布 manifest key；旧产物无 manifest 时使用论文更新时间。列表 ETag 包含类型与分页参数。

阅读页在当前登录会话的 QueryClient 中短时复用 PDF Blob：1 分钟内重新打开不重复请求，闲置 5 分钟回收；补传或替换 PDF 时失效，登录、退出与切换用户时清空。PDF 页面只预绘制邻近视口 200px 的区域。

## REJECTED

- 用 `localStorage`、IndexedDB 或 Cache Storage 自建持久文献缓存：二进制容量、版本与账号隔离复杂。
- 使用 `public`、长期免验证缓存，或让 PDF 原文字节跨登录会话复用：会破坏归属与版本检查。
- 打开时预绘制多个屏幕外页面：增加初始画布工作量。

## OUT OF SCOPE

PDF Range/分段读取、跨设备离线缓存、PDF.js 已解析文档的跨页复用。

## OPEN

大 PDF 的剩余解析耗时仍需浏览器性能记录定位；旧路径写入者须保证论文更新时间变化。
