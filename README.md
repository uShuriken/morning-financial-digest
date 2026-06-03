# Morning Financial News Email Digest

This project sends a short daily business and markets email without needing Codex open.

It uses:
- RSS feeds for headline collection
- source-specific business and tech feeds, including Reuters, CNBC, New York Times, RNZ, interest.co.nz, and The Verge
- `yfinance` for a quick market snapshot
- Gmail SMTP to send the email
- GitHub Actions as the free cloud scheduler
- OpenAI optionally, to rewrite the report in simple language

## What Changed

The summary prompt now tells the model to write for a smart 18-year-old:
- simpler wording
- less finance jargon
- short bullets
- plain-English bottom line
- source labels and short article summaries in each section

If OpenAI is unavailable, the fallback email is also written more simply.
It now also keeps the source name on each bullet and uses each RSS item's summary when available.

## Free Cloud Setup

GitHub Actions is the easiest free option for this repo.

How it works:
1. GitHub runs the workflow on a schedule.
2. The script checks Auckland time.
3. It only sends the email during the 7:00 AM window.
4. The email goes out through Gmail using an App Password.

This repo already includes the workflow at [.github/workflows/morning-digest.yml](C:/Users/shuri/Documents/Codex/2026-05-26/i-want-to-set-up-an/.github/workflows/morning-digest.yml).

## What You Need

Add these GitHub Actions secrets:
- `EMAIL_TO`
- `EMAIL_FROM`
- `GMAIL_APP_PASSWORD`
- `OPENAI_API_KEY` (recommended)

Add these GitHub Actions variables:
- `OPENAI_MODEL` (optional, defaults to `gpt-4.1-mini`)
- `FORCE_SEND` (leave blank for normal use, set to `true` only for testing)

## Step-By-Step Setup

1. Create a GitHub repo and push this project to it.
2. In the Gmail account that will send the digest:
   enable 2-step verification.
3. Create a Gmail App Password.
4. In GitHub, open:
   `Settings -> Secrets and variables -> Actions`
5. Add the secrets listed above.
6. Open the `Actions` tab and enable workflows if GitHub asks.
7. Run the workflow once with `workflow_dispatch` to test it.
8. Check your inbox for the test email.

## Testing Without Waiting For 7:00 AM

For a manual test, set this extra Actions variable or local env var:
- `FORCE_SEND=true`

That bypasses the Auckland time check so we can test immediately.

After testing, remove it so the digest only sends on schedule.

## Local Run

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
set FORCE_SEND=true
python digest.py
```

PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FORCE_SEND = "true"
python digest.py
```

## Notes

- GitHub Actions cron timing can drift by a few minutes.
- Auckland daylight saving is handled by running the workflow twice in UTC and checking local time inside the script.
- If you want stronger source quality later, we can swap RSS feeds for paid APIs.
- RSS feeds only expose the headline, link, and whatever short summary the publisher includes. This keeps the setup free, but it will not read full paywalled articles.
