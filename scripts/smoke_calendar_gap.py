"""Smoke tests for calendar-gap resync (run from repo root: python scripts/smoke_calendar_gap.py)."""
from __future__ import annotations

import sys
from pathlib import Path

# Repo root on sys.path so `app` imports work without PYTHONPATH=.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from datetime import date, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Day, Entry
from app.tracker.service import TrackerService

TODAY = date(2026, 4, 19)
YEST = date(2026, 4, 18)


def fresh() -> tuple:
    # New engine per test so sqlite :memory: is isolated.
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    return s, TrackerService(s)


def test_empty_stale_jumps_to_today() -> None:
    s, svc = fresh()
    uid = 1
    s.add(
        Day(
            user_id=uid,
            date=YEST,
            total_calories_in=0,
            total_calories_out=0,
            net_calories=0,
            closed=False,
        )
    )
    s.commit()
    with patch("app.tracker.service.date") as mock_date:
        mock_date.today.return_value = TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        reply = svc.add_log(uid, "200ml orange juice")
    open_day = svc._get_open_day(uid)
    assert open_day.date == TODAY, (open_day.date, reply)
    entries = s.query(Entry).filter(Entry.deleted.is_(False)).all()
    assert len(entries) == 1
    assert entries[0].day_id == open_day.id
    print("OK empty stale -> today:", reply.split("\n")[0][:60])


def test_filled_stale_blocks() -> None:
    s, svc = fresh()
    uid = 1
    d = Day(
        user_id=uid,
        date=YEST,
        total_calories_in=100,
        total_calories_out=0,
        net_calories=100,
        closed=False,
    )
    s.add(d)
    s.flush()
    s.add(
        Entry(
            day_id=d.id,
            type="food",
            description="egg",
            parsed_name="egg",
            calories_in=100,
            calories_out=None,
        )
    )
    s.commit()
    with patch("app.tracker.service.date") as mock_date:
        mock_date.today.return_value = TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        reply = svc.handle(uid, "200ml orange juice")
    assert "ND" in reply or "/nd" in reply
    n = s.query(Entry).filter(Entry.deleted.is_(False)).count()
    assert n == 1
    print("OK filled stale blocks:", reply[:80])


def test_nd_then_log_remainder() -> None:
    s, svc = fresh()
    uid = 1
    d = Day(
        user_id=uid,
        date=YEST,
        total_calories_in=0,
        total_calories_out=0,
        net_calories=0,
        closed=False,
    )
    s.add(d)
    s.commit()
    with patch("app.tracker.service.date") as mock_date:
        mock_date.today.return_value = TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        svc.handle(uid, "ND, 200ml orange juice")
    open_day = svc._get_open_day(uid)
    assert open_day.date == YEST + timedelta(days=1)
    entries = s.query(Entry).filter(Entry.deleted.is_(False)).all()
    assert len(entries) == 1
    assert entries[0].day_id == open_day.id
    print("OK ND+remainder on post-ND day:", open_day.date)


def test_summary_not_blocked_when_filled_stale() -> None:
    s, svc = fresh()
    uid = 1
    d = Day(
        user_id=uid,
        date=YEST,
        total_calories_in=50,
        total_calories_out=0,
        net_calories=50,
        closed=False,
    )
    s.add(d)
    s.flush()
    s.add(
        Entry(
            day_id=d.id,
            type="food",
            description="x",
            parsed_name="x",
            calories_in=50,
            calories_out=None,
        )
    )
    s.commit()
    with patch("app.tracker.service.date") as mock_date:
        mock_date.today.return_value = TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        out = svc.handle(uid, "summary")
    assert "before today" not in out
    print("OK summary with filled stale:", out[:100].replace("\n", " "))


def test_nd_on_empty_stale_syncs_without_nd_chain() -> None:
    s, svc = fresh()
    uid = 1
    s.add(
        Day(
            user_id=uid,
            date=YEST,
            total_calories_in=0,
            total_calories_out=0,
            net_calories=0,
            closed=False,
        )
    )
    s.commit()
    with patch("app.tracker.service.date") as mock_date:
        mock_date.today.return_value = TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        out = svc.handle(uid, "ND")
    assert "skipped" in out.lower() or "gap" in out.lower()
    open_day = svc._get_open_day(uid)
    assert open_day.date == TODAY
    print("OK ND on empty stale -> catch-up:", out.split("\n")[0][:70])


def test_weekly_only_counts_closed_days_in_calendar_window() -> None:
    s, svc = fresh()
    uid = 1
    s.add(
        Day(
            user_id=uid,
            date=date(2026, 4, 1),
            total_calories_in=9999,
            total_calories_out=0,
            net_calories=9999,
            closed=True,
        )
    )
    s.add(
        Day(
            user_id=uid,
            date=date(2026, 4, 17),
            total_calories_in=100,
            total_calories_out=0,
            net_calories=100,
            closed=True,
        )
    )
    s.add(
        Day(
            user_id=uid,
            date=date(2026, 4, 18),
            total_calories_in=200,
            total_calories_out=0,
            net_calories=200,
            closed=True,
        )
    )
    s.commit()
    with patch("app.tracker.service.date") as mock_date:
        mock_date.today.return_value = TODAY
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        out = svc.weekly(uid)
    assert "9999" not in out
    assert "300" in out
    assert "2026-04-13" in out and "2026-04-19" in out
    print("OK weekly 7-day window:", out.split("\n")[0])


if __name__ == "__main__":
    test_empty_stale_jumps_to_today()
    test_filled_stale_blocks()
    test_nd_then_log_remainder()
    test_summary_not_blocked_when_filled_stale()
    test_nd_on_empty_stale_syncs_without_nd_chain()
    test_weekly_only_counts_closed_days_in_calendar_window()
    print("All smoke checks passed.")
