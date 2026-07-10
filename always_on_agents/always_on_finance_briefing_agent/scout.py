"""SEC EDGAR filings briefing pipeline (美股信披简报).

The module is intentionally self-contained: it can run with deterministic sample
data for demos and tests, or fetch the latest SEC EDGAR filings feed directly
when live mode is enabled.

Compliance note: this pipeline produces factual summaries of public disclosures.
It must never emit buy/sell recommendations; a disclaimer is appended to every
rendered brief.
"""

from __future__ import annotations

import datetime as dt
import html
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Any
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")

ATOM_NS = "{http://www.w3.org/2005/Atom}"

EDGAR_LATEST_FILINGS_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=&company=&dateb=&owner=include&count=100&output=atom"
)

# SEC requires a User-Agent that identifies the requester with contact info.
DEFAULT_EDGAR_USER_AGENT = "FinanceBriefingAgent demo (set FINBRIEF_EDGAR_UA)"

DISCLAIMER = (
    "免责声明：本简报仅为公开信息披露的事实性摘要，不构成任何投资建议、"
    "证券推荐或收益承诺。据此操作，风险自担。"
)


@dataclass(frozen=True)
class FilingType:
    weight: int
    zh_name: str
    zh_hint: str


# Form types worth waking a reader up for, with Chinese explanations that make
# the brief readable without SEC background knowledge.
FILING_TYPES: dict[str, FilingType] = {
    "SC 13D": FilingType(
        weight=45,
        zh_name="举牌公告",
        zh_hint="持股超过 5% 且可能寻求影响公司经营，历史上常伴随收购或激进投资者行动。",
    ),
    "SC 13G": FilingType(
        weight=35,
        zh_name="被动持股公告",
        zh_hint="机构被动持股超过 5%，反映大资金建仓动向。",
    ),
    "8-K": FilingType(
        weight=30,
        zh_name="重大事项临时报告",
        zh_hint="并购、高管变动、业绩指引调整等须即时披露的重大事件。",
    ),
    "13F-HR": FilingType(
        weight=30,
        zh_name="机构季度持仓报告",
        zh_hint="管理规模超 1 亿美元的机构披露季度末持仓，可追踪知名基金调仓。",
    ),
    "S-1": FilingType(
        weight=28,
        zh_name="IPO 注册文件",
        zh_hint="公司启动上市流程，包含完整业务与财务信息。",
    ),
    "4": FilingType(
        weight=20,
        zh_name="内部人交易报告",
        zh_hint="董事、高管或大股东买卖自家公司股票，需在两个工作日内披露。",
    ),
    "10-K": FilingType(
        weight=15,
        zh_name="年度报告",
        zh_hint="经审计的年度财务报告，关注风险因素与管理层讨论章节。",
    ),
    "10-Q": FilingType(
        weight=12,
        zh_name="季度报告",
        zh_hint="未经审计的季度财务报告。",
    ),
}


@dataclass(frozen=True)
class Filing:
    form_type: str
    company: str
    cik: str
    url: str
    filed_at: str
    rank: int
    summary: str


@dataclass(frozen=True)
class Brief:
    generated_at: str
    watch_mode: str
    subject: str
    text: str
    html: str
    filings: list[Filing]
    next_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["filings"] = [asdict(filing) for filing in self.filings]
        return payload


def _watchlist() -> list[str]:
    raw = os.environ.get("FINBRIEF_WATCHLIST", "")
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _watchlist_hits(company: str) -> list[str]:
    lowered = company.lower()
    return [item for item in _watchlist() if item in lowered]


def _normalize_form_type(form_type: str) -> str:
    normalized = form_type.strip().upper()
    # Amendments (e.g. "8-K/A", "SC 13D/A") inherit the base form's meaning.
    return normalized.removesuffix("/A")


def _filing_type_info(form_type: str) -> FilingType | None:
    return FILING_TYPES.get(_normalize_form_type(form_type))


