from datetime import UTC, datetime, timedelta

from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock


def test_virtual_clock_restores_the_exact_checkpoint_time() -> None:
    clock = VirtualClock(datetime(2026, 1, 1, tzinfo=UTC))
    clock.advance(timedelta(minutes=3))
    snapshot = clock.snapshot()
    clock.advance(timedelta(days=1))

    clock.restore(snapshot)

    assert clock.now() == datetime(2026, 1, 1, 0, 3, tzinfo=UTC)


def test_id_factory_restores_every_namespace_counter() -> None:
    factory = DeterministicIdFactory("checkpoint-seed")
    factory.new_id("event")
    factory.new_id("artifact")
    snapshot = factory.snapshot()
    expected_event = factory.new_id("event")
    expected_artifact = factory.new_id("artifact")

    factory.restore(snapshot)

    assert factory.new_id("event") == expected_event
    assert factory.new_id("artifact") == expected_artifact
