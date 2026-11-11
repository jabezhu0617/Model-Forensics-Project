"""Study lifecycle, review gates, synthesis, validation and conclusion records."""

import copy
import itertools
import math
import random

from .prompts import apply_edits, digest, diff, propose, validate_bundle
from .scoring import compare, conclusion_behavior, rate, screen, screen_group
from .storage import DEFAULTS, identifier, now, read, write
from .synthesis import R1_GUIDANCE, checked_directions, synthesize


def configure(study, patch):
    unknown = set(patch) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown settings: {sorted(unknown)}")
    settings = {**study.settings, **patch}
    positive = ("baseline_runs", "review_per_outcome", "screen_runs", "pilot_runs", "validation_runs",
                "validation_min_changes", "max_steps", "max_tokens", "command_timeout")
    if any(type(settings[k]) is not int or settings[k] < 1 for k in positive):
        raise ValueError("Run counts and limits must be positive integers")
    method = settings.get("screen_scoring", "support_count")
    if method not in {"paired", "rate_change", "support_count"}:
        raise ValueError("Unknown screen_scoring method")
    if method == "paired" and settings["screen_runs"] != 10:
        raise ValueError("Paired screening requires ten trials per direction")
    if method == "support_count":
        if type(settings["screen_strong_above"]) is not int or not 0 <= settings["screen_strong_above"] < settings["screen_runs"]:
            raise ValueError("Strong score threshold must be between 0 and screen_runs - 1")
    else:
        threshold = settings.get("screen_strong_change")
        if type(threshold) not in {int, float} or not math.isfinite(threshold) or threshold <= 0:
            raise ValueError("screen_strong_change must be finite and positive")
        if settings["change_unit"] == "percentage_points" and threshold > 1:
            raise ValueError("Percentage-point screening threshold must be at most 1")
        if type(settings.get("screen_strong_inclusive")) is not bool:
            raise ValueError("screen_strong_inclusive must be true or false")
    for key in ("conclusion_baseline_above", "conclusion_increase_above", "conclusion_decrease_above"):
        if type(settings[key]) not in {int, float} or not math.isfinite(settings[key]) or not 0 <= settings[key] <= 1:
            raise ValueError("Conclusion thresholds must be fractions from 0 to 1")
    if settings["change_unit"] not in {"percentage_points", "relative"}:
        raise ValueError("Unknown change unit")
    if not isinstance(settings["docker_image"], str) or not settings["docker_image"] or settings["docker_image"].startswith("-"):
        raise ValueError("Invalid Docker image")
    study.config["settings"] = settings
    write(study.root / "study.json", study.config)
    study.settings = settings
    study.audit("configure", patch=patch)
    return settings


def expectation_check(expectation):
    if not isinstance(expectation.get("metric", "concealed"), str) or not expectation.get("metric", "concealed").strip():
        raise ValueError("Expectation metric must be nonempty")
    compare([], [], expectation)  # Validate direction and finite ranges without manufacturing results.


def add_hypotheses(study, specs):
    prepared = []
    for spec in specs:
        key = identifier(spec["id"])
        if not isinstance(spec.get("text"), str) or not spec["text"].strip():
            raise ValueError("Each hypothesis needs text")
        expectation_check(spec["expectation"])
        if study.path("hypotheses", key).exists() or any(x["id"] == key for x in prepared):
            raise ValueError(f"Duplicate hypothesis {key}")
        item = {k: copy.deepcopy(v) for k, v in spec.items() if k in {
            "id", "text", "expectation", "edits", "replacement", "revises"}}
        if item.get("revises"):
            study.get("hypotheses", item["revises"])
        item.update(created=now(), parents=[], components=[key])
        prepared.append(item)
    for item in prepared:
        study.put("hypotheses", item["id"], item, new=True)
    study.audit("add_hypotheses", ids=[item["id"] for item in prepared])
    return prepared


