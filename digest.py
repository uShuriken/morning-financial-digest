import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.utils import formataddr

import feedparser
import pytz
import yfinance as yf

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


AUCKLAND_TZ = pytz.timezone("Pacific/Auckland")

FEEDS = {
    "Global markets": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://feeds.reuters.com/news/wealth",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    ],
    "U.S. markets": [
        "https://feeds.reuters.com/reuters/domesticNews",
        "https://www.cnbc.com/id/15839135/device/rss/rss.html",
    ],
    "New Zealand": [
        "https://www.rnz.co.nz/rss/business.xml",
        "https://www.interest.co.nz/rss.xml",
    ],
    "Technology": [
        "https://feeds.reuters.com/reuters/technologyNews",
        "https://www.theverge.com/rss/index.xml",
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
    return now_local.hour == 7 and now_local.minute <= 20


def fetch_headlines(limit_per_section: int = 5) -> dict[str, list[str]]:
    headlines = {}
    for section, urls in FEEDS.items():
        items = []
        seen = set()
        for url in urls:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                items.append(title)
                if len(items) >= limit_per_section:
                    break
            if len(items) >= limit_per_section:
                break
        headlines[section] = items
    return headlines


def fetch_market_snapshot() -> list[str]:
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


def fallback_email_body(headlines: dict[str, list[str]], market_lines: list[str]) -> tuple[str, str]:
    local_now = datetime.now(AUCKLAND_TZ)
    subject = f"Morning Financial Digest - {local_now.strftime('%a %d %b %Y')}"

    body_lines = [
        "Good morning. Here is your simple financial news update for today.",
        "",
        "MARKET SNAPSHOT",
        "",
    ]
    body_lines.extend(line for item in market_lines for line in (item, ""))

    for section, items in headlines.items():
        body_lines.append(section.upper())
        body_lines.append("")
        if items:
            for item in items:
                body_lines.append(f"- {item}")
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
            "- Markets usually move most when rates, oil, and big tech all shift at the same time.",
        ]
    )
    return subject, "\n".join(body_lines)


def llm_email_body(headlines: dict[str, list[str]], market_lines: list[str]) -> tuple[str, str] | None:
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
- Keep each bullet concise and easy to scan on a phone.
- Focus on market-moving items, central banks, earnings, corporate actions, commodities, currencies, and major risks.
- Add a one-sentence bottom line in plain English.
- Return JSON with keys: subject, body.

Date in Auckland: {local_now.strftime("%Y-%m-%d %H:%M %Z")}

Market snapshot:
{chr(10).join(market_lines)}

Headlines by section:
{headlines}
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
    if not within_send_window():
        print("Outside the 7:00 AM Auckland send window; skipping.")
        return

    headlines = fetch_headlines()
    market_lines = fetch_market_snapshot()
    email = llm_email_body(headlines, market_lines)
    if email is None:
        email = fallback_email_body(headlines, market_lines)
    subject, body = email
    send_email(subject, body)
    print("Digest sent.")


if __name__ == "__main__":
    main()
