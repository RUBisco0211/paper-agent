"""Generate synthetic previews only; never send mail or read actual user content.

Run from backend: uv run python -m app.platform.mail_preview
"""

from html import escape
from pathlib import Path

from .config import settings
from .mail_templates import (
    password_reset_email,
    schedule_result_email,
    verification_email,
)

ROOT = Path(__file__).resolve().parents[3]

SAMPLE = r"""## 今日阅读结果

本次共整理 **3 篇论文**。以下均为用于展示排版的合成内容，不对应真实论文。

| 主题 | 结论 | 下一步 |
| --- | --- | --- |
| 检索 | 多路召回适合不同问题 | 核对原文证据 |
| 引用 | 保留页码与来源 | 在站内查看 |

### 建议关注

1. 明确实验的适用范围。
2. 检查基线和消融设置。

> 邮件仅包含最终回答，不展示思考或工具执行过程。

```python
results = search("retrieval")
print(len(results))
```

公式保留 LaTeX：$s(q,d)=\sum_i q_i d_i$。

![实验图表](https://example.invalid/private-figure.png)

引用示例：[1]。请在本次运行记录内核对证据与原文。
"""


def main() -> None:
    directory = ROOT / ".var" / "mail-previews"
    directory.mkdir(parents=True, exist_ok=True)
    run_url = settings.public_app_url.rstrip("/") + "/scheduled/example/runs/example"
    previews = {
        "register": verification_email("123456", "register"),
        "reset-code": verification_email("123456", "password_reset"),
        "password-changed": password_reset_email(),
        "task-success": schedule_result_email(
            name="每日论文阅读 · 演示",
            markdown=SAMPLE,
            status="success",
            run_url=run_url,
        ),
        "task-failed": schedule_result_email(
            name="每日论文阅读 · 演示",
            markdown="",
            status="failed",
            run_url=run_url,
            error="模型请求过于频繁或额度不足，请检查额度并稍后重新运行。",
        ),
    }
    links = []
    for name, (subject, html, text) in previews.items():
        (directory / f"{name}.html").write_text(html, encoding="utf-8")
        (directory / f"{name}.txt").write_text(text, encoding="utf-8")
        links.append(f'<li><a href="{name}.html">{escape(subject)}</a></li>')
    (directory / "index.html").write_text(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        "<title>Paper Agent 邮件预览</title><h1>邮件模板预览</h1>"
        "<p>全部为合成示例；验证码与运行链接不可用于真实操作。</p><ul>"
        + "".join(links)
        + "</ul></html>",
        encoding="utf-8",
    )
    print("Generated five synthetic HTML/text previews in .var/mail-previews/")


if __name__ == "__main__":
    main()
