"""One-shot daily run for external schedulers such as GitHub Actions or cron.

Runs the full pipeline once (fetch -> curate -> render brief + article ->
optional delivery) and prints the brief to stdout. Delivery reuses the same
opt-in FINBRIEF_* env vars as scheduler_api; with nothing configured the run
still succeeds so the brief can be read from the job log. On GitHub Actions
the article markdown is also appended to the job summary.
"""

from __future__ import annotations

import json
import os
import sys

try:
    from .article import render_wechat_article
    from .delivery import send_brief
    from .scout import run_finance_scout
except ImportError:
    from article import render_wechat_article
    from delivery import send_brief
    from scout import run_finance_scout


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes"}


def _env_top_n(default: int = 5) -> int:
    try:
        top_n = int(os.environ.get("FINBRIEF_TOP_N", default))
    except ValueError:
        return default
    return max(1, min(top_n, 10))


def main() -> int:
    live = _env_bool("FINBRIEF_LIVE_EDGAR", True)
    dry_run = _env_bool("FINBRIEF_DRY_RUN", False)

    brief = run_finance_scout(live=live, top_n=_env_top_n())
    brief["article"] = render_wechat_article(brief)

    print(brief["text"])

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(brief["article"]["markdown"] + "\n")

    if dry_run:
        print("\n[dry_run] delivery skipped.")
        return 0

    delivery = send_brief(brief)
    print("\ndelivery: " + json.dumps(delivery, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
