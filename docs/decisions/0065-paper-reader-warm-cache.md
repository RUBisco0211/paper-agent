# 0065 阅读页 PDF 热缓存

- DATE: 2026-10-08
- TAGS: frontend, library, cache
- STATUS: 当前
- SUPERSEDES: —

## DECISION

阅读页在当前登录会话的 QueryClient 中短时复用 PDF Blob，1 分钟内重新打开同一文献不重复请求字节，闲置 5 分钟回收。补传或替换 PDF 时失效；登录、退出与切换用户时清空。PDF 页面仅预绘制邻近视口 200px 的区域。

## REJECTED

不把 PDF 原文字节放入跨登录会话的持久前端状态；不在打开时预绘制多个屏幕外页面。

## RATIONALE

HTTP 304 仍有往返与浏览器读取缓存的成本；短时内存复用改善重复打开。较小的预绘制范围减少初始画布工作量。

## OUT OF SCOPE

PDF.js 已解析文档跨页面复用、Range 请求和持久离线缓存。

## OPEN

大 PDF 的剩余解析耗时需通过实际浏览器性能记录定位。
