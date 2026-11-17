"""Run the authorized, fixed-size H0-H4 follow-up without changing frozen screens.

Each of the ten original arms gets a separate 20-slot pilot. Completed slots
are never rerun; failed attempts remain archived. No provider reasoning is read.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import threading
import traceback
from collections import Counter, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from forensics import workflow
from forensics.prompts import digest
from forensics.runner import Client, DockerSandbox, rollout
from forensics.scoring import rate
from forensics.storage import Study, now, read, write

CAMPAIGN = "r1-h0-h4-followup-20261117"
SOURCES = [
    ("H0", "r1-reason-screen-v2", "r1-h0-firmer-moral-judgment"),
    ("H1", "r1-h1-tutor-selection", "r1-h1-civilian-harm-rescreen"),
    ("H2", "r1-h2-ease-motivation", "r1-h2-expanded-moral-case"),
    ("H3", "r1-h3-external-author", "r1-h3-prior-self-commitment"),
    ("H4", "r1-h4-china-affiliation", "r1-h4-us-coalition-against-china"),
]
REVIEWER = "User authorized 20 additional trials for each H0-H4 positive and negative arm on November 17, 2026"
STARTS = threading.BoundedSemaphore(6)


class FastStudy(Study):
    def attempts(self, experiment):
        return [r for p in sorted((self.root / "runs").glob(experiment + "-*.json"))
                if (r := read(p))["experiment"] == experiment]


class TrialSandbox(DockerSandbox):
    def start(self, files):
        with STARTS:
            super().start(files)


class DeadlineClient(Client):
    """Provider keepalive streams must not evade an absolute request deadline."""
    def complete(self, messages, tools=None):
        payload = dict(config=self.config, max_tokens=self.max_tokens, messages=messages, tools=tools)
        try:
            response = subprocess.run([sys.executable, str(ROOT / "scripts/followup_request.py")],
                                      input=json.dumps(payload).encode("utf8"), capture_output=True, timeout=600)
        except subprocess.TimeoutExpired:
            raise TimeoutError("Provider request exceeded the 600-second wall-clock deadline") from None
        if response.returncode:
            safe_error = response.stderr.decode("utf8", errors="replace")
            code = re.search(r"Provider HTTP (401|402|403|404|429|500|502|503|504)", safe_error)
            raise RuntimeError(code.group() if code else "Provider request failed in isolated request process")
        return json.loads(response.stdout)


@contextmanager
def keep_awake():
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    try:
        yield
    finally:
        if os.name == "nt":
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


def event(study, kind, **details):
    item = {"time": now(), "event": kind, **details}
    with (study.root / (CAMPAIGN + "-progress.jsonl")).open("a", encoding="utf8") as stream:
        stream.write(json.dumps(item) + "\n")
    print(json.dumps(item), flush=True)


def prepare(study):
    baseline = study.get("experiments", "r1-baseline")
    study.verify_experiment(baseline)
    workflow.complete_runs(study, baseline)
    arms = []
    for group, negative, positive in SOURCES:
        for direction, source_id in [("decrease", negative), ("increase", positive)]:
            original = study.get("experiments", source_id)
            study.verify_experiment(original)
            workflow.complete_runs(study, original)
            assert original["count"] == 10
            assert original["expectation"]["direction"] == direction
            eid = f"{CAMPAIGN}-{group.lower()}-{direction}"
            if not study.path("experiments", eid).exists():
                followup = workflow.plan(study, dict(
                    id=eid, kind="pilot", model=original["model"], count=20,
                    baseline=original["baseline"], hypothesis=original["hypothesis"],
                    expectation=original["expectation"], edits=original["edits"]))
                followup.update(replication_of=source_id, replication_campaign=CAMPAIGN,
                                original_experiment_hash=digest(original))
                study.put("experiments", eid, followup)
            followup = study.get("experiments", eid)
            assert followup["count"] == 20 and followup["replication_of"] == source_id
            assert followup["original_experiment_hash"] == digest(original)
            assert followup["prompt"] == original["prompt"]
            assert followup["prompt_hash"] == original["prompt_hash"]
            assert followup["model_config"] == original["model_config"]
            for key in ("max_steps", "max_tokens", "docker_image", "command_timeout"):
                assert followup["settings"][key] == original["settings"][key]
            if not followup.get("approval"):
                workflow.approve(study, eid, REVIEWER)
                followup = study.get("experiments", eid)
            study.verify_experiment(followup)
            arms.append(dict(group=group, direction=direction, original=source_id,
                             experiment=eid, prompt_hash=original["prompt_hash"]))
    manifest = dict(id=CAMPAIGN, baseline="r1-baseline", additional_per_arm=20,
                    original_per_arm=10, target_per_arm=30, arms=arms,
                    interval_method="Two-sided 95% Wilson score, no continuity correction",
                    original_screen_scores="Preserved; pooled follow-up rates are not rescored as ten-trial screens")
    target = study.root / (CAMPAIGN + "-manifest.json")
    if target.exists():
        assert read(target) == manifest
    else:
        write(target, manifest)
        study.audit("authorize_followup", campaign=CAMPAIGN, reviewer=REVIEWER, slots=200)
    return manifest


def summary(study, manifest):
    arms = []
    for arm in manifest["arms"]:
        original = [study.public_run(r) for r in study.runs(arm["original"])]
        added = [study.public_run(r) for r in study.runs(arm["experiment"])]
        arms.append(dict(**arm, original_stats=rate(original), added_stats=rate(added),
                         pooled_stats=rate(original + added),
                         completed=sum(r["status"] == "complete" for r in added),
                         attempts=len(study.attempts(arm["experiment"]))))
    result = dict(campaign=CAMPAIGN, updated=now(), arms=arms,
                  completed=sum(a["completed"] for a in arms),
                  classified=sum(a["added_stats"]["labeled"] for a in arms),
                  total_attempts=sum(a["attempts"] for a in arms), requested=200)
    write(study.root / (CAMPAIGN + "-status.json"), result)
    return result


def run_slot(study, experiment, index, attempt):
    return rollout(study, experiment, index,
                   DeadlineClient(experiment["model_config"], experiment["settings"]["max_tokens"]),
                   TrialSandbox(experiment["settings"]), attempt)


def run(study, manifest, workers, max_attempts):
    DockerSandbox.preflight("python:3.11-slim")
    Client(study.config["models"]["r1"])
    experiments = {a["experiment"]: study.get("experiments", a["experiment"]) for a in manifest["arms"]}
    prior = {key: {r["index"]: r for r in study.runs(key)} for key in experiments}
    jobs = deque()
    for index in range(1, 21):
        for eid, experiment in experiments.items():
            previous = prior[eid].get(index)
            if previous and previous["status"] == "complete":
                continue
            if previous and previous["status"] == "running":
                raise ValueError("Verify interrupted attempt before resuming: " + previous["id"])
            attempt = previous["attempt"] + 1 if previous else 1
            if attempt <= max_attempts:
                jobs.append((experiment, index, attempt))
    notified = set()
    done = sum(sum(r["status"] == "complete" for r in rows.values()) for rows in prior.values())
    counts = Counter({eid: sum(r["status"] == "complete" for r in rows.values()) for eid, rows in prior.items()})
    event(study, "started", workers=workers, remaining=len(jobs), requested=200)
    active, stopped = {}, False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        try:
            while active or (jobs and not stopped):
                while jobs and len(active) < workers and not stopped:
                    exp, index, attempt = jobs.popleft()
                    if attempt > 1:
                        study.audit("retry", experiment=exp["id"], index=index, attempt=attempt)
                    active[pool.submit(run_slot, study, exp, index, attempt)] = exp, index, attempt
                ready, _ = wait(active, timeout=30, return_when=FIRST_COMPLETED)
                if not ready:
                    event(study, "heartbeat", completed=done, active=len(active), queued=len(jobs))
                for future in ready:
                    exp, index, attempt = active.pop(future)
                    try:
                        record = future.result()
                    except Exception as error:
                        # Container cleanup can time out after the completed transcript
                        # has already been saved. Recover that slot, never rerun it.
                        run_id = f"{exp['id']}-{index:04d}" + (f"-retry{attempt}" if attempt > 1 else "")
                        path = study.path("runs", run_id)
                        if not path.exists():
                            raise
                        record = read(path)
                        if record["status"] not in {"complete", "failed", "incomplete"}:
                            raise
                        event(study, "worker_cleanup_error", run=run_id, error_type=type(error).__name__)
                    if record["status"] == "complete":
                        assert record["transcript_hash"] == digest(record["messages"])
                        done += 1
                        counts[exp["id"]] += 1
                    else:
                        path = study.root / "sealed" / record["id"] / "error.json"
                        message = read(path).get("message", "") if path.exists() else ""
                        if re.search(r"Provider HTTP (401|402|403|404)", message):
                            stopped = True
                            event(study, "provider_blocked", action="draining active trials; credentials/model/balance need attention")
                        elif attempt < max_attempts:
                            jobs.append((exp, index, attempt + 1))
                    event(study, "trial_finished", completed=done, run=record["id"],
                          status=record["status"], outcome=record["outcome"])
                    if counts[exp["id"]] == 20 and exp["id"] not in notified:
                        notified.add(exp["id"])
                        arm = next(a for a in manifest["arms"] if a["experiment"] == exp["id"])
                        stats = summary(study, manifest)
                        event(study, "arm_batch_complete", **next(a for a in stats["arms"] if a["experiment"] == exp["id"]))
                if ready:
                    summary(study, manifest)
        except BaseException:
            traceback.print_exc()
            raise
    stats = summary(study, manifest)
    event(study, "finished", completed=stats["completed"], classified=stats["classified"],
          total_attempts=stats["total_attempts"])
    return 0 if stats["completed"] == stats["classified"] == 200 else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run", "status"])
    parser.add_argument("--workers", type=int, default=100)
    parser.add_argument("--max-attempts", type=int, default=6)
    args = parser.parse_args()
    if not 1 <= args.workers <= 100 or not 1 <= args.max_attempts <= 6:
        parser.error("Use 1-100 workers and 1-6 attempts")
    study = FastStudy(ROOT / "studies/main")
    if args.action == "status":
        result = summary(study, read(study.root / (CAMPAIGN + "-manifest.json")))
        print(json.dumps(result, indent=2))
        return 0
    with keep_awake(), study.lock():
        manifest = prepare(study)
        if args.action == "run":
            return run(study, manifest, args.workers, args.max_attempts)
        print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
