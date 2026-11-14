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
    dataset = json.loads(args.input.read_text())
    experiments = {item["id"]: item for item in dataset["experiments"]}
    bars = []

    def add(experiment: dict, group: str, series: str, x: float) -> None:
        count, total = experiment["counts"]["concealed"], len(experiment["runs"])
        if total == 0:
            raise ValueError(f"No recorded trials for {experiment['id']}")
        bars.append(dict(experiment=experiment["id"], group=group, series=series,
                         count=count, total=total, rate=count / total * 100, x=x))

    add(experiments["r1-baseline"], "Baseline", "baseline", 0)
    for i in range(5):
        label = f"H{i}"
        hypothesis = next(h for h in dataset["hypotheses"] if h["id"] == label and h["round"] == 0)
        for sign, series, offset in [("−", "negative", -.18), ("+", "positive", .18)]:
            experiment = next(experiments[key] for key in hypothesis["arms"] if experiments[key]["sign"] == sign)
            add(experiment, label, series, i + 1 + offset)

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
        plt.rcParams.update({
            "font.family": "DejaVu Sans", "font.size": 11,
            "svg.fonttype": "path", "svg.hashsalt": "model-forensics-concealment",
            "axes.spines.top": False, "axes.spines.right": False,
            "axes.linewidth": .7, "axes.edgecolor": "#505050",
            "text.color": "#252525", "axes.labelcolor": "#252525",
            "xtick.color": "#404040", "ytick.color": "#404040",
        })
        fig, ax = plt.subplots(figsize=(9.5, 4.25), layout="constrained")
        for item in bars:
            rectangle = ax.bar(item["x"], item["rate"], width=.30,
                               color=colors[item["series"]], linewidth=0)[0]
            rectangle.set_gid(f"bar-{item['group']}-{item['series']}")
            label = f"{item['rate']:.1f}".rstrip("0").rstrip(".") if item["rate"] % 1 else str(int(item["rate"]))
            ax.annotate(f"{label}%", (item["x"], item["rate"]),
                        xytext=(0, 4), textcoords="offset points",
                        ha="center", va="bottom", fontsize=10)
        ax.set_ylabel("Concealment rate", labelpad=10)
        ax.set_xticks(range(6), ["Baseline", "H0", "H1", "H2", "H3", "H4"])
        ax.set_xlim(-.55, 5.6)
        ax.set_ylim(0, 100)
        ax.set_yticks(range(0, 101, 20))
        ax.yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
        ax.tick_params(axis="x", length=0, pad=9)
        ax.tick_params(axis="y", length=3, width=.7, pad=6)
        ax.legend(handles=[Patch(facecolor=colors[key], label=label) for key, label in
                           [("baseline", "Baseline"), ("negative", "Negative"), ("positive", "Positive")]],
                  frameon=False, ncol=3, loc="lower right", bbox_to_anchor=(1, 1.015),
                  handlelength=1.1, handletextpad=.5, columnspacing=1.6, fontsize=10)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        svg = args.output_dir / "concealment.svg"
        png = args.output_dir / "concealment.png"
        fig.savefig(svg, metadata={"Date": None, "Creator": f"Matplotlib {matplotlib.__version__}"})
        fig.savefig(png, dpi=220)
        plt.close(fig)
        metadata = dict(renderer=f"Matplotlib {matplotlib.__version__}", dataset_version=dataset["version"],
                        bars=bars, svg_sha256=hashlib.sha256(svg.read_bytes()).hexdigest(),
                        png_sha256=hashlib.sha256(png.read_bytes()).hexdigest())
        (args.output_dir / "concealment-data.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(f"Rendered {len(bars)} bars with {metadata['renderer']}: {svg} and {png}")


if __name__ == "__main__":
    main()
