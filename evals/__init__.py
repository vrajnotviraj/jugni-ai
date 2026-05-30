"""Selectable, in-process evals for the Jugni food bot.

Three small files:
  - harness.py : builds the real bot once and exposes its route handlers as a
                 `World` (upload, command, meals, delete, summary). Plumbing.
  - cases.py   : a self-printing `Day` API plus the cases — each reads top-to-bottom
                 as the steps it performs. This is the file you edit to add cases.
  - run.py     : the runner — picks the chosen cases, runs them, and judges the text.

See evals/README.md.
"""
