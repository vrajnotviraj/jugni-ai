# Evals

Selectable eval cases that run the real bot **in-process** — no HTTP server. Each
case is a short sequence of the actual route handlers (upload a photo, run a
`/profile` or `/addcontext` command, delete a meal, build the summary); a single
master function judges the text the cases produce.

## Run

```bash
# put a few real food photos in evals/photos/ first (gitignored).
python -m evals.run                 # run every case
python -m evals.run profile day     # run only chosen cases
python -m evals.run --list          # list cases
python -m evals.run --no-judge      # skip the LLM grading
```

Name photos by type and dish: prefix `s_` for a snack (posted 7–11 AM / 3–6 PM) or
`m_` for a meal (12–3 PM / 7–10 PM). The prefix sets a realistic time; the rest of
the **filename becomes the caption** (e.g. `m_palak paneer with rice.jpg`).

## Cases

| Case | Sequence |
| --- | --- |
| `profile` | one user sets a vegetarian fat-loss profile, then posts photos — tips must fit the diet |
| `context` | one user adds a `whole milk` context note, then posts photos |
| `delete`  | post photos, then delete one via the meals route — the total recomputes |
| `day`     | a few people post (one on a profile), then build and grade the daily summary |

## How it's built (three small files)

- **`harness.py`** — builds the real deps once (Redis + OpenAI) and exposes the
  route handlers as a `World` (upload, command, meals, delete, summary). Plumbing.
- **`cases.py`** — a self-printing `Day` API plus the cases. Each case reads
  top-to-bottom as the steps it runs, e.g.:
  ```python
  async def case_profile(day):
      await day.profile("@aarav", "vegetarian, no eggs, want to lose fat")
      await day.post("@aarav", day.snack(), judge=VEG)
      await day.post("@aarav", day.meal(), judge=VEG)
  ```
- **`run.py`** — runs the chosen cases (each isolated, then purged) and judges the
  text they flagged.

Adding a case: write `async def case_x(day)` in `cases.py`, use the `day.*` steps,
attach `judge=<rule>` to anything you want graded, and list it in `CASES`.

## Isolation

Everything writes under a synthetic eval chat id (`-9990000001`) and user ids
(`≥ 990000001`); none belong to a real group or person. `World.purge()` deletes
exactly those keys after each run. Connection settings come from the app's `.env`,
so the eval hits the same Redis + OpenAI the server does.
