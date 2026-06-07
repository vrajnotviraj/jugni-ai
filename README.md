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
- a streak line on the first meal of the day ("🔥 5-day streak")

For the daily summary:

- ranked team members
- total calories per person
- meal timeline
- health score out of 10
- short nutrition note per person
- each person's current logging streak (🔥)

Calories are photo estimates. Good enough for accountability, weak evidence for anything clinical.

## What comes next

I want the bot to get more personal without making the chat annoying.

Streaks shipped first (see [Streaks](#streaks)): the bot now knows when you post several days in a row, and the group sees it too.

Weekly analysis comes after that. The bot can spot patterns a single day misses: low protein breakfasts, late dinners, too many liquid calories, or the famous "healthy Monday, chaos by Thursday" graph.

Meal recommendations shipped too (see [Meal recommendations](#meal-recommendations-recommend)): `/recommend` suggests your next meal from today's gaps and your goal.

There should also be a preference page.

Each user should be able to save regular recipes, default portions, diet rules, goal weight, current weight, and calorie target. If your dinner is usually 2 rotis, dal, sabzi, and chaas, you should set that once. The bot should stop asking the same question like it has short-term memory loss.

## Personal profile (DM)

Each person can keep a private profile by messaging the bot directly (a 1:1 DM,
never in the group). Profiles are global per person, keyed by Telegram user id,
and shared across every group. Commands appear automatically in the Telegram
command menu

| Command          | What it does                                                                                       | Example                                              |
| ---------------- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| `/profile`       | View your profile, or set it in plain words (an LLM extracts height, weight, age, sex, activity, goal, diet, timezone) | `/profile 5ft9, 72 kg, 31M, gym 4x a week, vegetarian, want to lose fat` |
| `/context`       | Bare: list your saved context notes. With text: an LLM folds it into your notes (add, change, or remove), keeping them concise and deduped | `/context my chundo has no sugar`                    |
| `/recommend`     | Suggest your next meal from your day and goal (see [Meal recommendations](#meal-recommendations-recommend)) | `/recommend light dinner`                            |
| `/deleteprofile` | Delete your profile, context, and weight history                                                   | `/deleteprofile`                                     |

Notes:

- **Privacy.** Profile data (height/weight/goal) lives only in your DM and is
  never shown in a group.
- **Dietary preferences.** Tell the bot how you eat and it keeps every tip and
  daily note inside those limits, never suggesting a food you avoid. Set it on
  your profile (`/profile vegetarian, no eggs`) or as a standing note
  (`/context no eggs`). A vegetarian gets nudged toward paneer, tofu, or
  sprouts for protein, never eggs, chicken, or fish.
- **Weight history.** Every weight you enter stamps your latest reading and is
  also appended to an append-only history, kept for future trend analysis.
- **Calorie target.** Goal-aware tips and the daily ranking use a realistic
  calorie target (Mifflin-St Jeor from weight, and height/age/sex when given,
  times an activity factor; an average/moderate lifestyle is assumed if you do
  not state one). The surplus/deficit are capped so gain or loss goals stay
  realistic. Without a weight set, the bot falls back to its default logic.
- **Timezone.** Set yours (e.g. `/profile I'm in London`) and photo tips and the
  daily summary's "is your day over?" judgment use your own clock.
  Day bucketing for the group leaderboard stays on the app timezone. Unset means
  the app timezone is used, so nothing changes for you until you set it

## Meal recommendations (/recommend)

Ask "what should I eat next?" in your DM or in the group:

| Variant                     | What happens                                                                 |
| --------------------------- | ---------------------------------------------------------------------------- |
| `/recommend`                | Four keyboard buttons (breakfast / lunch / dinner / snack); a tap sends that command for you |
| `/recommend dinner`         | Options for that meal straight away                                           |
| `/recommend high protein`   | Modifier steers the options; works combined: `/recommend light dinner`       |
| `/recommend snack` at 23:00 | An explicit ask is honoured at any hour with something sensible and light    |

Each reply gives 2-3 realistic options with a rough calorie range, the plate's
macro shape in words, why it fits today, and one top YouTube recipe link when
search finds a clearly relevant match.

What it uses: your goal and dietary limits (profile + context notes), today's
logged meals, and today's macro gaps. All numbers are precomputed by the bot;
the LLM only chooses and explains. No meals logged today? It says so and goes
by your goal alone.

Notes:

- **Group privacy.** A recommendation asked in the group never contains your
  weight, height, age, sex, calorie/protein targets, or remaining-budget
  numbers, and never mentions health conditions from your notes. Those values
  are stripped before the prompt is built, not merely instructed away.
- **Buttons are plain commands.** A tap just sends `/recommend <meal>` as your
  own message, so whoever taps gets their own recommendation, charged to their
  own daily limit. In groups the keyboard is visible and hides after one tap.
- **Cost cap.** Each recommendation counts against the same daily AI-reply
  limit as other LLM commands. The button prompt itself is free.
- **Limits.** Calorie figures are honest ranges, not measurements. Suggestions
  are food ideas for today, not medical or dietetic advice.

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
TELEGRAM_GROUP_CHAT_ID=-1001234567890,-1009876543210
OPENAI_API_KEY=<your-openai-api-key>
OPENAI_MODEL=gpt-4.1-mini
REDIS_URL=redis://localhost:6379/0
APP_TIMEZONE=Asia/Kolkata
ADMIN_API_SECRET=another-long-secret
```

`TELEGRAM_GROUP_CHAT_ID` is a comma-separated list of group chat ids the bot serves. Add a new group's id to extend it; each group's meals and daily summary stay isolated.

`TELEGRAM_WEBHOOK_SECRET` protects the Telegram webhook.

`ADMIN_API_SECRET` protects the manual API routes: `/api/upload`, `/api/summary`, `/api/backfill`, `/api/meals`, `/api/profiles`, and `/api/telegram/simulate`. When it is set, send it as `X-Admin-API-Secret`.

`POST /api/telegram/simulate` runs a synthetic DM or group message through the real dispatch path and returns what the bot would have sent (no Telegram client needed):

```bash
# a group /recommend
curl -X POST http://localhost:8000/api/telegram/simulate \
  -H 'Content-Type: application/json' \
  -d '{"user_id": 123, "surface": "group", "text": "/recommend dinner", "username": "raj"}'
```

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
  -F caption="2 theplas with chai" \
  -F user_id=4242
```

`caption` helps the model. Use it for portion clues, hidden ingredients, or the thing the photo makes ambiguous.

`user_id` is optional. Pass a real Telegram user id to link the upload to that
person's profile, so context notes and their timezone shape the estimate and tip
exactly as they would for a real group photo. Leave it unset for an anonymous upload.

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

## Streaks

A streak is how many days in a row you logged at least one meal. It needs no
setup and no new storage — it's derived on read from the meals already stored,
so it just works.

It shows up on three surfaces:

- **First meal of the day** — your photo reply gains a streak line ("🔥 5-day
  streak"), with richer copy at the 3, 7, 14, and 30-day milestones. Only the
  first meal each day shows it, so replies never turn into streak spam.
- **Daily summary** — each ranked person carries their current streak (🔥). It's
  display-only; it never changes the ranking.
- **Evening nudge** — at 19:00 IST the bot posts one consolidated group message
  naming anyone with a live streak (3+ days) who hasn't logged yet today, so they
  can save it before the day ends. If nobody is at risk, it stays silent.

Missing a single day is forgiven (never-miss-twice): a streak only breaks on two
missed days in a row. Day bucketing uses the app timezone, like the group
leaderboard, so everyone shares one clock for what "today" means.

Both scheduled posts are GitHub Actions hitting cron endpoints with a
`Bearer $CRON_SECRET` header: `/api/cron/daily-summary` (21:30 IST) and
`/api/cron/streak-nudge` (19:00 IST). The nudge workflow reuses `CRON_URL` by
swapping the trailing path, so no new secret is needed.

## Finding the group chat id

Telegram group chat ids are negative numbers. Supergroups usually look like `-1001234567890`.

Add the bot to the group, send any message, then check server logs for:

```text
webhook chat_id=-1001234567890
```

Add that value to `TELEGRAM_GROUP_CHAT_ID` (comma-separated for multiple groups).

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
workflows/           top-level bot flows (dispatch, photo, recommend, reports)
domain/              typed dataclasses and pure rules (scoring, targets, gaps)
analyzers/           LLM calls: image, summary, profile, context, recommend
presenters/          Telegram message formatting
storage/             Redis repositories (photos, profiles)
telegram/            Telegram API wrapper, update parsing, polling
llm/                 OpenAI client plumbing and JSON parsing
core/                settings, dates, logging
evals/               end-to-end eval cases and LLM-as-judge runner
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