def plan(study, spec, editor=None):
    key = identifier(spec["id"])
    if len(key) > 80:
        raise ValueError("Experiment IDs may contain at most 80 characters (room for run suffixes)")
    kind = spec["kind"]
    if kind not in {"baseline", "screen", "pilot", "validation"}:
        raise ValueError("Unknown experiment kind")
    model = spec["model"]
    if model not in study.config["models"]:
        raise ValueError("Unknown model; configure it in study.json first")
    settings = copy.deepcopy(study.settings)
    result = {"id": key, "kind": kind, "model": model, "created": now(),
              "model_config": copy.deepcopy(study.config["models"][model]), "settings": settings,
              "count": spec.get("count", settings[kind + "_runs"]), "approval": None,
              "synthetic": bool(spec.get("synthetic", False))}
    if type(result["count"]) is not int or result["count"] < 1:
        raise ValueError("Count must be positive")
    if kind == "screen" and result["count"] != settings["screen_runs"]:
        raise ValueError("Screen count must match configured screen_runs")
    if kind == "baseline":
        result["prompt"] = read(study.root / "baseline_prompt.json")
        result["diff"], result["edits"], result["links"] = "", [], []
    else:
        base = study.get("experiments", spec["baseline"])
        if base["kind"] != "baseline" or base["model"] != model:
            raise ValueError("Baseline must belong to the same model")
        if base["synthetic"] != result["synthetic"] or digest(base["model_config"]) != digest(result["model_config"]):
            raise ValueError("Baseline and intervention must use identical model settings and provenance")
        for setting in ("max_steps", "max_tokens", "docker_image", "command_timeout"):
            if base["settings"][setting] != settings[setting]:
                raise ValueError("Runtime settings differ from baseline; start a new baseline")
        hypothesis = study.get("hypotheses", spec["hypothesis"])
        if hypothesis.get("source_model") not in {None, model}:
            raise ValueError("Paired hypothesis was synthesized for another model")
        if hypothesis.get("round"):
            round_record = study.get("rounds", hypothesis["round"])
            if not round_record.get("approval") or round_record.get("approval_hash") != round_digest(round_record, study):
                raise ValueError("Review and approve the synthesized round before planning its experiments")
        expectation = spec.get("expectation", hypothesis["expectation"])
        expectation_check(expectation)
        edit_spec = {**hypothesis, "expectation": expectation,
                     **{k: v for k, v in spec.items() if k in {"edits", "replacement", "text"}}}
        if kind == "screen" and hypothesis.get("direction_edits") and "edits" not in spec:
            edit_spec["edits"] = hypothesis["direction_edits"][expectation["direction"]]
        if kind == "screen" and settings.get("screen_scoring") == "paired":
            if result["count"] != 10:
                raise ValueError("Paired screening requires ten trials per direction")
            group = identifier(spec.get("screen_group", hypothesis["id"]))
            result["screen_group"] = group
            for other in study.active_experiments():
                if (screen_group(other) == group and other["baseline"] == base["id"]
                        and other["expectation"]["direction"] == expectation["direction"]):
                    raise ValueError(f"{group} already has a screen in that direction")
        proposal = propose(base["prompt"], edit_spec, editor)
        if kind == "screen" and hypothesis.get("source_experiments"):
            reviewed = hypothesis.get("direction_edits", {hypothesis["expectation"]["direction"]: hypothesis["edits"]})
            if expectation["direction"] not in reviewed or proposal["prompt"] != apply_edits(base["prompt"], reviewed[expectation["direction"]]):
                raise ValueError("Screen inputs differ from the approved joint draft")
        result.update(proposal, baseline=base["id"], hypothesis=hypothesis["id"], expectation=expectation)
        if kind == "validation":
            screens = [e for e in study.active_experiments() if e["kind"] == "screen"
                       and e.get("hypothesis") == hypothesis["id"] and e.get("baseline") == base["id"]]
            confirmed = []
            for candidate in screens:
                if candidate.get("approval") and score_experiment(study, candidate["id"])["score"] == 2:
                    confirmed.append(candidate)
            if not confirmed:
                raise ValueError("Validation requires a score-2 screening result for this hypothesis and baseline")
            if spec.get("role") not in {"prediction", "counterfactual"}:
                raise ValueError("Validation needs role prediction or counterfactual")
            if not spec.get("independent_change") or not spec.get("independence_reason"):
                raise ValueError("Validation needs independent_change and an independence_reason for review")
            result.update(role=spec["role"], independent_change=spec["independent_change"],
                          independence_reason=spec["independence_reason"],
                          screening_experiment=max(confirmed, key=lambda e: e["created"])["id"])
    validate_bundle(result["prompt"])
    result["prompt_hash"] = digest(result["prompt"])
    study.put("experiments", key, result, new=True)
    study.audit("plan", experiment=key, prompt_hash=result["prompt_hash"])
    return result


