"""Static mail layouts and script-free Markdown rendering; no remote fetches."""

from html import escape
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML

from .config import settings

_STYLE = """
body {
  margin:0; padding:24px 12px; background:#f5f5f4; color:#242424;
  font-family:Arial,'Microsoft YaHei',sans-serif; font-size:15px; line-height:1.7;
}
main {
  max-width:640px; margin:0 auto; padding:28px;
  background:#fff; border:1px solid #dededb;
}
h1 { font-size:22px; line-height:1.4; margin:12px 0 20px; }
h2 { font-size:19px; } h3 { font-size:17px; }
a { color:#245c42; text-decoration:underline; overflow-wrap:anywhere; }
table { border-collapse:collapse; width:100%; margin:16px 0; }
th,td { border:1px solid #d6d6d1; padding:8px; text-align:left; }
pre {
  background:#f3f3f0; padding:12px; white-space:pre-wrap; overflow-wrap:anywhere;
}
code { font-family:Consolas,monospace; }
blockquote {
  border-left:3px solid #d6d6d1; margin:16px 0; padding-left:14px; color:#555;
}
.brand,.footer { font-size:12px; color:#666; }
.footer { margin-top:24px; border-top:1px solid #dededb; padding-top:14px; }
.code {
  font-size:30px; letter-spacing:6px; font-family:Consolas,monospace; margin:24px 0;
}
""".strip()


def _layout(title: str, content: str) -> str:
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_STYLE}</style></head><body>"
        '<main><div class="brand">PAPER AGENT</div>'
        f"<h1>{escape(title)}</h1>{content}"
        '<p class="footer">此邮件由 Paper Agent 自动发送，请勿直接回复。</p>'
        "</main></body></html>"
    )


def verification_email(code: str, purpose: str) -> tuple[str, str, str]:
    title = "验证注册邮箱" if purpose == "register" else "验证密码重置请求"
    instruction = "请在页面中输入以下验证码，继续设置密码。"
    warning = "验证码 10 分钟内有效，请勿分享给他人。如果不是你本人操作，请忽略此邮件。"
    html = _layout(
        title,
        f'<p>{instruction}</p><div class="code">{escape(code)}</div><p>{warning}</p>',
    )
    return (
        f"Paper Agent · {title}",
        html,
        f"{title}\n\n{instruction}\n\n{code}\n\n{warning}",
    )


def password_reset_email() -> tuple[str, str, str]:
    title = "密码已重置"
    content = (
        "你的 Paper Agent 密码已成功重置，所有旧登录会话已失效。请使用新密码重新登录。"
    )
    warning = "如果不是你本人操作，请立即通过找回密码重新设置密码，并检查邮箱账号安全。"
    return (
        f"Paper Agent · {title}",
        _layout(title, f"<p>{content}</p><p>{warning}</p>"),
        f"{title}\n\n{content}\n\n{warning}",
    )


def _latex_inline(state, silent):
    for opening, closing in ((r"\(", r"\)"), (r"\[", r"\]"), ("$$", "$$"), ("$", "$")):
        if not state.src.startswith(opening, state.pos):
            continue
        end = state.src.find(closing, state.pos + len(opening), state.posMax)
        while end >= 0 and state.src[end - 1] == "\\":
            end = state.src.find(closing, end + len(closing), state.posMax)
        if end < 0:
            continue
        if not silent:
            token = state.push("latex_literal", "code", 0)
            token.content = state.src[state.pos : end + len(closing)]
        state.pos = end + len(closing)
        return True
    return False


def _latex_block(state, start, end, silent):
    begin = state.bMarks[start] + state.tShift[start]
    line = state.src[begin : state.eMarks[start]]
    for opening, closing in (("$$", "$$"), (r"\[", r"\]")):
        if not line.startswith(opening):
            continue
        for last in range(start, end):
            finish = state.eMarks[last]
            source = state.src[begin:finish]
            if len(source) <= len(opening) or not source.rstrip().endswith(closing):
                continue
            if silent:
                return True
            token = state.push("latex_literal", "code", 0)
            token.content = source
            token.map = [start, last + 1]
            state.line = last + 1
            return True
    return False


