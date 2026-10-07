# 0053 页面内 PDF 渲染

- DATE: 2026-10-07
- TAGS: frontend, product
- STATUS: 当前
- SUPERSEDES: —

## DECISION

授权 PDF 由现有业务接口获取，在前端用 PDF.js 绘制到页面内的 canvas。引用传入的可靠页码定位到对应页，并提供基础翻页、缩放与加载错误提示。PDF worker 作为前端静态资源打包。

## REJECTED

- 浏览器原生 iframe PDF 预览：浏览器联调时出现空白，难以稳定控制页码与错误状态。
- 当前直接套用 Extend UI PDF Viewer：其公开接口未提供受控的初始引用页，接入现有授权和引用定位需额外适配；后续需要搜索、选中文本或缩略图时再评估。

## RATIONALE

引用原文核对需要稳定显示授权文献与所引用的页面。基础控件延续 0029 的范围。

## OUT OF SCOPE

文本选择、全文搜索、缩略图、区域高亮与 PDF 编辑。

## OPEN

浏览器中的实际画面仍需人工回测。