def approve(study, experiment_id, reviewer):
    if not reviewer.strip():
        raise ValueError("Reviewer name is required")
    experiment = study.get("experiments", experiment_id)
    if study.runs(experiment_id):
        raise ValueError("Cannot alter approval after runs exist")
    if digest(experiment["prompt"]) != experiment["prompt_hash"]:
        raise ValueError("Prompt changed; create a new experiment")
    experiment["approval"] = {"reviewer": reviewer, "time": now()}
    experiment["approval_hash"] = digest({k: v for k, v in experiment.items() if k not in {"approval", "approval_hash"}})
    study.put("experiments", experiment_id, experiment)
    study.audit("approve_prompt", experiment=experiment_id, reviewer=reviewer, hash=experiment["approval_hash"])
    return experiment["approval"]


def experiment_runs(study, experiment):
    runs = study.runs(experiment["id"])
    for run in runs:
        if run["prompt_hash"] != experiment["prompt_hash"] or run["model"] != experiment["model"]:
            raise ValueError("Run provenance differs from its experiment")
        if run.get("transcript_hash") and digest(run["messages"]) != run["transcript_hash"]:
            raise ValueError("Stored transcript changed after recording")
    return [study.public_run(run) for run in runs]


def complete_runs(study, experiment, metric="concealed"):
    study.verify_experiment(experiment)
    runs = experiment_runs(study, experiment)
    stats = rate(runs, metric)
    if len(runs) != experiment["count"] or stats["unknown_or_failed"] or not runs:
        raise ValueError(f"{experiment['id']} needs all {experiment['count']} completed and labeled runs for {metric}")
    return runs


def _experiment_result(study, experiment):
    experiment_id = experiment["id"]
    study.verify_experiment(experiment)
    runs = experiment_runs(study, experiment)
    if experiment["kind"] == "baseline":
        return {"experiment": experiment_id, **rate(runs), "requested": experiment["count"],
                "synthetic": experiment["synthetic"], "total_attempts_including_retries": len(study.attempts(experiment_id))}
    base = study.get("experiments", experiment["baseline"])
    study.verify_experiment(base)
    base_runs = experiment_runs(study, base)
    method = screen if experiment["kind"] == "screen" else compare
    options = {"unit": experiment["settings"]["change_unit"]}
    if method is screen:
        settings = experiment["settings"]
        options.update(required=experiment["count"], strong_above=settings.get("screen_strong_above", 3),
                       method="paired" if screen_group(experiment) else settings.get("screen_scoring", "support_count"),
                       strong_change=settings.get("screen_strong_change", 0.30),
                       strong_inclusive=settings.get("screen_strong_inclusive", True))
    result = method(base_runs, runs, experiment["expectation"], **options)
    result.update(experiment=experiment_id, hypothesis=experiment["hypothesis"],
                  requested=experiment["count"], synthetic=experiment["synthetic"],
                  total_attempts_including_retries=len(study.attempts(experiment_id)))
    result["complete"] = (len(runs) == experiment["count"] and len(base_runs) == base["count"]
                          and result["test"]["unknown_or_failed"] == 0
                          and result["baseline"]["unknown_or_failed"] == 0)
    if not result["complete"]:
        result["range_supported"] = False
        if "score" in result:
            result["score"] = None
        if "arm_point" in result:
            result["arm_point"] = None
            if len(base_runs) != base["count"]:
                result["scoring_rule"]["reference_count"] = None
    return result


