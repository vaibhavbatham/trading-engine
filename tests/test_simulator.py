import time
from decimal import Decimal
from queue import Queue

from app.data.simulator import SimulationProvider


def test_simulation_provider_tick_generation():
    q = Queue()
    sim = SimulationProvider(
        tick_queue=q,
        symbols=["AAPL", "TSLA"],
        initial_prices={"AAPL": 150.0, "TSLA": 200.0},
        volatility=0.001,
    )

    tick_aapl = sim.generate_next_tick("AAPL")
    assert tick_aapl.symbol == "AAPL"
    assert isinstance(tick_aapl.price, Decimal)
    assert tick_aapl.price > 0
    assert tick_aapl.volume is not None and tick_aapl.volume > 0
    assert tick_aapl.source == "simulation"
    assert tick_aapl.timestamp.tzinfo is not None

    tick_tsla = sim.generate_next_tick("TSLA")
    assert tick_tsla.symbol == "TSLA"
    assert tick_tsla.price > 0


def test_simulation_provider_lifecycle():
    q = Queue()
    sim = SimulationProvider(
        tick_queue=q,
        symbols=["NVDA"],
        interval=0.05,
    )

    sim.start()
    assert sim.is_running()
    time.sleep(0.15)
    sim.stop()

    assert not sim.is_running()
    assert not q.empty()

    ticks = []
    while not q.empty():
        ticks.append(q.get())

    assert all(t.symbol == "NVDA" for t in ticks)
    assert all(t.source == "simulation" for t in ticks)
    assert len(ticks) >= 2


def test_simulation_provider_dynamic_subscribe():
    q = Queue()
    sim = SimulationProvider(
        tick_queue=q,
        symbols=["AAPL"],
    )

    assert sim.symbols == ["AAPL"]
    sim.subscribe(["META", "GOOGL"])
    assert "META" in sim.symbols
    assert "GOOGL" in sim.symbols
