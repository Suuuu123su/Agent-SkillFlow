from collections import Counter

from skillflow.experiment.t19.matrix import GROUPS, formal, precheck, supplements


def test_full_schedule_and_four_cells_are_complete() -> None:
    trials = formal()
    assert len(trials) == len({t.trial_id for t in trials}) == 336
    assert len([t for t in trials if not t.supplementary]) == 240
    assert len(precheck()) == 32
    for group in GROUPS:
        assert sum(t.group == group for t in trials) == 56
        for mechanism in ("C1", "C2"):
            for template in ("heldout-ledger", "heldout-inventory"):
                for repeat in (1, 2):
                    cells = {
                        (t.role, t.bridge)
                        for t in trials
                        if t.group == group
                        and t.mechanism == mechanism
                        and t.template == template
                        and t.repeat == repeat
                    }
                    assert cells == {
                        ("attack", True),
                        ("attack", False),
                        ("neutral", True),
                        ("neutral", False),
                    }


def test_supplement_mapping_covers_every_strict_metric_condition() -> None:
    result = supplements(formal())
    assert len(result) == len({r.supplement_id for r in result}) == 144
    assert Counter(r.reason for r in result) == {"ALR": 48, "RIR1": 48, "RIR3": 48}
    assert all(r.branches == ("identity", "neutral", "same_view") for r in result)


def test_group_positions_are_balanced_without_claiming_model_determinism() -> None:
    trials = formal()
    assert trials == formal()
    for group in GROUPS:
        counts = Counter(i % 6 for i, t in enumerate(trials) if t.group == group)
        assert max(counts.values()) - min(counts.values()) <= 1
