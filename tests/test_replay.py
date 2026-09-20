import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from queue import Queue

from app.data.base import Tick
from app.data.replay import HistoricalReplayProvider


def test_historical_replay_ordered_dispatch():
    q = Queue()
    now = datetime.now(timezone.utc)
    dataset = [
        Tick("AAPL", Decimal("150.00"), Decimal("100"), now, source="historical_replay"),
        Tick("AAPL", Decimal("151.00"), Decimal("200"), now + timedelta(milliseconds=10), source="historical_replay"),
        Tick("AAPL", Decimal("152.00"), Decimal("300"), now + timedelta(milliseconds=20), source="historical_replay"),
    ]

    replay = HistoricalReplayProvider(
        tick_queue=q,
        symbols=["AAPL"],
        replay_speed=100.0,  # fast replay
        ticks_dataset=dataset,
    )

    replay.start()
    time.sleep(0.15)
    replay.stop()

    assert not q.empty()
    ticks = []
    while not q.empty():
        ticks.append(q.get())

    assert len(ticks) == 3
    assert [t.price for t in ticks] == [Decimal("150.00"), Decimal("151.00"), Decimal("152.00")]
    assert all(t.source == "historical_replay" for t in ticks)


def test_historical_replay_empty_dataset_handling():
    q = Queue()
    replay = HistoricalReplayProvider(
        tick_queue=q,
        symbols=["AAPL"],
        ticks_dataset=[],
    )

    replay.start()
    time.sleep(0.05)
    replay.stop()

    assert q.empty()
    assert not replay.is_running()
