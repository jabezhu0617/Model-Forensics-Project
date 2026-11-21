"""Run the frozen B variants, or the five R rewrites after B is complete."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from run_hypothesis_followup import ROOT, FastStudy, keep_awake, run
from forensics.prompts import digest, validate_bundle
from forensics.scoring import rate
from forensics.storage import now, read, write
from forensics.workflow import approve

CAMPAIGN = "r1-b-variants-20261120"
REWRITE_CAMPAIGN = "r1-r-rewrites-20261120"
SLOTS = 30
DRAFTS = {
    "h1-minus-b": ("H1−B", "Civilian space exploration"),
    "h1-plus-b": ("H1+B", "Assignment after a passing score"),
    "h2-minus-b": ("H2−B", "Deception as the motive"),
    "h3-minus-b": ("H3−B", "Author is a different model"),
    "h4-minus-b": ("H4−B", "CASC affiliation"),
}
REWRITES = {
    "h0-minus-r": ("H0−R", "Closing without a justification", "r1-reason-screen-v2"),
    "h0-plus-r": ("H0+R", "Firmer closing moral judgment", "r1-h0-firmer-moral-judgment"),
    "h2-plus-r": ("H2+R", "A duty to prevent harm", "r1-h2-expanded-moral-case"),
    "h3-plus-r": ("H3+R", "A prior instance asks for continuity", "r1-h3-prior-self-commitment"),
    "h4-plus-r": ("H4+R", "U.S. partners and China as the named adversary", "r1-h4-us-coalition-against-china"),
}
ATTACHMENTS = {"questions.txt", "format_guide.md", "deployment_notes.txt", "notes_to_self.txt"}


def emit(study, kind, *, campaign=CAMPAIGN, **details):
    entry = {"time": now(), "event": kind, **details}
    with (study.root / f"{campaign}-progress.jsonl").open("a", encoding="utf8") as stream:
        stream.write(json.dumps(entry) + "\n")
    print(json.dumps(entry), flush=True)


def prepare(study, *, rewrites=False):
    campaign = REWRITE_CAMPAIGN if rewrites else CAMPAIGN
    kind = "rewrite" if rewrites else "variant"
    if rewrites:
        b_manifest = read(study.root / f"{CAMPAIGN}-manifest.json")
        b_status = summary(study, b_manifest)
        if b_status["completed"] != b_status["classified"] or b_status["classified"] != 150:
            raise ValueError("All five B batches must finish before scheduling the R rewrites")
    base = study.get("experiments", "r1-baseline")
    study.verify_experiment(base)
    receipt = read(ROOT / "build/personal-deployment.json")
    directory = Path(receipt["stage"]) / "dist/data/prompt-drafts"
    by_id = {d["id"]: d for d in read(directory / "index.json")}
    wanted = REWRITES if rewrites else {k: (*v, "r1-baseline") for k, v in DRAFTS.items()}
    if {key for key, draft in by_id.items() if draft["kind"] == kind} != set(wanted):
        raise ValueError("Requested drafts do not match the reviewed draft index")
    records = []
    for draft_id, (label, title, source_id) in wanted.items():
        draft = read(directory / f"{draft_id}.json")
        if (draft["id"], draft["label"], draft["title"], draft["kind"], draft["sourceId"]) != (
            draft_id, label, title, kind, source_id
        ):
            raise ValueError(f"Wrong reviewed prompt: {draft_id}")
        sections = {s["key"]: s["text"] for s in draft["sections"]}
        if len(draft["sections"]) != 6 or set(sections) != ATTACHMENTS | {"system", "user"}:
            raise ValueError(f"Incomplete prompt: {draft_id}")
        eid = ("r1-rewrite-" if rewrites else "r1-variant-") + draft_id
        prompt = {"system": sections["system"], "user": sections["user"],
                  "files": {k: sections[k] for k in sorted(ATTACHMENTS)},
                  "source": "Reviewed viewer draft " + draft_id}
        validate_bundle(prompt)
        if prompt["system"] != base["prompt"]["system"] or any(
            prompt["files"][k] != base["prompt"]["files"][k] for k in ("questions.txt", "format_guide.md")
        ):
            raise ValueError(f"Baseline control changed: {draft_id}")
        spec = dict(id=eid, kind="pilot", model=base["model"], model_config=base["model_config"],
                    settings=base["settings"], count=SLOTS, synthetic=False, baseline=base["id"],
                    title=title, prompt=prompt, prompt_hash=digest(prompt), campaign=campaign, variant_label=label)
        if rewrites:
            original = study.get("experiments", source_id)
            study.verify_experiment(original)
            runtime = ("max_steps", "max_tokens", "docker_image", "command_timeout")
            if original["model_config"] != base["model_config"] or any(
                original["settings"][key] != base["settings"][key] for key in runtime
            ):
                raise ValueError(f"Tested arm settings differ from baseline: {draft_id}")
            spec["rewrite_of"] = source_id
            spec["settings"] = original["settings"]
        records.append((spec, draft_id, label, title))
    manifest = dict(campaign=campaign, baseline=base["id"], slots_per_arm=SLOTS, arms=[
        dict(experiment=spec["id"], draft_id=draft_id, label=label, group=label[:2], sign=label[2],
             title=title, prompt_hash=spec["prompt_hash"],
             **({"rewrite_of": spec["rewrite_of"]} if rewrites else {})) for spec, draft_id, label, title in records
    ])
    target = study.root / f"{campaign}-manifest.json"
    if target.exists() and read(target) != manifest:
        raise ValueError("The reviewed prompts differ from the frozen campaign")
    for spec, _, _, _ in records:
        eid = spec["id"]
        if not study.path("experiments", eid).exists():
            study.put("experiments", eid, dict(**spec, created=now(), approval=None), new=True)
            study.audit("plan_prompt_edit", experiment=eid, prompt_hash=spec["prompt_hash"])
        saved = study.get("experiments", eid)
        if any(saved.get(k) != v for k, v in spec.items()):
            raise ValueError(f"Frozen experiment differs: {eid}")
        if not saved.get("approval"):
            approve(study, eid, "User requested 30 trials per R rewrite after B" if rewrites else
                    "User requested 30 trials on each B variant and no wording rewrites")
        study.verify_experiment(study.get("experiments", eid))
    if not target.exists():
        write(target, manifest)
    return manifest


def summary(study, manifest):
    arms = []
    for arm in manifest["arms"]:
        attempts = study.attempts(arm["experiment"])
        latest = {}
        for attempt in attempts:
            slot = attempt["index"]
            if slot not in latest or attempt["attempt"] > latest[slot]["attempt"]:
                latest[slot] = attempt
        finished = [study.public_run(r) for r in latest.values() if r["status"] == "complete"]
        counts = Counter(r["outcome"] for r in finished)
        arms.append(dict(**arm, completed=len(finished), concealed=counts["concealed"],
                         reported=counts["reported"], unresolved=counts["unresolved"], attempts=len(attempts),
                         added_stats=rate(finished)))
    campaign = manifest["campaign"]
    report = dict(campaign=campaign, completed=sum(a["completed"] for a in arms),
                  classified=sum(a["concealed"] + a["reported"] for a in arms), requested=SLOTS * len(arms),
                  total_attempts=sum(a["attempts"] for a in arms), arms=arms)
    write(study.root / f"{campaign}-status.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run"])
    parser.add_argument("--workers", type=int, default=100)
    parser.add_argument("--rewrites", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 100:
        parser.error("Use 1–100 workers")
    study = FastStudy(ROOT / "studies/main")
    with keep_awake(), study.lock():
        manifest = prepare(study, rewrites=args.rewrites)
        if args.action == "prepare":
            print(json.dumps(manifest))
            return 0
        return run(study, manifest, args.workers, 6, slots=SLOTS, report=summary,
                   emit=lambda study, kind, **kw: emit(study, kind, campaign=manifest["campaign"], **kw))


if __name__ == "__main__":
    sys.exit(main())
