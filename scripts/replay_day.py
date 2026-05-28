"""Regression replay: 2026-05-27 day-summary fixture.

Replays yesterday's eight users through the new scoring + ranking pipeline
WITHOUT calling the LLM. Each user's FoodSignals and macros are hand-crafted
from the dish list as if the detection prompt had returned the targets in
the plan at docs/plans/2026-05-28-001-...-plan.md. Macros are anchor-based
estimates from the photo prompt anchor table.

Run: python3 scripts/replay_day.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domain.day import DayMacros, DayNote, DayReport, Meal, UserDay
from domain.scoring import FoodSignals, compute_day_score


def m(dish: str, kcal: int, time: str, *,
      p: int = 0, c: int = 0, f: int = 0, fb: int = 0,
      asu: int = 0, sf: int = 0) -> Meal:
    return Meal(
        dish=dish, calories=kcal, eaten_at=time,
        protein_g=p, carb_g=c, fat_g=f, fibre_g=fb,
        added_sugar_g=asu, sat_fat_g=sf,
    )


# Each entry: (sender, [(meals)], FoodSignals) — macros aggregated by DayMacros.
FIXTURE: list[tuple[str, list[Meal], FoodSignals]] = [
    (
        "@vrajshah",
        [
            m("Veg uttapam with aloo gravy and black chana salad", 500, "10:03",
              p=15, c=80, f=10, fb=8, asu=0, sf=2),
            m("100 ml coffee", 60, "11:21", p=2, c=8, f=2, fb=0, asu=5, sf=1),
            m("Mix veg with mushroom, 2 roti, salad", 460, "13:05",
              p=12, c=60, f=15, fb=8, asu=0, sf=3),
            m("Black coffee", 5, "16:12"),
            m("Vegetable fried rice with paneer chilly", 700, "20:21",
              p=18, c=85, f=28, fb=4, asu=2, sf=8),
            m("Blueberry sorbet popsicle", 90, "22:24",
              p=0, c=22, f=0, fb=0, asu=18, sf=0),
        ],
        FoodSignals(
            veg_servings=3, has_legume=True, has_whole_grain=False, protein_meals=2,
            has_fruit=False, has_plain_dairy=True,
            fried_items=0, sweet_items=1, ultraprocessed_items=1,
            refined_grain_dominant=True,
        ),
    ),
    (
        "@piratehen",
        [
            m("Oats in milk with pumpkin seeds and 3 Parle-G biscuits", 345, "10:02",
              p=10, c=45, f=10, fb=4, asu=10, sf=3),
            m("Single samosa with chutney", 280, "10:35",
              p=5, c=30, f=14, fb=2, asu=0, sf=5),
            m("Tofu with dal, curd and salad", 360, "14:17",
              p=22, c=20, f=12, fb=8, asu=0, sf=3),
            m("Veg cheese grilled sandwich", 520, "18:06",
              p=14, c=50, f=22, fb=3, asu=2, sf=10),
            m("1 piece chewing gum", 5, "21:25",
              p=0, c=2, f=0, fb=0, asu=2, sf=0),
        ],
        FoodSignals(
            veg_servings=1, has_legume=True, has_whole_grain=True, protein_meals=1,
            has_fruit=False, has_plain_dairy=True,
            fried_items=1, sweet_items=1, ultraprocessed_items=2,
            refined_grain_dominant=True,
        ),
    ),
    (
        "@Wetsal",
        [
            m("2 methi theplas with ghee and tea", 340, "09:04",
              p=10, c=40, f=15, fb=4, asu=4, sf=4),
            m("Rice with dahi, dal-peanuts, chokha, samosa, farali pattice", 1090, "13:32",
              p=30, c=130, f=45, fb=12, asu=0, sf=15),
            m("1 kesar mango slices", 150, "13:32",
              p=1, c=37, f=0, fb=3, asu=0, sf=0),
            m("Rice flour roti with chole and mango", 550, "20:37",
              p=18, c=90, f=8, fb=10, asu=0, sf=2),
        ],
        FoodSignals(
            veg_servings=1, has_legume=True, has_whole_grain=False, protein_meals=2,
            has_fruit=True, has_plain_dairy=True,
            fried_items=2, sweet_items=0, ultraprocessed_items=0,
            refined_grain_dominant=True,
        ),
    ),
    (
        "@divyeshvartha",
        [
            m("Overnight oats with yoghurt, milk, chia and sunflower seeds", 510, "08:57",
              p=20, c=55, f=18, fb=10, asu=2, sf=4),
            m("Indian chai tea", 35, "11:46", p=1, c=5, f=1, fb=0, asu=4, sf=1),
            m("Rice with sambar, rasam, chana, curd, papad", 830, "13:52",
              p=28, c=120, f=18, fb=12, asu=0, sf=5),
            m("Half tea", 20, "16:18", p=1, c=3, f=0, fb=0, asu=2, sf=0),
            m("Cabbage sabji with 4 butter roti and kachumbar", 670, "19:52",
              p=15, c=90, f=22, fb=10, asu=0, sf=8),
            m("Thin tuwar dal", 140, "20:31", p=8, c=18, f=3, fb=4, asu=0, sf=1),
        ],
        FoodSignals(
            veg_servings=3, has_legume=True, has_whole_grain=True, protein_meals=3,
            has_fruit=False, has_plain_dairy=True,
            fried_items=0, sweet_items=0, ultraprocessed_items=0,
            refined_grain_dominant=False,
        ),
    ),
    (
        "@sanziepie",
        [
            m("Coffee with skimmed milk and sugar", 60, "10:49",
              p=2, c=8, f=2, fb=0, asu=5, sf=1),
            m("Chicken fajita sandwich with large chai latte", 740, "13:44",
              p=28, c=80, f=28, fb=4, asu=10, sf=8),
            m("1 banana", 105, "18:36", p=1, c=27, f=0, fb=3, asu=0, sf=0),
            m("Bhindi with rice and milk coffee", 500, "19:19",
              p=10, c=80, f=10, fb=6, asu=3, sf=2),
            m("Paneer curry with rice", 650, "22:29",
              p=22, c=70, f=28, fb=4, asu=0, sf=12),
        ],
        FoodSignals(
            veg_servings=1, has_legume=False, has_whole_grain=False, protein_meals=3,
            has_fruit=True, has_plain_dairy=True,
            fried_items=0, sweet_items=2, ultraprocessed_items=0,
            refined_grain_dominant=True,
        ),
    ),
    (
        "@ravindupatel",
        [
            m("Milk tea, chai", 100, "07:59", p=2, c=10, f=4, fb=0, asu=6, sf=2),
            m("Tindora sabji with rice flour roti and keri chundho", 570, "13:12",
              p=10, c=80, f=18, fb=6, asu=12, sf=4),
            m("Moong dal with rice flour roti and keri chundho", 470, "21:30",
              p=15, c=70, f=8, fb=8, asu=12, sf=2),
        ],
        FoodSignals(
            veg_servings=1, has_legume=True, has_whole_grain=False, protein_meals=1,
            has_fruit=False, has_plain_dairy=True,
            fried_items=0, sweet_items=2, ultraprocessed_items=0,
            refined_grain_dominant=True,
        ),
    ),
    (
        "@thegreyman",
        [
            m("Coffee with milk, mamra, 2 Parle-G biscuits", 280, "05:19",
              p=5, c=40, f=8, fb=2, asu=8, sf=3),
            m("Masala chai", 150, "06:56", p=3, c=12, f=6, fb=0, asu=8, sf=3),
            m("5 egg omelette", 430, "14:54", p=35, c=4, f=30, fb=0, asu=0, sf=8),
            m("Chicken and egg curry with keri chhundo, 2 whole wheat roti", 760, "18:59",
              p=42, c=60, f=32, fb=6, asu=10, sf=8),
            m("250 ml milk with 3 Marie biscuits", 210, "19:24",
              p=10, c=25, f=8, fb=0, asu=5, sf=5),
        ],
        FoodSignals(
            veg_servings=0, has_legume=False, has_whole_grain=True, protein_meals=3,
            has_fruit=False, has_plain_dairy=True,
            fried_items=0, sweet_items=2, ultraprocessed_items=1,
            refined_grain_dominant=False,
        ),
    ),
    (
        "@jashlii",
        [
            m("2 rice flour rotis with masala tea", 430, "08:39",
              p=8, c=70, f=8, fb=4, asu=5, sf=2),
            m("2 vada pav, samosa, chevdo, buttermilk", 1450, "19:46",
              p=30, c=170, f=60, fb=10, asu=2, sf=20),
            m("3 kesar mangoes", 420, "21:23", p=3, c=100, f=0, fb=6, asu=0, sf=0),
        ],
        FoodSignals(
            veg_servings=0, has_legume=False, has_whole_grain=False, protein_meals=1,
            has_fruit=True, has_plain_dairy=True,
            fried_items=3, sweet_items=1, ultraprocessed_items=1,
            refined_grain_dominant=True,
        ),
    ),
]


def main() -> None:
    users: list[UserDay] = []
    notes: list[DayNote] = []
    print(f"{'sender':<18} {'kcal':>5}  {'periods':>7}  {'P':>3} {'Fb':>3} "
          f"{'Sug%':>5} {'Sat%':>5}  {'score':>5}")
    print("-" * 70)
    for sender, meals, signals in FIXTURE:
        macros = DayMacros.from_meals(meals)
        kcal = sum(me.calories for me in meals)
        score = compute_day_score(signals, meals, macros)
        sugar_pct = (macros.added_sugar_g * 4) / kcal * 100 if kcal else 0
        sat_pct = (macros.sat_fat_g * 9) / kcal * 100 if kcal else 0
        from domain.day import meal_periods_covered
        periods = meal_periods_covered(meals)
        print(f"{sender:<18} {kcal:>5}  {periods:>7}  "
              f"{macros.protein_g:>3} {macros.fibre_g:>3} "
              f"{sugar_pct:>5.1f} {sat_pct:>5.1f}  {score:>5}")
        users.append(UserDay(sender_label=sender, calories=kcal, meals=tuple(meals)))
        notes.append(DayNote(summary="(skipped LLM)", health_score=score))

    print()
    print("Leaderboard (two-tier rank):")
    report = DayReport.assemble(chat_id=-1, day_key="2026-05-27",
                                users=users, notes=notes, total_photos=37)
    for u in report.users:
        print(f"  #{u.rank}  {u.sender_label:<18} "
              f"🍽️ {u.meal_periods_covered}/3  "
              f"🔥 {u.calories} kcal  "
              f"💪 {u.health_score}/10")


if __name__ == "__main__":
    main()