def filing_type_label(form_type: str) -> str:
    """Human-readable Chinese label for a form type, e.g. "举牌公告（SC 13D）"."""

    info = _filing_type_info(form_type)
    return f"{info.zh_name}（{form_type}）" if info else form_type


def _score_filing(filing: Filing) -> float:
    info = _filing_type_info(filing.form_type)
    type_score = info.weight if info else 0
    watchlist_score = 40 if _watchlist_hits(filing.company) else 0
    freshness_score = max(0, 30 - filing.rank)
    return type_score + watchlist_score + freshness_score


def _summarize_filing(form_type: str, company: str) -> str:
    info = _filing_type_info(form_type)
    if info is None:
        return f"{company} 提交了 {form_type} 文件，属于常规披露，可低优先级跟进。"
    watch_note = ""
    if _watchlist_hits(company):
        watch_note = "该公司在你的关注列表中，建议优先阅读原文。"
    return f"{company} 提交了{info.zh_name}（{form_type}）。{info.zh_hint}{watch_note}"


def sample_filings() -> list[Filing]:
    """Deterministic demo data used when live EDGAR mode is disabled."""

    rows = [
        ("SC 13D", "EXAMPLE ACTIVIST FUND LP", "0001111111", "2026-07-10T08:31:00-04:00"),
        ("8-K", "ACME SEMICONDUCTOR CORP", "0002222222", "2026-07-10T08:05:00-04:00"),
        ("13F-HR", "WELL-KNOWN CAPITAL MANAGEMENT", "0003333333", "2026-07-10T07:58:00-04:00"),
        ("4", "ACME SEMICONDUCTOR CORP", "0002222222", "2026-07-10T07:40:00-04:00"),
        ("S-1", "NEXTGEN ROBOTICS INC", "0004444444", "2026-07-10T07:12:00-04:00"),
    ]
    filings = []
    for rank, (form_type, company, cik, filed_at) in enumerate(rows, start=1):
        filings.append(
            Filing(
                form_type=form_type,
                company=company,
                cik=cik,
                url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
                filed_at=filed_at,
                rank=rank,
                summary=_summarize_filing(form_type, company),
            )
        )
    return filings


_ENTRY_TITLE_PATTERN = re.compile(
    r"^(?P<form>.+?)\s+-\s+(?P<company>.+?)\s+\((?P<cik>\d{10})\)"
)


def parse_edgar_atom(markup: str) -> list[Filing]:
    """Parse the EDGAR "latest filings" atom feed into Filing records."""

    root = ET.fromstring(markup)
    filings: list[Filing] = []
    for entry in root.iter(f"{ATOM_NS}entry"):
        title = (entry.findtext(f"{ATOM_NS}title") or "").strip()
        match = _ENTRY_TITLE_PATTERN.match(title)
        if not match:
            continue
        form_type = match.group("form").strip()
        company = match.group("company").strip()
        link = entry.find(f"{ATOM_NS}link")
        url = link.get("href", "") if link is not None else ""
        rank = len(filings) + 1
        filings.append(
            Filing(
                form_type=form_type,
                company=company,
                cik=match.group("cik"),
                url=url,
                filed_at=(entry.findtext(f"{ATOM_NS}updated") or "").strip(),
                rank=rank,
                summary=_summarize_filing(form_type, company),
            )
        )
    return filings


