from app.models import Day


def format_totals_block(day: Day) -> str:
    lines = [
        "Today's totals:",
        f"  In:  {day.total_calories_in} kcal",
        f"  Out: {day.total_calories_out} kcal",
        f"  Net: {day.net_calories} kcal",
    ]
    if day.total_calories_in > 3500:
        lines.append("(High intake — possible cheat day.)")
    return "\n".join(lines)


def format_confirmation(summary_bits: list[str], day: Day) -> str:
    head = "Got it: " + "; ".join(summary_bits) if summary_bits else "Logged."
    return f"{head}\n\n{format_totals_block(day)}"


def format_new_day(prev: Day | None, new: Day) -> str:
    prev_line = ""
    if prev:
        prev_line = (
            f"Closed {prev.date}: In {prev.total_calories_in} / "
            f"Out {prev.total_calories_out} / Net {prev.net_calories}\n\n"
        )
    return (
        f"{prev_line}New day started ({new.date}).\n\n{format_totals_block(new)}"
    )


def format_removed(entry_desc: str, day: Day) -> str:
    return f"Removed: {entry_desc}\n\n{format_totals_block(day)}"


def format_summary_only(day: Day) -> str:
    return format_totals_block(day)


def format_weekly_summary(days: list[Day], maintenance_calories: int | None = None) -> str:
    if not days:
        return "No closed days yet — log some days and use ND to close them for weekly stats."

    n = len(days)
    sum_in = sum(d.total_calories_in for d in days)
    sum_out = sum(d.total_calories_out for d in days)
    sum_net = sum(d.net_calories for d in days)
    avg_net = sum_net / n
    oldest = min(d.date for d in days)
    newest = max(d.date for d in days)
    lines = [
        f"Week summary ({n} closed day(s), {oldest} → {newest}):",
        f"  Avg net: {avg_net:.0f} kcal/day",
        f"  Total In:  {sum_in} kcal",
        f"  Total Out: {sum_out} kcal",
        f"  Total Net: {sum_net} kcal",
    ]
    if maintenance_calories is not None and maintenance_calories > 0:
        target_total = maintenance_calories * n
        delta = sum_net - target_total
        if delta < 0:
            status = (
                f"Below maintenance by {-delta} kcal total "
                f"({(-delta / n):.0f} kcal/day average)."
            )
            maint_lbs = (-delta) / 3500.0
            trend = f"Maintenance-based trend: ~{maint_lbs:.2f} lb loss."
        elif delta > 0:
            status = (
                f"Above maintenance by {delta} kcal total "
                f"({(delta / n):.0f} kcal/day average)."
            )
            maint_lbs = delta / 3500.0
            trend = f"Maintenance-based trend: ~{maint_lbs:.2f} lb gain."
        else:
            status = "Exactly at maintenance for this period."
            trend = "Maintenance-based trend: weight stable."
        lines.extend(
            [
                f"  Maintenance target: {maintenance_calories} kcal/day",
                f"  {status}",
                f"  {trend} (3500 kcal ≈ 1 lb)",
            ]
        )
    else:
        # If maintenance is unknown, net is the best approximation we have.
        if sum_net <= 0:
            est_lbs = (-sum_net) / 3500.0
            fat_line = (
                f"Estimated fat loss (rough): ~{est_lbs:.2f} lb this week "
                "(3500 kcal ≈ 1 lb)."
            )
        else:
            est_lbs = sum_net / 3500.0
            fat_line = f"Estimated fat gain (rough): ~{est_lbs:.2f} lb this week."
        lines.append("  Maintenance target: not set (use /maintenance).")
        lines.append(f"  {fat_line}")
    return "\n".join(lines)


def format_parse_failure() -> str:
    return (
        "Couldn't parse that. Try e.g. `300 kcal chicken`, `2 beers`, "
        "`ran 5km`, or set OPENAI_API_KEY for messier phrases."
    )