def _markdown(markdown: str, run_url: str) -> tuple[str, str]:
    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    parser.inline.ruler.before("escape", "latex_literal", _latex_inline)
    parser.block.ruler.before("fence", "latex_literal", _latex_block)
    parser.add_render_rule(
        "latex_literal",
        lambda renderer, tokens, idx, *_: (
            '<code style="white-space:pre-wrap">'
            + escape(tokens[idx].content)
            + "</code>"
        ),
    )

    def image(renderer, tokens, idx, options, env):
        alt = tokens[idx].content or "图片"
        return (
            f'<span>［图片：{escape(alt)}，请<a href="{escape(run_url, quote=True)}">'
            "进入运行记录查看</a>］</span>"
        )

    def link_open(renderer: RendererHTML, tokens, idx, options, env):
        token = tokens[idx]
        href = token.attrGet("href") or ""
        parts = urlsplit(href)
        # Citation/relative links belong to the authenticated run, never a
        # fabricated public source URL. MarkdownIt's validator rejects JS/data.
        if parts.scheme not in {"http", "https", "mailto"}:
            token.attrSet("href", run_url)
        token.attrSet("rel", "noreferrer noopener")
        return renderer.renderToken(tokens, idx, options, env)

    parser.add_render_rule("image", image)
    parser.add_render_rule("link_open", link_open)
    tokens = parser.parse(markdown)
    rendered = parser.renderer.render(tokens, parser.options, {})

    # Preserve source Markdown in the text alternative, but replace image URLs
    # using parsed source ranges, not remote downloads or regex HTML rewriting.
    def inline_text(children):
        result = []
        for token in children or []:
            if token.type == "image":
                result.append(
                    f"［图片：{token.content or '图片'}，请进入运行记录查看］"
                )
            elif token.type in {"softbreak", "hardbreak"}:
                result.append("\n")
            elif token.type == "link_open":
                href = token.attrGet("href") or ""
                if urlsplit(href).scheme in {"http", "https", "mailto"}:
                    result.append(f"（{href}）")
            elif token.type not in {"link_close"} and not token.type.endswith(
                ("_open", "_close")
            ):
                result.append(token.content)
        return "".join(result)

    text = []
    for token in tokens:
        if token.type == "inline":
            text.append(inline_text(token.children))
        elif token.type in {"fence", "code_block", "latex_literal"}:
            text.append(token.content)
    has_images = any(
        child.type == "image" for token in tokens for child in token.children or []
    )
    return rendered, "\n".join(text) if has_images else markdown


def schedule_result_email(
    *, name: str, markdown: str, status: str, run_url: str, error: str | None = None
) -> tuple[str, str, str]:
    parts = urlsplit(run_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("Run link must be an absolute HTTP(S) URL")
    title = "定时任务已完成" if status == "success" else "定时任务未完成"
    name = " ".join(name.split())[:120]
    prefix = f"<p><strong>{escape(name)}</strong></p>"
    link = (
        f'<p><a href="{escape(run_url, quote=True)}">查看本次运行记录</a>'
        "（需要登录）</p>"
    )
    notice = "邮件仅展示部分内容，请进入运行记录查看完整结果。"
    limit = max(4096, settings.mail_body_max_bytes)
    if status != "success":
        body = escape(error or "任务运行失败，请检查模型配置后重新运行。")
        return (
            f"Paper Agent · {title} · {name}",
            _layout(title, prefix + f"<p>{body}</p>" + link),
            f"{title}\n{name}\n\n"
            f"{error or '任务运行失败，请检查模型配置后重新运行。'}\n\n"
            f"查看本次运行记录：{run_url}",
        )
    # Bound rendering work before parsing untrusted model text. The final byte
    # budget includes layout, escaping and markup expansion, not just source.
    content = markdown[:limit]
    truncated = len(content) != len(markdown)
    while True:
        rendered, text = _markdown(content, run_url)
        warning = f"<p><strong>{notice}</strong></p>" if truncated else ""
        html = _layout(title, prefix + rendered + warning + link)
        if len(html.encode()) <= limit:
            break
        content = content[: max(0, len(content) // 2)]
        truncated = True
        if not content:
            html = _layout(title, prefix + f"<p>{notice}</p>" + link)
            text = ""
            break
    text_body = f"{title}\n{name}\n\n{text}\n\n"
    if truncated:
        text_body += notice + "\n\n"
    text_body += f"查看本次运行记录（需要登录）：{run_url}"
    return f"Paper Agent · {title} · {name}", html, text_body