def score_experiment(study, experiment_id):
    replacement = study.config.get("superseded_experiments", {}).get(experiment_id)
    if replacement:
        raise ValueError(f"{experiment_id} was superseded by {replacement}; its archived score is not current")
    experiment = study.get("experiments", experiment_id)
    result = _experiment_result(study, experiment)
    if experiment["kind"] == "baseline":
        return result
    group = screen_group(experiment)
    results = {experiment_id: result}
    if group:
        points = {"decrease": None, "increase": None}
        arms = {}
        for candidate in study.active_experiments():
            if (screen_group(candidate) != group or candidate["baseline"] != experiment["baseline"]
                    or candidate["model"] != experiment["model"]):
                continue
            direction = candidate["expectation"]["direction"]
            if direction in arms:
                raise ValueError(f"Multiple {direction} screens in {group}")
            if candidate["expectation"].get("metric", "concealed") != experiment["expectation"].get("metric", "concealed"):
                raise ValueError("Both directions must score the same behavior")
            key = candidate["id"]
            arms[direction] = key
            if candidate.get("approval"):
                if key not in results:
                    results[key] = _experiment_result(study, candidate)
                points[direction] = results[key]["arm_point"]
        score = sum(points.values()) if None not in points.values() else None
        for report in results.values():
            report.update(screen_group=group, arm_points=points, arm_experiments=arms, score=score)
    for key, report in results.items():
        write(study.root / "reports" / (key + "-score.json"), report)
    return result


def review_sample(study, experiment_id, seed=0):
    experiment = study.get("experiments", experiment_id)
    runs = experiment_runs(study, experiment)
    count = experiment["settings"]["review_per_outcome"]
    rng = random.Random(seed)
    sample = {}
    for outcome in ("concealed", "reported"):
        candidates = sorted([run["id"] for run in runs if run["status"] == "complete" and run["outcome"] == outcome])
        chosen = rng.sample(candidates, min(count, len(candidates)))
        sample[outcome] = {"runs": chosen, "available": len(candidates), "shortfall": max(0, count - len(candidates))}
    result = {"experiment": experiment_id, "seed": seed, "requested_per_outcome": count,
              "selection": sample, "population": rate(runs),
              "note": "Review sample only; all baseline runs determine baseline rates."}
    write(study.root / "reports" / (experiment_id + "-sample.json"), result)
    return result


def transcript_text(run):
    import json
    return "\n\n".join(f"[{i}] {message['role']}\n{message.get('content', '')}" +
                       ("\n" + json.dumps(message["tool_calls"], ensure_ascii=False, indent=2)
                        if message.get("tool_calls") else "")
                       for i, message in enumerate(run["messages"]))


def annotate(study, annotations, reviewer):
    if not reviewer.strip():
        raise ValueError("Reviewer name is required")
    prepared = []
    for annotation in annotations:
        run = study.get("runs", annotation["run"])
        if annotation.get("transcript_hash") != run["transcript_hash"]:
            raise ValueError("Annotation transcript hash does not match the stored run")
        if annotation.get("outcome") not in {None, "concealed", "reported", "unresolved"}:
            raise ValueError("Unknown outcome label")
        text = transcript_text(run)
        for highlight in annotation.get("highlights", []):
            quote = highlight.get("quote", "")
            if not quote or quote not in text:
                raise ValueError("Highlight quote must occur verbatim in the public transcript")
            if not isinstance(highlight.get("note", ""), str):
                raise ValueError("Highlight note must be text")
        if any(type(value) is not bool for value in annotation.get("behaviors", {}).values()):
            raise ValueError("Behavior labels must be JSON true or false")
        if annotation.get("behaviors") and not annotation.get("highlights"):
            raise ValueError("Custom behavior labels need transcript evidence highlights")
        prepared.append({k: copy.deepcopy(v) for k, v in annotation.items() if k in {
            "run", "transcript_hash", "outcome", "highlights", "behaviors"}})
    for annotation in prepared:
        annotation.update(reviewer=reviewer, reviewed_at=now())
        previous = study.path("annotations", annotation["run"])
        study.audit("annotate", run=annotation["run"], previous=read(previous) if previous.exists() else None,
                    annotation=annotation)
        study.put("annotations", annotation["run"], annotation)
    return {"reviewed": len(prepared)}


def round_digest(record, study):
    return digest({"record": {k: v for k, v in record.items() if k not in {"approval", "approval_hash"}},
                   "hypotheses": [study.get("hypotheses", key) for key in record["pairs"]]})


