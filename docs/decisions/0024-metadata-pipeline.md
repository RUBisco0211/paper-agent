# 0024 元数据链路：前 5 页布局 → 识别 → 标识符在线补全

- DATE: 2026-10-05
- TAGS: ingest, product
- STATUS: 当前
- SUPERSEDES: `docs/overview/minimal-mvp.md` F03 中元数据部分（已删除）

## DECISION

元数据链路：读 PDF 前 5 页的文本、行与词级布局（不做 OCR）→ Zotero recognizer 识别 → 识别出 DOI/arXiv 就做精确在线查询补全 → 只有标题作者就保存已有结果 → 未识别或服务失败则保留占位，允许补填标识符再试。**正文处理独立继续，不因元数据未识别而阻断。** 元数据状态区分识别成功 / 部分字段 / 未识别 / 服务失败。MinerU 产物（`content_list.json`、Markdown、图片）留存并记录版本。失败重试只重做必要阶段（0019）。

## REJECTED

- GROBID：0001 已否决。
- 用 MinerU 或 LLM 猜元数据：前者不是它的职责，后者消耗用户 Key 且结果不稳定。
- 元数据失败就阻断正文：把已有的解析能力一起藏掉。
- 无限自动重试：鉴权与额度错误必须明确提示。
- 解析取消、换 Embedding 模型重建、多解析器自动回退：均后置。

## RATIONALE

该 recognizer 是未公开接口，只作为尽力而为的默认适配器；正文可用才是主链路。

## OUT OF SCOPE

OCR 与扫描件、中文文献、多解析器回退、完整书目编辑器。

## OPEN

Python 本地提取器选型 —— 必须用样例验证页、行、词、字体、坐标是否满足识别输入。
