import pytest

from skillflow.models.enums import Lifetime, lifetime_covers


def test_lifetime_exposes_exactly_four_frozen_values() -> None:
    # Given: T03 冻结的 Lifetime 枚举
    # When: 读取全部序列化值
    values = {lifetime.value for lifetime in Lifetime}

    # Then: 只包含用户指定的四个值
    assert values == {"call", "task", "session", "persistent"}


@pytest.mark.parametrize(
    ("granted", "requested", "expected"),
    [
        (Lifetime.CALL, Lifetime.CALL, True),
        (Lifetime.CALL, Lifetime.TASK, False),
        (Lifetime.CALL, Lifetime.SESSION, False),
        (Lifetime.CALL, Lifetime.PERSISTENT, False),
        (Lifetime.TASK, Lifetime.CALL, True),
        (Lifetime.TASK, Lifetime.TASK, True),
        (Lifetime.TASK, Lifetime.SESSION, False),
        (Lifetime.TASK, Lifetime.PERSISTENT, False),
        (Lifetime.SESSION, Lifetime.CALL, True),
        (Lifetime.SESSION, Lifetime.TASK, False),
        (Lifetime.SESSION, Lifetime.SESSION, True),
        (Lifetime.SESSION, Lifetime.PERSISTENT, False),
        (Lifetime.PERSISTENT, Lifetime.CALL, True),
        (Lifetime.PERSISTENT, Lifetime.TASK, True),
        (Lifetime.PERSISTENT, Lifetime.SESSION, True),
        (Lifetime.PERSISTENT, Lifetime.PERSISTENT, True),
    ],
)
def test_lifetime_uses_diamond_partial_order(
    granted: Lifetime,
    requested: Lifetime,
    expected: bool,
) -> None:
    # Given: 一个 Grant lifetime 和一个 Effect lifetime
    # When: 判断 Grant 是否覆盖 Effect
    result = lifetime_covers(granted, requested)

    # Then: 使用菱形偏序而不是线性枚举顺序
    assert result is expected
