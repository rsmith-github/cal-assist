from datetime import date

from app.models import Day

KCAL_PER_KG = 7700.0


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


def format_stale_empty_caught_up(day: Day) -> str:
    head = (
        "Empty backdated day(s) were skipped — your active logging day is now "
        f"{day.date} (no need to ND through each gap day).\n\n"
    )
    return head + format_totals_block(day)


def format_weekly_summary(
    days: list[Day],
    maintenance_calories: int | None = None,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
) -> str:
    if period_start is not None and period_end is not None:
        period = f"{period_start} – {period_end}"
    elif days:
        period = f"{min(d.date for d in days)} – {max(d.date for d in days)}"
    else:
        period = ""

    if not days:
        if period:
            return (
                f"No closed days in this window ({period}). "
                "Log and ND days in that range to see a week summary."
            )
        return "No closed days yet — log some days and use ND to close them for weekly stats."

    n = len(days)
    sum_in = sum(d.total_calories_in for d in days)
    sum_out = sum(d.total_calories_out for d in days)
    sum_net = sum(d.net_calories for d in days)
    avg_net = sum_net / n
    lines = [
        f"Week ({period}) — {n} closed day(s)",
        f"Avg net: {avg_net:.0f} kcal/day",
        f"Total in:  {sum_in} kcal",
        f"Total out: {sum_out} kcal",
        f"Total net: {sum_net} kcal",
    ]
    if maintenance_calories is not None and maintenance_calories > 0:
        target_total = maintenance_calories * n
        delta = sum_net - target_total
        lines.append(f"Maintenance: {maintenance_calories} kcal/day")
        if delta < 0:
            kg = (-delta) / KCAL_PER_KG
            lines.append(f"Vs maintenance: ~{kg:.2f} kg loss (rough, {KCAL_PER_KG:.0f} kcal ≈ 1 kg)")
        elif delta > 0:
            kg = delta / KCAL_PER_KG
            lines.append(f"Vs maintenance: ~{kg:.2f} kg gain (rough, {KCAL_PER_KG:.0f} kcal ≈ 1 kg)")
        else:
            lines.append("Vs maintenance: on target for this window.")
    else:
        if sum_net <= 0:
            est_kg = (-sum_net) / KCAL_PER_KG
            fat_line = (
                f"Rough net-kcal trend: ~{est_kg:.2f} kg loss "
                f"(set /maintenance for a better estimate; {KCAL_PER_KG:.0f} kcal ≈ 1 kg)."
            )
        else:
            est_kg = sum_net / KCAL_PER_KG
            fat_line = (
                f"Rough net-kcal trend: ~{est_kg:.2f} kg gain "
                f"(set /maintenance for a better estimate; {KCAL_PER_KG:.0f} kcal ≈ 1 kg)."
            )
        lines.append("Maintenance: not set (use /maintenance).")
        lines.append(fat_line)
    return "\n".join(lines)


def format_parse_failure() -> str:
    return (
        "Couldn't parse that. Try e.g. `300 kcal chicken`, `2 beers`, "
        "`ran 5km`, or set OPENAI_API_KEY for messier phrases."
    )