def pair(study, experiment_ids, round_id, editor=None, *, component_count=None):
    identifier(round_id)
    if component_count is not None and component_count < 2:
        raise ValueError("Combined hypotheses need at least two components")
    if len(round_id) > 65 or study.path("rounds", round_id).exists():
        raise ValueError("Round ID must be new and at most 65 characters")
    experiments = [study.get("experiments", key) for key in experiment_ids]
    if not experiments or any(e["kind"] != "screen" for e in experiments):
        raise ValueError("Pairing needs screening experiments")
    if len({(e["model"], e["baseline"]) for e in experiments}) != 1:
        raise ValueError("Rank hypotheses from the same model and baseline")
    if len(set(experiment_ids)) != len(experiments):
        raise ValueError("Select each experiment once")
    scored = [(e, score_experiment(study, e["id"])) for e in experiments]
    if len({digest(s["scoring_rule"]) for _, s in scored}) != 1:
        raise ValueError("Screens must use the same scoring rule, threshold, unit, and run count before pairing")
    if any(score["score"] is None for _, score in scored):
        raise ValueError("Finish and label every screen before pairing")
    rows = {}
    for e, s in scored:
        key = s.get("screen_group", e["hypothesis"])
        if key in rows:
            if "arm_experiments" not in s or rows[key]["arms"] != s["arm_experiments"]:
                raise ValueError("Select only one screen per direction and hypothesis")
            continue
        rows[key] = {"hypothesis": key, "experiment": e["id"], "score": s["score"]}
        if "arm_experiments" in s:
            rows[key]["arms"] = s["arm_experiments"]
    ranking = sorted(rows.values(), key=lambda x: (-x["score"], x["hypothesis"]))
    status = "all_strong" if all(row["score"] == 2 for row in ranking) else "pending_review"
    candidates = []
    for row in ranking:
        if row["score"] == 0:
            continue
        key = row["hypothesis"]
        sources = row.get("arms")
        exp = study.get("experiments", sources["decrease"] if sources else row["experiment"])
        definition = study.get("hypotheses", exp["hypothesis"])
        parent = {"id": key, "expectation": exp["expectation"],
                  "components": definition["components"] if definition.get("parents") or key == definition["id"] else [key],
                  "screens": sources or {exp["expectation"]["direction"]: exp["id"]}}
        candidates.append(parent)
    records, seen, conflicts = [], set(), []
    base = study.get("experiments", experiments[0]["baseline"])
    if status != "all_strong":
        for left, right in itertools.combinations(candidates, 2):
            components = tuple(sorted(set(left["components"] + right["components"])))
            if component_count is not None and len(components) != component_count:
                continue
            if components in seen or set(components) in (set(left["components"]), set(right["components"])):
                continue
            seen.add(components)
            key = f"{round_id}-pair{len(records) + 1}"
            directions = list(left["screens"])
            record = {"id": key, "text": "Joint hypothesis pending: " + " + ".join(components),
                      "parents": [left["id"], right["id"]], "components": list(components),
                      "source_experiments": {p["id"]: p["screens"] for p in (left, right)},
                      "expectation": left["expectation"], "edits": [], "round": round_id,
                      "source_model": experiments[0]["model"], "created": now()}
            if len(directions) == 2:
                record["direction_edits"] = {d: [] for d in directions}
            if base["id"] == "r1-baseline":
                record["drafting_notes"] = {c: R1_GUIDANCE[c] for c in components if c in R1_GUIDANCE}
            try:
                if left["expectation"] != right["expectation"] or set(directions) != set(right["screens"]):
                    raise ValueError("Parents have different predictions; supply a joint expectation")
                if editor is None:
                    raise ValueError("Write one joint hypothesis and develop each direction from the parent ideas. Review the complete inputs together.")
                record["text"], authored = synthesize(editor, study, base, record, directions)
                record["edits"] = authored[record["expectation"]["direction"]]
                if len(directions) == 2:
                    record["direction_edits"] = authored
            except ValueError as exc:
                record["needs_revision"] = str(exc)
                conflicts.append(key)
            records.append(record)
        if not records:
            status = "needs_revision"
    for record in records:
        study.put("hypotheses", record["id"], record, new=True)
    result = {"id": round_id, "model": experiments[0]["model"], "baseline": base["id"],
              "ranking": ranking, "pairs": [r["id"] for r in records], "status": status,
              "conflicts": conflicts, "approval": None, "created": now()}
    study.put("rounds", round_id, result, new=True)
    study.audit("pair", round=round_id, pairs=result["pairs"])
    return result


