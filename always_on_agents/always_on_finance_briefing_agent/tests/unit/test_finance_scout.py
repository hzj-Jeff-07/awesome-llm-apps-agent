import datetime as dt

from always_on_finance_briefing_agent.scout import (
    BEIJING,
    DISCLAIMER,
    curate_filings,
    parse_edgar_atom,
    render_brief,
    run_finance_scout,
)

SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Latest Filings - Thu, 10 Jul 2026 12:00:00 EDT</title>
  <entry>
    <title>8-K - ACME SEMICONDUCTOR CORP (0002222222) (Filer)</title>
    <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/2222222/000222222226000001-index.htm"/>
    <updated>2026-07-10T08:05:00-04:00</updated>
  </entry>
  <entry>
    <title>SC 13D - EXAMPLE ACTIVIST FUND LP (0001111111) (Filed by)</title>
    <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/1111111/000111111126000001-index.htm"/>
    <updated>2026-07-10T08:31:00-04:00</updated>
  </entry>
  <entry>
    <title>424B2 - BIG BANK CORP (0005555555) (Filer)</title>
    <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/5555555/000555555526000001-index.htm"/>
    <updated>2026-07-10T08:02:00-04:00</updated>
  </entry>
</feed>
"""


def test_parse_edgar_atom_extracts_filings():
    filings = parse_edgar_atom(SAMPLE_ATOM)

    assert len(filings) == 3
    assert filings[0].form_type == "8-K"
    assert filings[0].company == "ACME SEMICONDUCTOR CORP"
    assert filings[0].cik == "0002222222"
    assert filings[0].url.startswith("https://www.sec.gov/Archives/")
    assert filings[1].filed_at == "2026-07-10T08:31:00-04:00"


def test_curate_filings_ranks_activist_stakes_above_routine_filings():
    filings = curate_filings(live=False, top_n=5)

    assert filings
    assert filings[0].form_type == "SC 13D"
    form_types = {filing.form_type for filing in filings}
    assert "8-K" in form_types


def test_curate_filings_watchlist_boost(monkeypatch):
    monkeypatch.setenv("FINBRIEF_WATCHLIST", "nextgen robotics")

    filings = curate_filings(live=False, top_n=2)

    assert any("NEXTGEN ROBOTICS" in filing.company for filing in filings)


def test_render_brief_includes_disclaimer_and_chinese_labels():
    filings = curate_filings(live=False, top_n=2)
    now = dt.datetime(2026, 7, 10, 9, 0, tzinfo=BEIJING)

    brief = render_brief(filings, watch_mode="sample", now=now)

    assert brief.subject == "美股信披简报 - 2026-07-10"
    assert DISCLAIMER in brief.text
    assert DISCLAIMER in brief.html
    assert "举牌公告" in brief.text
    assert "<ol>" in brief.html
    assert len(brief.next_actions) == 3


def test_run_finance_scout_returns_delivery_handoff_payload():
    payload = run_finance_scout(live=False, top_n=1)

    assert payload["watch_mode"] == "sample"
    assert payload["filings"]
    assert "text" in payload
    assert "html" in payload
    assert "delivery_note" in payload
