from always_on_finance_briefing_agent.article import render_wechat_article
from always_on_finance_briefing_agent.scout import DISCLAIMER, run_finance_scout


def test_render_wechat_article_produces_markdown_with_disclaimer():
    brief = run_finance_scout(live=False, top_n=3)

    article = render_wechat_article(brief)

    assert article["title"].startswith("美股信披日报 | ")
    assert "3 条值得看的公告" in article["title"]
    assert article["markdown"].startswith("# 美股信披日报")
    assert "## 1." in article["markdown"]
    assert DISCLAIMER in article["markdown"]


def test_render_wechat_article_handles_empty_brief():
    brief = run_finance_scout(live=False, top_n=3)
    brief["filings"] = []

    article = render_wechat_article(brief)

    assert "今日暂无高信号披露" in article["markdown"]
    assert DISCLAIMER in article["markdown"]