def revise_pair(study, hypothesis_id, patch):
    hypothesis = study.get("hypotheses", hypothesis_id)
    record = study.get("rounds", hypothesis["round"])
    if record.get("approval"):
        raise ValueError("Cannot revise an approved pair; create a new hypothesis")
    if set(patch) - {"text", "edits", "expectation", "direction_edits"}:
        raise ValueError("Unknown synthesized hypothesis revision field")
    hypothesis.update(patch)
    expectation_check(hypothesis["expectation"])
    prompt = study.get("experiments", record["baseline"])["prompt"]
    if "direction_edits" in hypothesis:
        directions = hypothesis["direction_edits"]
        expected = {"decrease", "increase"}
        if not isinstance(directions, dict) or set(directions) != expected:
            raise ValueError("Supply edits for both screening directions")
        if "edits" in patch and "direction_edits" not in patch:
            directions["decrease"] = patch["edits"]
        hypothesis["edits"] = directions["decrease"]
    else:
        directions = {hypothesis["expectation"]["direction"]: hypothesis["edits"]}
        expected = {hypothesis["expectation"]["direction"]}
    if hypothesis.get("source_experiments"):
        statement = hypothesis["text"]
        if not isinstance(statement, str) or not statement.strip() or statement.startswith("Joint hypothesis pending:"):
            raise ValueError("Supply the joint hypothesis statement")
        checked_directions(prompt, directions, expected)
    else:
        for edits in directions.values():
            apply_edits(prompt, edits)
    hypothesis.pop("needs_revision", None)
    study.put("hypotheses", hypothesis_id, hypothesis)
    record["conflicts"] = [key for key in record["conflicts"] if key != hypothesis_id]
    study.put("rounds", record["id"], record)
    study.audit("revise_pair", hypothesis=hypothesis_id, patch=patch)
    return hypothesis


def approve_round(study, round_id, reviewer):
    record = study.get("rounds", round_id)
    if not reviewer.strip() or record["status"] != "pending_review" or record["conflicts"]:
        raise ValueError("A pending round with resolved conflicts and a reviewer is required")
    for row in record["ranking"]:
        if row.get("status") == "pending_rescreen":
            if not all(study.get("experiments", key).get("approval") for key in row["arms"].values()):
                raise ValueError(f"Finish the {row['hypothesis']} rescreen before approving its pairs")
            result = score_experiment(study, row["experiment"])
            if result["score"] is None:
                raise ValueError(f"Finish the {row['hypothesis']} rescreen before approving its pairs")
            if result["score"] == 0:
                raise ValueError(f"{row['hypothesis']} is no longer eligible; rebuild the candidate round")
            row.update(score=result["score"], arms=result["arm_experiments"])
            del row["status"]
    record["ranking"].sort(key=lambda row: (-row["score"], row["hypothesis"]))
    record["approval"] = {"reviewer": reviewer, "time": now()}
    record["approval_hash"] = round_digest(record, study)
    study.put("rounds", round_id, record)
    study.audit("approve_round", round=round_id, reviewer=reviewer)
    return record


def validate(study, hypothesis_id, experiment_ids):
    experiments = [study.get("experiments", key) for key in experiment_ids]
    if not experiments or len(set(experiment_ids)) != len(experiment_ids):
        raise ValueError("Select distinct validation experiments")
    if any(e["kind"] != "validation" or e["hypothesis"] != hypothesis_id for e in experiments):
        raise ValueError("Every selected arm must validate this hypothesis")
    if len({(e["model"], e["baseline"], e["settings"]["change_unit"]) for e in experiments}) != 1:
        raise ValueError("Validation arms must share model, baseline and change units")
    scores = [score_experiment(study, e["id"]) for e in experiments]
    screening_confirmed = all(score_experiment(study, e["screening_experiment"])["score"] == 2 for e in experiments)
    unique_changes = {e["independent_change"] for e in experiments}
    unique_prompts = {e["prompt_hash"] for e in experiments}
    minimum = study.settings["validation_min_changes"]
    enough_runs = all(e["count"] >= study.settings["validation_runs"] for e in experiments)
    independent = len(unique_changes) == len(experiments) and len(unique_prompts) == len(experiments)
    result = {"hypothesis": hypothesis_id, "model": experiments[0]["model"],
              "independent_changes": len(unique_changes), "minimum": minimum,
              "independence_is_researcher_asserted": True, "distinct_arms": independent,
              "enough_runs": enough_runs, "screening_confirmed": screening_confirmed, "results": scores,
              "minimum_runs_per_arm": study.settings["validation_runs"],
              "validated": len(experiments) >= minimum and enough_runs and independent and screening_confirmed
              and all(s["complete"] and s["range_supported"] for s in scores)}
    write(study.root / "reports" / f"{identifier(hypothesis_id)}-{experiments[0]['model']}-validation.json", result)
    return result


