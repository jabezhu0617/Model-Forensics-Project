"""Render the overview chart from the exported study data with Matplotlib."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=root / "public/data/index.json")
    parser.add_argument("--output-dir", type=Path, default=root / "src/assets/plots")
    args = parser.parse_args()
    dataset = json.loads(args.input.read_text(encoding="utf8"))
    experiments = {item["id"]: item for item in dataset["experiments"]}
    bars = []

    def add(experiment: dict, group: str, series: str, x: float) -> None:
        pooled = experiment.get("pooled")
        count = (pooled or experiment)["counts"]["concealed"]
        total = pooled["total"] if pooled else len(experiment["runs"])
        if total == 0:
            raise ValueError(f"No recorded trials for {experiment['id']}")
        bars.append(dict(experiment=experiment["id"], group=group, series=series,
                         count=count, total=total, rate=count / total * 100, x=x,
                         interval95=(pooled or experiment).get("interval95"),
                         label=experiment["label"] if experiment.get("variant") else None,
                         sources=pooled["sources"] if pooled else [experiment["id"]]))

    add(experiments["r1-baseline"], "Baseline", "baseline", 0)
    with_variants = any(e.get("variant") for e in experiments.values())
    for i in range(5):
        label = f"H{i}"
        hypothesis = next(h for h in dataset["hypotheses"] if h["id"] == label and h["round"] == 0)
        ordered = []
        for sign, series in [("−", "negative"), ("+", "positive")]:
            group = [experiments[key] for key in hypothesis["arms"] if experiments[key]["sign"] == sign]
            ordered.extend((e, series + ("-rewrite" if e.get("variant", "").endswith("-r") else "-variant" if e.get("variant") else "")) for e in sorted(group, key=lambda e: bool(e.get("variant"))))
        step = .20 if with_variants else .36
        for j, (experiment, series) in enumerate(ordered):
            add(experiment, label, series, i + 1 + (j - (len(ordered) - 1) / 2) * step)

    # Keep the font cache out of the user's home and make SVG IDs reproducible.
    with tempfile.TemporaryDirectory(prefix="forensics-matplotlib-") as cache:
        os.environ["MPLCONFIGDIR"] = cache
        os.environ["XDG_CACHE_HOME"] = cache
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
        from matplotlib.ticker import PercentFormatter

        colors = dict(baseline="#d98a2b", negative="#cc5454", positive="#32936b")
        colors.update({"negative-variant": "#e8a5a5", "positive-variant": "#9aceb5"})
        colors.update({"negative-rewrite": "#f4c9c9", "positive-rewrite": "#c9e8d8"})
        patterns = {"variant": "//", "rewrite": ".."}
        plt.rcParams.update({
            "font.family": "DejaVu Sans", "font.size": 11,
            "svg.fonttype": "path", "svg.hashsalt": "model-forensics-concealment",
            "axes.spines.top": False, "axes.spines.right": False,
            "axes.linewidth": .7, "axes.edgecolor": "#505050",
            "text.color": "#252525", "axes.labelcolor": "#252525",
            "xtick.color": "#404040", "ytick.color": "#404040",
        })
        fig, ax = plt.subplots(figsize=(12.8 if with_variants else 9.5, 4.75 if with_variants else 4.25), layout="constrained")
        baseline_reference = dict(experiment="r1-baseline", rate=bars[0]["rate"], style="dotted")
        reference = ax.axhline(baseline_reference["rate"], color="#666666", linestyle=":", linewidth=1.2, zorder=2)
        reference.set_gid("baseline-reference")
        for item in bars:
            variant = bool(item["label"])
            rectangle = ax.bar(item["x"], item["rate"], width=.17 if with_variants else .30,
                               color=colors[item["series"]], linewidth=.7 if variant else 0,
                               edgecolor="#414141" if variant else None, hatch=patterns.get(item["series"].split("-")[-1]))[0]
            rectangle.set_gid(f"bar-{item['group']}-{item['series']}")
            if with_variants and item["count"] == 0:
                ax.plot(item["x"], 0, marker="_", color=colors[item["series"]], markersize=9,
                        markeredgewidth=2, clip_on=False, zorder=5)
            label_y = item["rate"]
            if item["interval95"] is not None:
                interval = item["interval95"]
                lower, upper = interval["lower"] * 100, interval["upper"] * 100
                error = ax.errorbar(item["x"], item["rate"],
                                    yerr=[[item["rate"] - lower], [upper - item["rate"]]],
                                    fmt="none", ecolor="#404040", elinewidth=1,
                                    capsize=4, capthick=1, zorder=3)
                error.lines[2][0].set_gid(f"errorbar-{item['group']}-{item['series']}")
                label_y = upper
            label = f"{item['rate']:.1f}".rstrip("0").rstrip(".") if item["rate"] % 1 else str(int(item["rate"]))
            caption = f"{item['count']}/{item['total']}" if with_variants else f"{label}%"
            ax.annotate(caption, (item["x"], label_y),
                        xytext=(0, 4), textcoords="offset points",
                        ha="center", va="bottom", fontsize=8 if with_variants else 10,
                        bbox=dict(facecolor="white", edgecolor="none", pad=.2), zorder=4)
        ax.set_ylabel("Concealment rate", labelpad=10)
        ax.set_xticks(range(6), ["Baseline", "H0", "H1", "H2", "H3", "H4"])
        ax.set_xlim(-.55, 5.6)
        ax.set_ylim(0, 107 if with_variants else 100)
        ax.set_yticks(range(0, 101, 20))
        ax.yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
        ax.tick_params(axis="x", length=0, pad=9)
        ax.tick_params(axis="y", length=3, width=.7, pad=6)
        ax.text(0, 1.035, "Error bars: 95% Wilson confidence intervals",
                transform=ax.transAxes, ha="left", va="bottom",
                fontsize=8.5, color="#606060")
        legend = [("baseline", "Baseline"), ("negative", "Original −"), ("positive", "Original +"),
                  ("negative-variant", "B variant −"), ("positive-variant", "B variant +"),
                  ("negative-rewrite", "R rewrite −"), ("positive-rewrite", "R rewrite +")] if with_variants else [
                  ("baseline", "Baseline"), ("negative", "Negative"), ("positive", "Positive")]
        shown = {b["series"] for b in bars}
        ax.legend(handles=[Patch(facecolor=colors[key], label=label, hatch=patterns.get(key.split("-")[-1]),
                                 edgecolor="#414141" if "-" in key else None) for key, label in legend if key in shown],
                  frameon=False, ncol=4 if with_variants else 3, loc="lower right", bbox_to_anchor=(1, 1.015),
                  handlelength=1.1, handletextpad=.5, columnspacing=1.25, fontsize=9 if with_variants else 10)
        if with_variants:
            caption = "Labels show concealed / completed trials. Each bar represents a distinct prompt."
            if dataset.get("requiredReads"):
                caption += f" Includes {dataset['requiredReads']['total']} required-read replacements."
            fig.supxlabel(caption, fontsize=8.5, color="#606060")
        elif any(experiment.get("pooled") for experiment in experiments.values()):
            fig.supxlabel("Baseline: 60 trials · H0–H4: 30 trials per direction (10 original + 20 follow-up)", fontsize=8.5, color="#606060")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        svg = args.output_dir / "concealment.svg"
        png = args.output_dir / "concealment.png"
        fig.savefig(svg, metadata={"Date": None, "Creator": f"Matplotlib {matplotlib.__version__}"})
        fig.savefig(png, dpi=220)
        plt.close(fig)
        metadata = dict(renderer=f"Matplotlib {matplotlib.__version__}", dataset_version=dataset["version"],
                        bars=bars, baseline_reference=baseline_reference,
                        svg_sha256=hashlib.sha256(svg.read_bytes()).hexdigest(),
                        png_sha256=hashlib.sha256(png.read_bytes()).hexdigest())
        (args.output_dir / "concealment-data.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf8")
        print(f"Rendered {len(bars)} bars with {metadata['renderer']}: {svg} and {png}")


if __name__ == "__main__":
    main()