def fetch_edgar_latest_filings(timeout_seconds: int = 20) -> list[Filing]:
    """Fetch and parse the current EDGAR latest-filings feed."""

    request = urllib.request.Request(
        EDGAR_LATEST_FILINGS_URL,
        headers={
            "User-Agent": os.environ.get("FINBRIEF_EDGAR_UA", DEFAULT_EDGAR_USER_AGENT)
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            markup = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not fetch SEC EDGAR feed: {exc}") from exc
    return parse_edgar_atom(markup)


def curate_filings(
    *,
    live: bool | None = None,
    top_n: int = 5,
) -> list[Filing]:
    """Select the highest-signal filings for the daily brief."""

    if live is None:
        live = os.environ.get("FINBRIEF_LIVE_EDGAR", "").lower() in {"1", "true", "yes"}

    filings = fetch_edgar_latest_filings() if live else sample_filings()
    candidates = [
        filing
        for filing in filings
        if _filing_type_info(filing.form_type) or _watchlist_hits(filing.company)
    ]
    return sorted(candidates, key=_score_filing, reverse=True)[:top_n]


def render_brief(
    filings: list[Filing],
    *,
    watch_mode: str = "sample",
    now: dt.datetime | None = None,
) -> Brief:
    """Render the daily filings brief in Chinese text and HTML."""

    now = now or dt.datetime.now(BEIJING)
    date_label = now.strftime("%Y-%m-%d")
    subject = f"美股信披简报 - {date_label}"
    next_actions = [
        "优先打开举牌（SC 13D）和 8-K 原文，确认事件类别与涉及金额。",
        "将关注列表公司的披露转发到你的订阅群或简报正文。",
        "定时运行时，确认渲染成功后再触发投递。",
    ]

    text_lines = [
        f"美股信披简报（{date_label}）",
        f"生成时间: {now.isoformat(timespec='seconds')}",
        f"数据模式: {watch_mode}",
        "",
        "今日高信号披露:",
    ]
    html_lines = [
        f"<h2>美股信披简报（{html.escape(date_label)}）</h2>",
        f"<p><strong>生成时间:</strong> {html.escape(now.isoformat(timespec='seconds'))}<br>",
        f"<strong>数据模式:</strong> {html.escape(watch_mode)}</p>",
        "<ol>",
    ]

    for index, filing in enumerate(filings, start=1):
        type_label = filing_type_label(filing.form_type)
        signal = f"类型 {type_label} · 披露时间 {filing.filed_at}"
        text_lines.extend(
            [
                f"{index}. {filing.company} - {type_label}",
                f"   为何重要: {filing.summary}",
                f"   信号: {signal}",
                f"   原文: {filing.url}",
                "",
            ]
        )
        html_lines.extend(
            [
                "<li>",
                f"<strong>{html.escape(filing.company)} - {html.escape(type_label)}</strong>",
                f"<p>{html.escape(filing.summary)}</p>",
                f"<p><strong>信号:</strong> {html.escape(signal)}<br>",
                f'<a href="{html.escape(filing.url)}">披露原文</a></p>',
                "</li>",
            ]
        )

    if not filings:
        text_lines.append("今日暂无高信号披露。")
        html_lines.append("<li>今日暂无高信号披露。</li>")

    text_lines.extend(["下一步:", *[f"- {action}" for action in next_actions]])
    text_lines.extend(["", DISCLAIMER])
    html_lines.extend(
        [
            "</ol>",
            "<h3>下一步</h3>",
            "<ul>",
            *[f"<li>{html.escape(action)}</li>" for action in next_actions],
            "</ul>",
            f"<p><em>{html.escape(DISCLAIMER)}</em></p>",
        ]
    )
    return Brief(
        generated_at=now.isoformat(timespec="seconds"),
        watch_mode=watch_mode,
        subject=subject,
        text="\n".join(text_lines),
        html="\n".join(html_lines),
        filings=filings,
        next_actions=next_actions,
    )


def run_finance_scout(*, live: bool | None = None, top_n: int = 5) -> dict[str, Any]:
    """Run the complete EDGAR filings briefing pipeline."""

    filings = curate_filings(live=live, top_n=top_n)
    inferred_live = live
    if inferred_live is None:
        inferred_live = os.environ.get("FINBRIEF_LIVE_EDGAR", "").lower() in {
            "1",
            "true",
            "yes",
        }
    brief = render_brief(filings, watch_mode="live_edgar" if inferred_live else "sample")
    payload = brief.to_dict()
    payload["delivery_note"] = (
        "This demo renders the EDGAR filings digest. Wire the returned text/html "
        "to your email, WeCom, Feishu, or Telegram sender when you deploy it."
    )
    return payload
