from datetime import UTC, datetime, timedelta

from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock

START = datetime(2026, 1, 1, tzinfo=UTC)


def test_virtual_clock_moves_only_when_explicitly_advanced() -> None:
    # Given: 一个固定起点的虚拟时钟
    clock = VirtualClock(START)

    # When: 显式推进五秒
    before = clock.now()
    clock.advance(timedelta(seconds=5))
    after = clock.now()

    # Then: 时间只按显式增量变化
    assert before == START
    assert after == START + timedelta(seconds=5)


def test_deterministic_id_factory_replays_same_namespaced_sequence() -> None:
    # Given: 两个 seed 相同的独立 ID 工厂
    first = DeterministicIdFactory("seed-7")
    second = DeterministicIdFactory("seed-7")

    # When: 以相同顺序生成不同命名空间的 ID
    first_sequence = (
        first.new_id("event"),
        first.new_id("artifact"),
        first.new_id("event"),
    )
    second_sequence = (
        second.new_id("event"),
        second.new_id("artifact"),
        second.new_id("event"),
    )

    # Then: 序列完全可重放且命名空间可见
    assert first_sequence == second_sequence
    assert first_sequence[0].startswith("event-")
    assert first_sequence[1].startswith("artifact-")
    assert len(set(first_sequence)) == len(first_sequence)
