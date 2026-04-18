import re
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import formatter
from app.models import Day, Entry, UserProfile
from app.parser import regex_parser
from app.parser.base import ParsedEntry
from app.parser.router import parse_log_line


class TrackerService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _get_open_day(self, user_id: int) -> Day | None:
        return (
            self.session.query(Day)
            .filter(Day.user_id == user_id, Day.closed.is_(False))
            .order_by(Day.id.desc())
            .first()
        )

    def _has_any_entries(self, day: Day) -> bool:
        return (
            self.session.query(Entry)
            .filter(Entry.day_id == day.id, Entry.deleted.is_(False))
            .first()
            is not None
        )

    def _jump_empty_stale_open_day_to_today(self, user_id: int) -> None:
        """If open day is before today and has no entries, drop it and open today."""
        open_day = self._get_open_day(user_id)
        if not open_day or open_day.date >= date.today():
            return
        if self._has_any_entries(open_day):
            return
        self.session.delete(open_day)
        self.session.flush()
        self._attach_open_day_for_calendar_date(user_id, date.today())

    def _attach_open_day_for_calendar_date(self, user_id: int, target: date) -> Day:
        row = (
            self.session.query(Day)
            .filter(Day.user_id == user_id, Day.date == target)
            .first()
        )
        if row:
            row.closed = False
            self.session.flush()
            self._recalc_day(row)
            return row
        d = Day(
            user_id=user_id,
            date=target,
            total_calories_in=0,
            total_calories_out=0,
            net_calories=0,
            closed=False,
        )
        self.session.add(d)
        self.session.flush()
        return d

    def _stale_filled_calendar_block_message(self, user_id: int) -> str | None:
        """If open day is before today but already has logs, require ND first."""
        open_day = self._get_open_day(user_id)
        if not open_day or open_day.date >= date.today():
            return None
        if not self._has_any_entries(open_day):
            return None
        return (
            f"Your active logging day is dated {open_day.date}, which is before today. "
            "Send ND or /nd to close it and start a new day, then log again."
        )

    def _recalc_day(self, day: Day) -> None:
        q = (
            self.session.query(Entry)
            .filter(Entry.day_id == day.id, Entry.deleted.is_(False))
            .all()
        )
        tin = sum(e.calories_in or 0 for e in q)
        tout = sum(e.calories_out or 0 for e in q)
        day.total_calories_in = tin
        day.total_calories_out = tout
        day.net_calories = tin - tout
        self.session.flush()

    def _ensure_open_day(self, user_id: int, *, allow_calendar_jump: bool = True) -> Day:
        if allow_calendar_jump:
            self._jump_empty_stale_open_day_to_today(user_id)

        open_day = self._get_open_day(user_id)
        if open_day:
            return open_day

        max_d = self.session.scalar(
            select(func.max(Day.date)).where(Day.user_id == user_id)
        )
        next_date = (max_d + timedelta(days=1)) if max_d else date.today()
        d = Day(
            user_id=user_id,
            date=next_date,
            total_calories_in=0,
            total_calories_out=0,
            net_calories=0,
            closed=False,
        )
        self.session.add(d)
        self.session.flush()
        return d

    def _add_parsed_entries(
        self, day: Day, raw_text: str, items: list[ParsedEntry]
    ) -> None:
        for p in items:
            cin, cout = p.calories_in, p.calories_out
            self.session.add(
                Entry(
                    day_id=day.id,
                    type=p.entry_type,
                    description=raw_text[:512],
                    parsed_name=p.name[:256],
                    calories_in=cin,
                    calories_out=cout,
                )
            )
        self.session.flush()
        self._recalc_day(day)

    def new_day(self, user_id: int, *, for_remainder_followup: bool = False) -> str:
        """Roll forward the calendar day. If the open day is empty and behind
        server today, sync to today first (avoids closing one ND at a time
        across a gap). Skipped when `for_remainder_followup` so ND, food keeps
        the post-ND day as the +1 calendar day.
        """
        day = self._ensure_open_day(user_id, allow_calendar_jump=False)
        if (
            not for_remainder_followup
            and not self._has_any_entries(day)
            and day.date < date.today()
        ):
            before = day.date
            self._jump_empty_stale_open_day_to_today(user_id)
            self.session.flush()
            day = self._get_open_day(user_id)
            if day is not None and day.date != before:
                self.session.commit()
                return formatter.format_stale_empty_caught_up(day)

        self._recalc_day(day)
        day.closed = True
        self.session.flush()

        new_date = day.date + timedelta(days=1)
        new_day = Day(
            user_id=user_id,
            date=new_date,
            total_calories_in=0,
            total_calories_out=0,
            net_calories=0,
            closed=False,
        )
        self.session.add(new_day)
        self.session.flush()
        self.session.commit()
        prev = day
        return formatter.format_new_day(prev, new_day)

    # Matches "ND" or "new day" at the very start of a message, optionally
    # followed by a separator (comma, newline, slash) and more text to log.
    _ND_PREFIX = re.compile(
        r"(?i)^(?:nd|new\s*day)\s*(?:[,\n/]\s*(.+))?$",
        re.DOTALL,
    )

    def _match_nd(self, text: str) -> tuple[bool, str]:
        """Returns (is_nd, remaining_text_to_log)."""
        m = self._ND_PREFIX.match(text.strip())
        if not m:
            return False, text
        remainder = (m.group(1) or "").strip()
        return True, remainder

    def _match_remove(self, text: str) -> str | None:
        m = re.match(r"(?i)^remove\s+(.+)$", text.strip())
        return m.group(1).strip() if m else None

    def _match_actually(self, text: str) -> tuple[int, str, int] | None:
        m = re.match(
            r"(?i)^actually\s+(\d+)\s+(.+?)\s+not\s+(\d+)\s*$",
            text.strip(),
        )
        if not m:
            return None
        return int(m.group(1)), m.group(2).strip(), int(m.group(3))

    def remove_entry(self, user_id: int, needle: str) -> str:
        day = self._ensure_open_day(user_id)
        needle_l = needle.lower()
        q = (
            self.session.query(Entry)
            .join(Day)
            .filter(
                Day.user_id == user_id,
                Entry.day_id == day.id,
                Entry.deleted.is_(False),
            )
            .order_by(Entry.timestamp.desc())
            .all()
        )
        hit = next(
            (
                e
                for e in q
                if needle_l in e.description.lower()
                or needle_l in e.parsed_name.lower()
            ),
            None,
        )
        if not hit:
            self.session.commit()
            return f"No matching entry for “{needle}” on the current day."

        desc = hit.parsed_name or hit.description
        hit.deleted = True
        self.session.flush()
        self._recalc_day(day)
        self.session.commit()
        return formatter.format_removed(desc, day)

    def correction(self, user_id: int, new_n: int, item_phrase: str, old_n: int) -> str:
        day = self._ensure_open_day(user_id)
        item_l = item_phrase.lower()
        q = (
            self.session.query(Entry)
            .join(Day)
            .filter(
                Day.user_id == user_id,
                Entry.day_id == day.id,
                Entry.deleted.is_(False),
            )
            .order_by(Entry.timestamp.desc())
            .all()
        )
        hit = next(
            (
                e
                for e in q
                if item_l in e.description.lower()
                or item_l in e.parsed_name.lower()
                or str(old_n) in e.description
            ),
            None,
        )
        if hit:
            hit.deleted = True
            self.session.flush()
            self._recalc_day(day)

        fragment = f"{new_n} {item_phrase}"
        items = regex_parser.parse(fragment)
        if not items:
            items = parse_log_line(fragment)
        if not items:
            self.session.commit()
            return "Updated old entry but couldn't parse the correction — try logging again."

        self._add_parsed_entries(day, fragment, items)
        self.session.commit()
        bits = [p.summary_fragment() for p in items]
        return formatter.format_confirmation(bits, day)

    def add_log(self, user_id: int, text: str, *, skip_calendar_jump: bool = False) -> str:
        day = self._ensure_open_day(
            user_id, allow_calendar_jump=not skip_calendar_jump
        )
        block = self._stale_filled_calendar_block_message(user_id)
        if block:
            self.session.commit()
            return block
        items = parse_log_line(text)
        if not items:
            self.session.commit()
            return formatter.format_parse_failure()

        self._add_parsed_entries(day, text, items)
        self.session.commit()
        bits = [p.summary_fragment() for p in items]
        return formatter.format_confirmation(bits, day)

    def summary(self, user_id: int) -> str:
        day = self._ensure_open_day(user_id)
        self.session.commit()
        return formatter.format_summary_only(day)

    def weekly(self, user_id: int) -> str:
        today = date.today()
        window_start = today - timedelta(days=6)
        days = (
            self.session.query(Day)
            .filter(
                Day.user_id == user_id,
                Day.closed.is_(True),
                Day.date >= window_start,
                Day.date <= today,
            )
            .order_by(Day.date.desc())
            .all()
        )
        maintenance = self.get_maintenance_calories(user_id)
        self.session.commit()
        return formatter.format_weekly_summary(
            days, maintenance, period_start=window_start, period_end=today
        )

    def get_maintenance_calories(self, user_id: int) -> int | None:
        profile = (
            self.session.query(UserProfile)
            .filter(UserProfile.user_id == user_id)
            .first()
        )
        if not profile:
            return None
        return profile.maintenance_calories

    def set_maintenance_calories(self, user_id: int, calories: int) -> int:
        profile = (
            self.session.query(UserProfile)
            .filter(UserProfile.user_id == user_id)
            .first()
        )
        if not profile:
            profile = UserProfile(user_id=user_id, maintenance_calories=calories)
            self.session.add(profile)
        else:
            profile.maintenance_calories = calories
        self.session.commit()
        return calories

    def undo(self, user_id: int) -> str:
        """Pop the most recent non-deleted entry from today."""
        day = self._ensure_open_day(user_id)
        last = (
            self.session.query(Entry)
            .filter(Entry.day_id == day.id, Entry.deleted.is_(False))
            .order_by(Entry.timestamp.desc())
            .first()
        )
        if not last:
            self.session.commit()
            return "Nothing to undo on the current day."
        desc = last.parsed_name or last.description
        last.deleted = True
        self.session.flush()
        self._recalc_day(day)
        self.session.commit()
        return formatter.format_removed(f"(undo) {desc}", day)

    def handle(self, user_id: int, text: str) -> str:
        raw = text.strip()
        if not raw:
            return "Send food, exercise, ND, remove …, /undo, or /week."

        is_nd, remainder = self._match_nd(raw)
        if is_nd:
            nd_reply = self.new_day(
                user_id, for_remainder_followup=bool(remainder)
            )
            if not remainder:
                return nd_reply
            # Log the remainder onto the newly-opened day
            log_reply = self.add_log(user_id, remainder, skip_calendar_jump=True)
            return f"{nd_reply}\n\n{log_reply}"

        rm = self._match_remove(raw)
        if rm:
            return self.remove_entry(user_id, rm)

        act = self._match_actually(raw)
        if act:
            new_n, phrase, old_n = act
            return self.correction(user_id, new_n, phrase, old_n)

        low = raw.lower()
        if low in ("summary", "totals", "today"):
            return self.summary(user_id)
        if low in ("week", "weekly"):
            return self.weekly(user_id)
        if low in ("undo", "undolast"):
            return self.undo(user_id)

        return self.add_log(user_id, raw)
