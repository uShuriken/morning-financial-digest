import html
import os
import re
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any, TypedDict

import pytz

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


AUCKLAND_TZ = pytz.timezone("Pacific/Auckland")


class FeedConfig(TypedDict):
    source: str
    url: str


class Article(TypedDict):
    source: str
    title: str
    summary: str
    link: str


FEEDS: dict[str, list[FeedConfig]] = {
    "Global markets": [
        {"source": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews"},
        {"source": "CNBC Markets", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
        {"source": "NYT Business", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"},
    ],
    "U.S. markets": [
        {"source": "Reuters U.S.", "url": "https://feeds.reuters.com/reuters/domesticNews"},
        {"source": "CNBC Economy", "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html"},
        {"source": "NYT DealBook", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Dealbook.xml"},
    ],
    "New Zealand": [
        {"source": "RNZ Business", "url": "https://www.rnz.co.nz/rss/business.xml"},
        {"source": "interest.co.nz", "url": "https://www.interest.co.nz/rss.xml"},
    ],
    "Technology": [
        {"source": "Reuters Tech", "url": "https://feeds.reuters.com/reuters/technologyNews"},
        {"source": "NYT Technology", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"},
        {"source": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
    ],
}

TICKERS = {
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "Dow": "^DJI",
    "NZD/USD": "NZDUSD=X",
    "Brent crude": "BZ=F",
    "Gold": "GC=F",
}


def within_send_window() -> bool:
    if os.getenv("FORCE_SEND", "").lower() in {"1", "true", "yes"}:
        return True

    now_local = datetime.now(AUCKLAND_TZ)
    return now_local.hour == 7 and now_local.minute <= 40


def strip_html(raw_text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def shorten_summary(raw_text: str, max_chars: int = 160) -> str:
    cleaned = strip_html(raw_text)
    if not cleaned:
        return ""

    first_sentence = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0].strip()
    summary = first_sentence or cleaned

    if len(summary) <= max_chars:
        return summary

    shortened = summary[: max_chars - 3].rsplit(" ", 1)[0].strip()
    return f"{shortened}..." if shortened else f"{summary[: max_chars - 3]}..."


def entry_summary(entry: dict[str, Any]) -> str:
    candidates = [
        entry.get("summary", ""),
        entry.get("description", ""),
    ]

    for candidate in candidates:
        summary = shorten_summary(candidate)
        if summary:
            return summary
    return ""


def fetch_articles(limit_per_source: int = 2, limit_per_section: int = 6) -> dict[str, list[Article]]:
    import feedparser

    articles_by_section: dict[str, list[Article]] = {}

    for section, feeds in FEEDS.items():
        section_articles: list[Article] = []
        seen_titles = set()

        for feed_config in feeds:
            feed = feedparser.parse(feed_config["url"])
            source_count = 0

            for entry in feed.entries:
                title = strip_html(entry.get("title", ""))
                if not title:
                    continue

                normalized_title = title.casefold()
                if normalized_title in seen_titles:
                    continue

                summary = entry_summary(entry)
                section_articles.append(
                    {
                        "source": feed_config["source"],
                        "title": title,
                        "summary": summary,
                        "link": entry.get("link", "").strip(),
                    }
                )
                seen_titles.add(normalized_title)
                source_count += 1

                if source_count >= limit_per_source or len(section_articles) >= limit_per_section:
                    break

            if len(section_articles) >= limit_per_section:
                break

        articles_by_section[section] = section_articles

    return articles_by_section


def fetch_market_snapshot() -> list[str]:
    import yfinance as yf

    lines = []
    for label, ticker in TICKERS.items():
        try:
            history = yf.Ticker(ticker).history(period="2d", interval="1d")
            if len(history) < 2:
                continue
            prev_close = float(history["Close"].iloc[-2])
            last_close = float(history["Close"].iloc[-1])
            move_pct = ((last_close - prev_close) / prev_close) * 100
            lines.append(f"- {label}: {last_close:.2f} ({move_pct:+.2f}%)")
        except Exception:
            continue
    return lines


def format_article_line(article: Article) -> str:
    if article["summary"]:
        return f"- {article['source']}: {article['title']}. {article['summary']}"
    return f"- {article['source']}: {article['title']}"


def fallback_email_body(articles: dict[str, list[Article]], market_lines: list[str]) -> tuple[str, str]:
    local_now = datetime.now(AUCKLAND_TZ)
    subject = f"Morning Financial Digest - {local_now.strftime('%a %d %b %Y')}"

    body_lines = [
        "Good morning. Here is your simple financial news update for today.",
        "",
        "MARKET SNAPSHOT",
        "",
    ]
    body_lines.extend(line for item in market_lines for line in (item, ""))

    for section, items in articles.items():
        body_lines.append(section.upper())
        body_lines.append("")
        if items:
            for item in items:
                body_lines.append(format_article_line(item))
                body_lines.append("")
        else:
            body_lines.append("- No major items came through from the news feeds.")
            body_lines.append("")

    body_lines.extend(
        [
            "WHAT TO WATCH NEXT",
            "",
            "- Any central-bank update that could change interest-rate expectations.",
            "",
            "- Big tech earnings, especially anything tied to AI spending.",
            "",
            "- Oil prices, the New Zealand dollar, and any fresh global risk headlines.",
            "",
            "BOTTOM LINE",
            "",
            "- This version pulls named sources directly, so you can see who is driving each story each morning.",
        ]
    )
    return subject, "\n".join(body_lines)


def llm_email_body(articles: dict[str, list[Article]], market_lines: list[str]) -> tuple[str, str] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return None

    client = OpenAI(api_key=api_key)
    local_now = datetime.now(AUCKLAND_TZ)

    prompt = f"""
Write a short morning financial news email for mobile reading.

Requirements:
- Add a blank line between every bullet point.
- Use these sections exactly: GLOBAL MARKETS, U.S. MARKETS, NEW ZEALAND, TECHNOLOGY, WHAT TO WATCH NEXT.
- Write for a smart 18-year-old.
- Use simple, everyday language.
- Avoid jargon. If you need a finance term, explain it in plain English in the same bullet.
- Start each story bullet with the source name.
- Use the article summaries provided instead of inventing extra detail.
- Keep each bullet concise and easy to scan on a phone.
- Focus on market-moving items, central banks, earnings, corporate actions, commodities, currencies, and major risks.
- Add a one-sentence bottom line in plain English.
- Return JSON with keys: subject, body.

Date in Auckland: {local_now.strftime("%Y-%m-%d %H:%M %Z")}

Market snapshot:
{chr(10).join(market_lines)}

Articles by section:
{articles}
""".strip()

    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=prompt,
    )
    text = response.output_text

    if '"subject"' not in text or '"body"' not in text:
        return None

    import json

    try:
        parsed = json.loads(text)
        return parsed["subject"], parsed["body"]
    except Exception:
        return None


def send_email(subject: str, body: str) -> None:
    sender = os.environ["EMAIL_FROM"]
    recipient = os.environ["EMAIL_TO"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("Morning Digest", sender))
    msg["To"] = recipient

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.sendmail(sender, [recipient], msg.as_string())


def main() -> None:
    now_local = datetime.now(AUCKLAND_TZ)
    print(f"Current Auckland time: {now_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    if not within_send_window():
        print("Outside the 7:00 AM Auckland send window; skipping.")
        return

    articles = fetch_articles()
    market_lines = fetch_market_snapshot()
    email = llm_email_body(articles, market_lines)
    if email is None:
        email = fallback_email_body(articles, market_lines)
    subject, body = email
    send_email(subject, body)
    print("Digest sent.")


if __name__ == "__main__":
    main()
