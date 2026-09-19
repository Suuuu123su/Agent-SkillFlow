"""Restore the published P3 valid-only contract without altering frozen releases.

The run status belongs to the failure/qualification evidence channel. It must
therefore be removed together with that channel; observation.closed and legacy
behavior_valid labels are never used to recover a withheld qualification.
"""

from collections import Counter, defaultdict

CONTRACT_VERSION = "p3_valid_only_restored_v1"
CELLS = frozenset({"p00", "p01", "p10", "p11"})


def conjunction(values):
    """Three-valued conjunction; observed failure dominates missing evidence."""
    values = list(values)
    if False in values:
        return False
    return None if None in values else True


def qualification(failure):
    """P3: completed, no issues, every recorded decision behavior normal."""
    if failure is None:
        return None
    status = failure.get("run_status")
    issues = failure.get("issues")
    steps = failure.get("steps")
    return conjunction([
        None if status is None else status == "completed",
        None if issues is None else not issues,
        None if steps is None else conjunction(
            None if x.get("behavior") is None else x["behavior"] == "normal" for x in steps
        ),
    ])


def corrected_analyzer(base_class):
    """Wrap only grid qualification; all other frozen predictor methods stay intact."""

    class CorrectedAnalyzer(base_class):
        def grid(self, document, protocol):
            if protocol != "valid_only":
                return super().grid(document, protocol)
            design = self.get(document, "design")
            groups = defaultdict(list)
            for member in design["members"]:
                groups[(member["cluster"], member["repeat"])].append(member)
            kept = []
            unknown = False
            for members in groups.values():
                # Incomplete or duplicated cells never qualify as a quartet.
                if len(members) != 4 or {x["cell"] for x in members} != CELLS:
                    continue
                state = conjunction(
                    qualification(self.get(self.documents[x["unit"]], "failure"))
                    for x in members
                )
                if state is True:
                    kept.extend(members)
                elif state is None:
                    unknown = True
            filtered = dict(document, design=dict(design, members=kept))
            # Preserve the frozen endpoint/interval/cluster bootstrap estimator.
            result = super().grid(filtered, "scheduled")
            planned = Counter(x["cell"] for x in design["members"])
            for cell, values in result["details"]["cells"].items():
                values["planned"] = planned[cell]
            if unknown:
                return self.result(
                    eligibility=None, lower=-2, upper=2,
                    details={"cells": result["details"]["cells"]},
                    reason="valid_only_qualification_unknown",
                )
            return result

    return CorrectedAnalyzer
