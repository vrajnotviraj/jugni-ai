"""Text intake: turn a typed meal description into honest numbers and a tip.

The image analyzer reads a photo; this one reads words ("2 blocks chocolate +
10g almonds"). It reuses the same two-pass shape -- an objective extraction that
estimates calories and macros from the text (searching the web for the calorie
counts), then the shared text-only coaching pass. The output is a ``FoodAnalysis``
identical in shape to the photo path, so storage, the reply card, summaries, and
streaks all work unchanged.
"""

from analyzers.intake.analyzer import analyse_intake
from analyzers.intake.factory import IntakeAnalyzer, build_intake_analyzer

__all__ = [
    "IntakeAnalyzer",
    "analyse_intake",
    "build_intake_analyzer",
]
