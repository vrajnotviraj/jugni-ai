# Drop food photos here

Put real food photos in this folder (`.jpg`, `.jpeg`, `.png`, `.webp`). The eval
hands them to simulated people and prints the bot's tips and daily summary.

**Name files by meal type and dish** — the prefix sets a realistic time, the rest
becomes the caption sent to the analyzer:

- `s_` = snack → posted 7–11 AM or 3–6 PM. e.g. `s_banana shake with protein.jpg`
- `m_` = meal  → posted 12–3 PM or 7–10 PM. e.g. `m_palak paneer with rice.jpg`

The `s_`/`m_` prefix is stripped before the filename is used as the caption.

This folder is gitignored (only this README is tracked), so your photos are never
committed.
