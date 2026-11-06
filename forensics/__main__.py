"""Run with python -m forensics --help from the project root."""

import argparse
import json
import sys
from pathlib import Path

from . import workflow as w
from .prompts import ASSETS, map_ideas
from .review import export_prompt, export_review
from .runner import Client, run_batch
from .storage import Study, read, write


def parser():
    p = argparse.ArgumentParser(description="Behavior-first evaluation tampering experiments")
    p.add_argument("--study", default="studies/main", help="Study directory (default: studies/main)")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create a study with configurable R1/V4 Pro model entries")
    c = commands.add_parser("configure", help="Apply a JSON object of settings; plans snapshot their settings")
    c.add_argument("file")
    c = commands.add_parser("hypotheses", help="Import a JSON array of hypothesis definitions")
    c.add_argument("file")
    c = commands.add_parser("map", help="Find prompt chunks linked to a hypothesis, without an API call")
    c.add_argument("hypothesis")
    c = commands.add_parser("plan", help="Create immutable experiment and prompt diff from JSON")
    c.add_argument("file")
    c.add_argument("--editor", choices=["r1", "v4-pro"], help="Optional API model to propose minimal exact edits")
    c = commands.add_parser("prompt", help="Export prompt and edits for review")
    c.add_argument("experiment")
    c = commands.add_parser("approve", help="Record review of the experiment design and edited prompt")
    c.add_argument("experiment")
    c.add_argument("--reviewer", required=True)
    c = commands.add_parser("run", help="Run/resume an approved batch; live requests incur provider charges")
    c.add_argument("experiment")
    c.add_argument("--retry-failed", action="store_true", help="Explicitly retry failed/incomplete slots, retaining every prior attempt")
    c.add_argument("--workers", type=int, default=1, help="Concurrent isolated trials (1-16; default 1)")
    c = commands.add_parser("review", help="Export offline transcript viewer with highlights and labels")
    c.add_argument("experiment")
    c = commands.add_parser("annotate", help="Import downloaded JSON annotations")
    c.add_argument("file")
    c.add_argument("--reviewer", required=True)
    c = commands.add_parser("sample", help="Select reproducible 15+15 outcome review samples")
    c.add_argument("experiment")
    c.add_argument("--seed", type=int, default=0)
    c = commands.add_parser("score", help="Compute supported runs and baseline-adjusted scores")
    c.add_argument("experiment")
    c = commands.add_parser("pair", help="Rank screens and propose all nonzero hypothesis pairs")
    c.add_argument("round")
    c.add_argument("experiments", nargs="+")
    c = commands.add_parser("revise-pair", help="Resolve conflicts before confirming a synthesized round")
    c.add_argument("hypothesis")
    c.add_argument("file")
    c = commands.add_parser("approve-round", help="Confirm synthesized hypotheses before their next round")
    c.add_argument("round")
    c.add_argument("--reviewer", required=True)
    c = commands.add_parser("validate", help="Require at least three independent, supported changes")
    c.add_argument("hypothesis")
    c.add_argument("experiments", nargs="+")
    c = commands.add_parser("conclude", help="Record a conclusion and score it against paper or behavior")
    c.add_argument("file")
    c = commands.add_parser("release-reasoning", help="Record post-conclusion access to archived reasoning")
    c.add_argument("conclusion")
    commands.add_parser("status", help="Show batch progress and missing labels without reading reasoning")
    commands.add_parser("doctor", help="Check local runtime and credential presence, without API requests")
    commands.add_parser("demo", help="Create an offline synthetic demonstration in a NEW study directory")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            study = Study.create(args.study)
            write(study.root / "paper_reference.json", read(ASSETS / "paper_reference.json"))
            result = {"study": str(study.root), "next": "Review study.json and baseline_prompt.json, then plan experiments"}
        elif args.command == "demo":
            from .demo import demo
            result = demo(args.study)
        else:
            study = Study(args.study)
            with study.lock():
                result = dispatch(args, study)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


def dispatch(args, study):
    command = args.command
    if command == "configure":
        return w.configure(study, read(args.file))
    if command == "hypotheses":
        return w.add_hypotheses(study, read(args.file))
    if command == "map":
        h = study.get("hypotheses", args.hypothesis)
        return map_ideas(read(study.root / "baseline_prompt.json"), h["text"])
    if command == "plan":
        editor = Client(study.config["models"][args.editor], archive_dir=study.root / "sealed" / "editor") if args.editor else None
        experiment = w.plan(study, read(args.file), editor)
        return {"id": experiment["id"], **export_prompt(study, experiment["id"])}
    if command == "prompt":
        return export_prompt(study, args.experiment)
    if command == "approve":
        return w.approve(study, args.experiment, args.reviewer)
    if command == "run":
        experiment = study.get("experiments", args.experiment)
        if experiment["synthetic"]:
            raise ValueError("Synthetic experiments are run only by demo/tests, never against a live model")
        if experiment.get("baseline"):
            w.complete_runs(study, study.get("experiments", experiment["baseline"]), experiment["expectation"].get("metric", "concealed"))
        return run_batch(study, args.experiment, retry_failed=args.retry_failed, workers=args.workers)
    if command == "review":
        return export_review(study, args.experiment)
    if command == "annotate":
        return w.annotate(study, read(args.file), args.reviewer)
    if command == "sample":
        return w.review_sample(study, args.experiment, args.seed)
    if command == "score":
        return w.score_experiment(study, args.experiment)
    if command == "pair":
        return w.pair(study, args.experiments, args.round)
    if command == "revise-pair":
        return w.revise_pair(study, args.hypothesis, read(args.file))
    if command == "approve-round":
        return w.approve_round(study, args.round, args.reviewer)
    if command == "validate":
        return w.validate(study, args.hypothesis, args.experiments)
    if command == "conclude":
        return w.conclude(study, read(args.file))
    if command == "release-reasoning":
        return w.release_reasoning(study, args.conclusion)
    if command == "status":
        return [{"id": e["id"], "model": e["model"], "kind": e["kind"], "approved": bool(e["approval"]),
                 "requested": e["count"], **w.rate(w.experiment_runs(study, e))} for e in study.all("experiments")]
    if command == "doctor":
        import os
        import shutil
        import subprocess
        docker = shutil.which("docker")
        ready = False
        if docker:
            try:
                ready = subprocess.run([docker, "image", "inspect", study.settings["docker_image"]], capture_output=True, timeout=15).returncode == 0
            except subprocess.TimeoutExpired:
                pass
        return {"python": sys.version.split()[0], "docker_installed": bool(docker), "docker_image_ready": ready,
                "credentials_present": {name: bool(os.getenv(config["api_key_env"])) for name, config in study.config["models"].items()},
                "live_ready": ready and all(os.getenv(config["api_key_env"]) for config in study.config["models"].values())}
    raise ValueError("Unknown command")


if __name__ == "__main__":
    raise SystemExit(main())
