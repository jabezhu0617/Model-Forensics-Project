"""Atomic local records. Public evidence and sealed provider responses live separately."""

import contextlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .prompts import baseline, digest


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value):
        raise ValueError("IDs must use 1–96 letters, digits, underscores or hyphens")
    return value


DEFAULTS = {
    "baseline_runs": 60, "review_per_outcome": 15, "screen_runs": 10,
    "pilot_runs": 30, "validation_runs": 30, "validation_min_changes": 3,
    "screen_scoring": "paired", "screen_strong_change": 0.30,
    "screen_strong_inclusive": True,
    "screen_strong_above": 3, "conclusion_baseline_above": 0.50,
    "conclusion_increase_above": 0.25, "conclusion_decrease_above": 0.25,
    "change_unit": "percentage_points", "max_steps": 20, "max_tokens": 16000,
    "docker_image": "python:3.11-slim", "command_timeout": 30,
}

MODELS = {
    "r1": {"family": "r1", "provider": "openrouter", "model": "deepseek/deepseek-r1-0528",
           "base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY",
           "extra": {"reasoning": {"effort": "high", "exclude": False},
                     "provider": {"require_parameters": True}}},
    "v4-pro": {"family": "v4-pro", "provider": "deepseek", "model": "deepseek-v4-pro",
               "base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY",
               "extra": {"thinking": {"type": "enabled"}, "reasoning_effort": "high"}},
}


class Study:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config = read(self.root / "study.json")
        self.settings = self.config["settings"]

    @classmethod
    def create(cls, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        if (root / "study.json").exists():
            raise ValueError("Study already exists")
        write(root / "study.json", {"schema": 1, "created": now(), "settings": DEFAULTS, "models": MODELS})
        write(root / "baseline_prompt.json", baseline())
        return cls(root)

    def path(self, kind, key):
        if kind not in {"experiments", "runs", "hypotheses", "annotations", "conclusions", "rounds"}:
            raise ValueError("Unknown record kind")
        return self.root / kind / (identifier(key) + ".json")

    def get(self, kind, key):
        return read(self.path(kind, key))

    def put(self, kind, key, value, *, new=False):
        path = self.path(kind, key)
        if new and path.exists():
            raise ValueError(f"{kind}/{key} already exists; use a new ID")
        write(path, value)

    def all(self, kind):
        return [read(path) for path in sorted((self.root / kind).glob("*.json"))]

    def runs(self, experiment):
        latest = {}
        for run in self.attempts(experiment):
            slot = run.get("index", run["id"])
            if slot not in latest or run.get("attempt", 1) > latest[slot].get("attempt", 1):
                latest[slot] = run
        return sorted(latest.values(), key=lambda run: run["id"])

    def attempts(self, experiment):
        return [run for run in self.all("runs") if run["experiment"] == experiment]

    def audit(self, action, **details):
        with (self.root / "audit.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": now(), "action": action, **details}) + "\n")

    @contextlib.contextmanager
    def lock(self):
        """Single writer, including across model batches; stale lock never silently removed."""
        path = self.root / ".writer.lock"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            raise ValueError("Study is locked by another writer. After a crash, verify it stopped before removing .writer.lock") from None
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            yield
        finally:
            path.unlink(missing_ok=True)

    def verify_experiment(self, experiment):
        if experiment["prompt_hash"] != digest(experiment["prompt"]):
            raise ValueError("Experiment prompt was modified after creation; create a new experiment")
        if experiment.get("approval_hash") != digest({k: v for k, v in experiment.items()
                                                      if k not in {"approval", "approval_hash"}}):
            raise ValueError("Experiment is unapproved or changed after approval")

    def public_run(self, run):
        result = dict(run)
        annotation_path = self.path("annotations", run["id"])
        if annotation_path.exists():
            annotation = read(annotation_path)
            result["annotation"] = annotation
            if annotation.get("outcome"):
                result["outcome"] = annotation["outcome"]
        return result
