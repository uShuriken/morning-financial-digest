from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from digest import format_article_line, shorten_summary


def test_digest_script_exists() -> None:
    assert (PROJECT_ROOT / "digest.py").exists()


def test_shorten_summary_strips_html() -> None:
    summary = shorten_summary("<p>Stocks jumped after the Fed update.</p><p>More detail.</p>")
    assert summary == "Stocks jumped after the Fed update."


def test_format_article_line_includes_source_and_summary() -> None:
    article = {
        "source": "NYT Business",
        "title": "Stocks rally on rate hopes",
        "summary": "Investors reacted to softer inflation data.",
        "link": "https://example.com/story",
    }

    line = format_article_line(article)

    assert line == "- NYT Business: Stocks rally on rate hopes. Investors reacted to softer inflation data."
