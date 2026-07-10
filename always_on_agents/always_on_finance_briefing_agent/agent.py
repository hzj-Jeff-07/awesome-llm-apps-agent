"""FinanceScout: an always-on SEC EDGAR filings briefing agent."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from .article import render_wechat_article
from .scout import run_finance_scout


def preview_finance_brief(top_n: int = 5) -> dict:
    """Preview the SEC EDGAR filings brief.

    Args:
        top_n: Number of filings to include in the brief.

    Returns:
        A rendered daily brief with ranked filings, signal, and next actions.
    """

    return run_finance_scout(live=None, top_n=top_n)


def preview_wechat_article(top_n: int = 5) -> dict:
    """Preview the WeChat-ready markdown article generated from today's brief.

    Args:
        top_n: Number of filings to include in the article.

    Returns:
        The article title and markdown body.
    """

    return render_wechat_article(run_finance_scout(live=None, top_n=top_n))


root_agent = LlmAgent(
    name="finance_scout",
    model="gemini-3-flash-preview",
    description=(
        "Always-on SEC EDGAR briefing agent that watches for high-signal "
        "filings (SC 13D, 8-K, 13F-HR, Form 4, S-1) and renders a Chinese "
        "daily brief plus a WeChat-ready article."
    ),
    instruction="""
你是 FinanceScout，一个常驻的美股信息披露简报 Agent，服务中文读者。

你的工作方式：
- 只筛选高信号的 SEC 披露（举牌、8-K 重大事项、机构持仓、内部人交易、IPO）。
- 用中文解释每条披露为什么重要，面向没有 SEC 背景知识的读者。
- 只做事实性摘要，绝对不给出买入/卖出建议、目标价或收益预测。
- 用户要今日简报、日报、盘前简报时，调用 preview_finance_brief。
- 用户要公众号文章、推文草稿时，调用 preview_wechat_article。
- 回答保持简洁、可执行：排序后的披露、信号说明、下一步动作。

工具返回的 text/html/markdown 可直接交给邮件、企业微信、飞书或公众号发布流程。
""",
    tools=[preview_finance_brief, preview_wechat_article],
)
