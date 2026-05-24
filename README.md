<img src="assets/logo.png" alt="Jugni AI logo" width="260">

# Jugni AI

**A Telegram food accountability bot for teams.**

[How it works](#how-it-works) · [Setup](#setup) · [Daily summary](#daily-summary) · [Roadmap](#what-comes-next)

---

The first problem was boring and real: group accountability dies when tracking takes work.

Someone eats lunch, forgets to log it, and remembers at 11:47 pm with the confidence of a tax notice. After 3 days, the group is back to vibes.

Jugni makes the group chat do the work.

You post a food photo. The bot replies with the dish, calories, confidence, your running total for the day, and 1 useful tip.

```text
@vraj, 2 methi theplas with masala chai
360 kcal, high confidence, today: 360 kcal
Light on protein for breakfast. Add a boiled egg or a katori curd.
```

Every night, the team gets ranked.

The summary pulls everyone who posted food that day, totals their calories, checks meal quality, and ranks the healthiest eaters in the group. It adds a short note for each person so the leaderboard has context instead of pure calorie math.

## How it works

1. Add the bot to your Telegram group.
2. People post meal photos in the group.
3. The bot analyses each photo with OpenAI vision.
4. Redis stores the meal, calories, sender, time, and tip.
5. `/summary` posts the daily team ranking.

That loop is the product.

The bot is built for Indian food, especially Gujarati home food, but it handles regular restaurant and Western meals too.

## What the bot posts

For every food photo:

- dish name
- estimated calories
- confidence level
- sender's total calories for the day
- 1 practical diet tip

For the daily summary:

- ranked team members
- total calories per person
- meal timeline
- health score out of 10
- short nutrition note per person

Calories are photo estimates. Good enough for accountability, weak evidence for anything clinical.

## What comes next

I want the bot to get more personal without making the chat annoying.

Streaks are first. If you post meals 5 days in a row, the bot should know. If you disappear for 2 days, the group should see that too.

Weekly analysis comes after that. The bot can spot patterns a single day misses: low protein breakfasts, late dinners, too many liquid calories, or the famous "healthy Monday, chaos by Thursday" graph.

Then daily recommendations. Once the bot has your past meals, goals, and weight history, it can suggest today's meals from your history and goals.

There should also be a preference page.

Each user should be able to save regular recipes, default portions, diet rules, goal weight, current weight, and calorie target. If your dinner is usually 2 rotis, dal, sabzi, and chaas, you should set that once. The bot should stop asking the same question like it has short-term memory loss.

## Setup

You need 3 things:

- a Telegram bot from BotFather
- group access for that bot
- the sample env values configured

Create the bot in Telegram:

1. Open `@BotFather`.
2. Run `/newbot`.
3. Copy the bot token.
4. Run `/setprivacy`.
5. Disable privacy mode for this bot so it can read group food photos.
6. Add the bot to your group.

Then copy the env file:

```bash
cp .env.example .env
```

Set these values:

```bash
TELEGRAM_BOT_TOKEN=<your-telegram-bot-token>
TELEGRAM_WEBHOOK_SECRET=make-this-long
TELEGRAM_GROUP_CHAT_ID=-1001234567890
OPENAI_API_KEY=<your-openai-api-key>
OPENAI_MODEL=gpt-4.1-mini
REDIS_URL=redis://localhost:6379/0
APP_TIMEZONE=Asia/Kolkata
ADMIN_API_SECRET=another-long-secret
```

`TELEGRAM_WEBHOOK_SECRET` protects the Telegram webhook.

`ADMIN_API_SECRET` protects the manual API routes: `/api/upload`, `/api/summary`, and `/api/backfill`. When it is set, send it as `X-Admin-API-Secret`.

Keep `.env` private. Commit `.env.example`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d redis
food-summary-api
```

The app starts on `http://localhost:8000`.

Useful routes:

- `GET /api/health`
- `POST /api/telegram/webhook`
- `POST /api/upload`
- `GET /api/summary`
- `POST /api/backfill`

## Local upload

Use this when you want to test without sending a Telegram photo.

```bash
curl -X POST http://localhost:8000/api/upload \
  -H "X-Admin-API-Secret: another-long-secret" \
  -F image=@./plate.jpg \
  -F user_label=@vraj \
  -F caption="2 theplas with chai"
```

`caption` helps the model. Use it for portion clues, hidden ingredients, or the thing the photo makes ambiguous.

## Daily summary

In the group:

```text
/summary
```

From HTTP:

```bash
curl -H "X-Admin-API-Secret: another-long-secret" \
  'http://localhost:8000/api/summary?date=2026-05-20&send=true'
```

The summary ranks the team for that local day.

## Finding the group chat id

Telegram group chat ids are negative numbers. Supergroups usually look like `-1001234567890`.

Add the bot to the group, send any message, then check server logs for:

```text
webhook chat_id=-1001234567890
```

Copy that value into `TELEGRAM_GROUP_CHAT_ID`.

## Webhook mode

Point Telegram at your deployed URL:

```bash
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -d "url=https://your-domain.com/api/telegram/webhook" \
  -d "secret_token=$TELEGRAM_WEBHOOK_SECRET"
```

For local testing, you can use polling:

```bash
TELEGRAM_POLLING_ENABLED=true
```

Use webhook mode in production.

## Project map

```text
api/                 FastAPI routes and app wiring
controllers/         top-level bot flows
domain/              typed dataclasses
image_analyser/      food photo prompt, parser, estimator
summary_analyser/    daily ranking prompt, parser, summarizer
presenters/          Telegram message formatting
storage/             Redis repository
telegram/            Telegram API wrapper and update parsing
users/               per-user daily breakdown
core/                settings, dates, logging
```

The code is intentionally small. Most files do 1 thing and hand off typed objects instead of loose dicts.

## Notes before publishing

- `.env` is ignored by Git. Check it anyway before pushing.
- `__pycache__` files are ignored by Git. Delete them before uploading a zip manually.
- Set `TELEGRAM_WEBHOOK_SECRET` on any public webhook.
- Set `ADMIN_API_SECRET` before exposing the manual HTTP routes.
- Redis stores meal history. Treat it like user data.

## License

Add your license before publishing.
