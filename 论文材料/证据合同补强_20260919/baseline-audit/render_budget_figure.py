"""Layout-only budget figure rendering from sealed aggregate curves.

Does not import or run any experiment module, predictor, runner, or oracle.
Run with -B; all matplotlib configuration remains inside the supplied E: run.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    run = args.run.resolve()
    if run.drive.casefold() != "e:":
        raise ValueError("This review only writes to the authorized E: workspace")
    target = Path("E:/Skill ＆ Harness/tmp/evidence-strengthening-matplotlib")
    config = run / ".mplconfig"
    config.mkdir(exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(config)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(target))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, FuncFormatter, PercentFormatter

    source = run / "AGGREGATE_CURVES.csv"
    originals = [run / "BUDGET_COVERAGE.svg", run / "BUDGET_COVERAGE.png"]
    before = {path.name: sha(path) for path in [source, *originals]}
    with source.open(encoding="utf-8", newline="") as stream:
        chosen = [row for row in csv.DictReader(stream)
                  if row["split"] == "heldout" and row["metric"] == "ALL"
                  and row["mechanism"] == "ALL"]
    policies = sorted({row["policy"] for row in chosen})
    expected_policies = ["dependency_guided", "global_fixed", "metric_static", "random"]
    if policies != expected_policies:
        raise ValueError("Unexpected policy set; layout review cannot change series")
    budgets = sorted({int(row["budget"]) for row in chosen})
    if budgets[0] != 0 or budgets[-1] != 76363:
        raise ValueError("Frozen budget range changed")
    fields = ("family_equal_correct_point_coverage", "family_equal_wrong_point_rate")
    titles = ("Correct definite coverage", "Wrong definite judgments")
    colors = {"global_fixed": "#777777", "random": "#9970ab",
              "metric_static": "#2166ac", "dependency_guided": "#d6604d"}
    labels = {"global_fixed": "Global fixed", "random": "Random order (seed mean)",
              "metric_static": "Metric static", "dependency_guided": "Dependency guided"}
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "svg.fonttype": "none"})
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.3))
    series = []
    for axis, field, title in zip(axes, fields, titles):
        for index, policy in enumerate(policies):
            rows = sorted([r for r in chosen if r["policy"] == policy],
                          key=lambda r: int(r["budget"]))
            values = [(int(r["budget"]), float(r[field])) for r in rows if r[field] != ""]
            x, y = zip(*values)
            axis.plot(x, y, color=colors[policy], marker=("o", "s", "^", "D")[index],
                      markersize=4.0, linewidth=1.8, label=labels[policy],
                      linestyle=("-", "--", "-.", ":")[index])
            series.append({"panel_field": field, "policy": policy, "points": values})
        axis.set(title=title, xlabel="Total serialized-byte budget (KiB)",
                 ylabel="Fraction of point-oracle queries")
        axis.set_xlim(0, 76363)
        axis.set_ylim(-0.015, 1.015)
        axis.yaxis.set_major_formatter(PercentFormatter(xmax=1))
        axis.xaxis.set_major_locator(FixedLocator([0, 20 * 1024, 40 * 1024, 60 * 1024]))
        axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1024:.0f}"))
        axis.grid(axis="y", color="#dddddd", linewidth=0.7)
    handles, legend_labels = axes[0].get_legend_handles_labels()
    legend = fig.legend(handles, legend_labels, loc="lower center", ncol=2, frameon=False,
                        bbox_to_anchor=(0.5, 0.055))
    fig.suptitle("Heldout families: equal-byte coverage and error", fontsize=13)
    fig.text(0.5, 0.012,
             "Six families; seeds averaged within query; infeasible rows retained; no IID confidence interval.",
             ha="center", fontsize=8)
    fig.subplots_adjust(left=0.085, right=0.985, top=0.84, bottom=0.30, wspace=0.30)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    tick_overlap = False
    for axis in axes:
        boxes = [text.get_window_extent(renderer) for text in axis.get_xticklabels()]
        tick_overlap |= any(a.overlaps(b) for a, b in zip(boxes, boxes[1:]))
    legend_box = legend.get_window_extent(renderer)
    legend_covers_axes = any(legend_box.overlaps(axis.get_window_extent(renderer)) for axis in axes)
    if tick_overlap or legend_covers_axes:
        raise ValueError("Layout validation failed")
    outputs = [run / "BUDGET_COVERAGE_REVIEWED.svg", run / "BUDGET_COVERAGE_REVIEWED.png"]
    report_path = run / "FIGURE_REVIEW.json"
    if any(path.exists() for path in [*outputs, report_path]):
        raise FileExistsError("Reviewed artifacts already exist; preserve them")
    fig.savefig(outputs[0], format="svg",
                metadata={"Title": "Heldout evidence recovery under frozen total-byte budgets"})
    fig.savefig(outputs[1], dpi=240)
    plt.close(fig)
    after = {path.name: sha(path) for path in [source, *originals]}
    if before != after:
        raise ValueError("Data or original figure changed during layout-only rendering")
    report = {
        "status": "PASS",
        "review_scope": "Layout only; source values, selection, four policies, two panels, ranges, line styles and confidence-interval policy unchanged.",
        "changes": ["Fixed x-axis ticks at 0, 20, 40, 60 KiB.",
                    "Short integer tick labels; KiB unit moved to the x-axis label."],
        "matplotlib_version": matplotlib.__version__,
        "backend": "Agg",
        "dependency_target": str(target),
        "configuration_directory": str(config),
        "csv_sha256": before[source.name],
        "original_figure_sha256": {p.name: before[p.name] for p in originals},
        "reviewed_figure_sha256": {p.name: sha(p) for p in outputs},
        "originals_and_csv_unchanged": before == after,
        "x_range_bytes": [0, 76363],
        "x_tick_bytes": [0, 20480, 40960, 61440],
        "x_tick_labels_KiB": ["0", "20", "40", "60"],
        "y_range": [-0.015, 1.015],
        "panels": list(fields),
        "policies": policies,
        "series_point_counts": [{"panel_field": row["panel_field"], "policy": row["policy"],
                                 "points": len(row["points"])} for row in series],
        "series_sha256": hashlib.sha256(json.dumps(series, sort_keys=True,
                                                   separators=(",", ":")).encode()).hexdigest(),
        "layout_checks": {"tick_label_overlap": tick_overlap, "legend_covers_axes": legend_covers_axes},
        "visual_review": "PENDING",
        "predictor_runs": 0, "new_sandbox_executions": 0, "model_calls": 0,
    }
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "matplotlib_version": matplotlib.__version__,
                      "reviewed_outputs": [p.name for p in outputs],
                      "layout_checks": report["layout_checks"]}))


if __name__ == "__main__":
    main()