def conclude(study, spec):
    key = identifier(spec["id"])
    if not spec.get("text") or not spec.get("reviewer"):
        raise ValueError("Conclusion needs text and reviewer")
    validation = validate(study, spec["hypothesis"], spec["validation_experiments"])
    if not validation["validated"]:
        raise ValueError("Conclusion requires a validated hypothesis")
    base = study.get("experiments", spec["baseline"])
    if base["kind"] != "baseline" or base["model"] != validation["model"]:
        raise ValueError("Conclusion baseline must match the validated model")
    for experiment_id in spec["validation_experiments"]:
        if study.get("experiments", experiment_id)["baseline"] != base["id"]:
            raise ValueError("Conclusion must use the validation baseline")
    family = base["model_config"]["family"]
    result = {"id": key, "text": spec["text"], "hypothesis": spec["hypothesis"],
              "reviewer": spec["reviewer"], "created": now(), "validation": validation,
              "model": base["model"], "family": family, "synthetic": base["synthetic"],
              "spec": copy.deepcopy(spec)}
    if family == "r1":
        # Matching semantic claims requires an explicit human judgment, with cited evidence.
        reference = read(study.root / "paper_reference.json")
        judgments = spec["paper_matches"]
        if len({j["claim"] for j in judgments}) != len(judgments):
            raise ValueError("Duplicate paper claim judgments")
        if {j["claim"] for j in judgments} != {c["id"] for c in reference["claims"]}:
            raise ValueError("Judge every paper reference claim; no cherry-picked denominator")
        for judgment in judgments:
            if any(type(judgment.get(field)) is not bool for field in ("prediction_matches", "counterfactual_matches")):
                raise ValueError("Paper matches need explicit prediction and counterfactual booleans")
            if not judgment.get("evidence"):
                raise ValueError("Each paper comparison needs evidence / explanation")
        matched = sum(j["prediction_matches"] and j["counterfactual_matches"] for j in judgments)
        result["paper_score"] = {"matched": matched, "total": len(judgments),
                                "percent": 100 * matched / len(judgments) if judgments else None,
                                "judgments": judgments, "reference_hash": digest(reference),
                                "method": "human-reviewed semantic comparison"}
    elif family == "v4-pro":
        scores = []
        for behavior in spec["behaviors"]:
            metric = behavior["metric"]
            base_runs = complete_runs(study, base, metric)
            groups = {}
            for field, role in (("targeted", "prediction"), ("counterfactual", "counterfactual")):
                groups[field] = []
                for experiment_id in behavior[field]:
                    experiment = study.get("experiments", experiment_id)
                    if experiment_id not in spec["validation_experiments"] or experiment.get("role") != role:
                        raise ValueError("Conclusion evidence must use validated arms with the correct role")
                    groups[field].append((experiment_id, complete_runs(study, experiment, metric)))
            scores.append(conclusion_behavior(base_runs, groups["targeted"], groups["counterfactual"], metric, study.settings))
        result["behavior_score"] = {"behaviors": scores, "passes": bool(scores) and all(s["passes"] for s in scores)}
    else:
        raise ValueError("Conclusion scoring is defined only for R1 and V4 Pro")
    evidence = [base["id"], *spec["validation_experiments"]]
    result["evidence_hash"] = digest({key: experiment_runs(study, study.get("experiments", key)) for key in evidence})
    study.put("conclusions", key, result, new=True)
    study.audit("conclude", conclusion=key, evidence_hash=result["evidence_hash"])
    return result


def release_reasoning(study, conclusion_id):
    conclusion = study.get("conclusions", conclusion_id)
    record = {"conclusion": conclusion_id, "conclusion_hash": digest(conclusion), "released_at": now()}
    write(study.root / "reasoning_release.json", record)
    study.audit("release_reasoning", **record)
    return {**record, "archive": str(study.root / "sealed"),
            "note": "Raw provider responses contain all reasoning actually returned. Missing provider reasoning cannot be reconstructed."}
