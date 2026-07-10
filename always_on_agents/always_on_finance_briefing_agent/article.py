"""Content pipeline: turn a rendered brief into a WeChat-ready markdown article.

The same curated filings feed two outputs: the subscriber brief (email/webhook)
and a public article for 公众号/知识星球 that doubles as a customer-acquisition
channel. Keeping this a pure function of the brief payload means the article can
never drift from what subscribers received.
"""

from __future__ import annotations

from typing import Any

try:
    from .scout import DISCLAIMER, filing_type_label
except ImportError:
    from scout import DISCLAIMER, filing_type_label


def render_wechat_article(brief_payload: dict[str, Any]) -> dict[str, str]:
    """Render a brief payload into a markdown article for 公众号 publishing."""

    filings = brief_payload.get("filings", [])
    date_label = brief_payload.get("subject", "").split(" - ")[-1]
    title = f"美股信披日报 | {date_label}：{len(filings)} 条值得看的公告"

    lines = [
        f"# {title}",
        "",
        "每天从 SEC EDGAR 数千条披露中，筛出真正影响股价逻辑的几条，"
        "并解释它为什么重要。以下是今天的高信号披露。",
        "",
    ]

    for index, filing in enumerate(filings, start=1):
        type_label = filing_type_label(filing["form_type"])
        lines.extend(
            [
                f"## {index}. {filing['company']}：{type_label}",
                "",
                filing["summary"],
                "",
                f"- 披露时间：{filing['filed_at']}",
                f"- [披露原文]({filing['url']})",
                "",
            ]
        )

    if not filings:
        lines.extend(["今日暂无高信号披露，市场安静的日子也值得记录。", ""])

    lines.extend(
        [
            "---",
            "",
            "以上内容由常驻信息简报 Agent 自动生成，人工复核后发布。",
            "想在盘前第一时间收到完整版简报，欢迎订阅。",
            "",
            f"> {DISCLAIMER}",
        ]
    )
    return {"title": title, "markdown": "\n".join(lines)}
