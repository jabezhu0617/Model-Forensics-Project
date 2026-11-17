"""Verify and publish completed follow-up evidence into the public viewer export."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from run_hypothesis_followup import CAMPAIGN, ROOT, FastStudy, prepare, summary
from forensics.collection_review import publish_zip_bytes, render_viewer
from forensics.prompts import digest
from forensics.review import export_review
from forensics.storage import read, write
from forensics.workflow import complete_runs


def main():
    study = FastStudy(ROOT / "studies/main")
    with study.lock():
        manifest = prepare(study)
        results = summary(study, manifest)
        if results["completed"] != 200 or results["classified"] != 200:
            raise ValueError("Publish only after all 200 additional slots are complete and classified")
        reports = study.root / "reports"
        viewer = reports / "viewer.html"
        original_html = viewer.read_text(encoding="utf8")
        entries = json.loads(re.search(r'<script\b[^>]*\bid="data"[^>]*>(.*?)</script>', original_html, re.S)[1])
        by_id = {e["experiment"]: e for e in entries}
        additions = []
        for arm in manifest["arms"]:
            experiment = study.get("experiments", arm["experiment"])
            rows = complete_runs(study, experiment)
            assert len(rows) == 20 and len({r["id"] for r in rows}) == 20
            for row in rows:
                assert row["transcript_hash"] == digest(row["messages"])
                assert row["prompt_hash"] == arm["prompt_hash"]
                assert row["experiment"] == arm["experiment"]
            source = by_id[arm["original"]]
            source_records = json.loads(re.search(r'<script\b[^>]*\bid="records"[^>]*>(.*?)</script>', source["pages"]["transcripts"], re.S)[1])
            assert len(source_records) == 10
            assert {(r["id"], r["transcript_hash"], r["outcome"]) for r in source_records} == {
                (r["id"], r["transcript_hash"], r["outcome"]) for r in complete_runs(study, study.get("experiments", arm["original"]))}
            views = export_review(study, experiment["id"])
            sign = "+" if arm["direction"] == "increase" else "−"
            additions.append(dict(
                id="main/" + experiment["id"], experiment=experiment["id"], study="main",
                display_name=arm["group"] + sign + " — Twenty-trial follow-up",
                title=source["title"], arm=None, runs=20, requested=20, approved=True,
                synthetic=False, replication_of=arm["original"], replication_campaign=CAMPAIGN,
                prompt_hash=experiment["prompt_hash"],
                pages={key: Path(views[path_key]).read_text(encoding="utf8")
                       for key, path_key in [("summary", "review"), ("transcripts", "transcripts"), ("inputs", "inputs")]}))
        existing_followups = {e["experiment"] for e in additions}
        entries = [e for e in entries if e["experiment"] not in existing_followups] + additions
        report_stem = CAMPAIGN + "-results"
        write(reports / (report_stem + ".json"), {**manifest, **results})
        lines = ["# H0–H4 follow-up: thirty trials per direction", "",
                 "The original ten-trial screens are preserved. Each arm received twenty additional independent slots using its identical frozen prompt, model configuration and runtime settings. The baseline remains 20/60. All 200 additional slots are complete and classified.", "",
                 "Intervals are two-sided 95% Wilson score intervals without continuity correction, calculated separately for each pooled arm. These are exploratory, nominal per-arm intervals; they do not establish causal effects or simultaneous significance. Original screening scores are not recalculated from the pooled data.", "",
                 "| Arm | Original concealed | New concealed | Pooled concealed | 95% interval | New attempts |",
                 "|---|---:|---:|---:|---:|---:|"]
        for arm in results["arms"]:
            old, added, pooled = arm["original_stats"], arm["added_stats"], arm["pooled_stats"]
            lo, hi = pooled["wilson_95"]
            sign = "+" if arm["direction"] == "increase" else "−"
            lines.append(f"| {arm['group']}{sign} | {old['successes']}/10 | {added['successes']}/20 | {pooled['successes']}/30 ({pooled['rate']:.1%}) | {lo:.1%}–{hi:.1%} | {arm['attempts']} |")
        lines += ["", f"Total additional attempts, including preserved retries: {results['total_attempts']}.", "",
                  "Every latest slot is counted once. Completed slots were not rerun. Invalid/incomplete attempts are retained separately and do not count as reporting outcomes. Public exports include observable messages and final submissions; provider reasoning remains sealed.", ""]
        (reports / (report_stem + ".md")).write_text("\n".join(lines), encoding="utf8")
        hypothesis_doc = ROOT / "hypotheses.md"
        hypothesis_text = hypothesis_doc.read_text(encoding="utf8")
        section = ["<!-- h0-h4-followup:start -->", "## November 17 follow-up: thirty trials per direction", "",
                   "Each original arm received twenty additional trials with the same frozen prompt and model settings. The rates below pool all thirty slots. Original ten-trial screening scores above are preserved as historical screening results. The two-sided 95% Wilson intervals describe each rate separately.", "",
                   "| Hypothesis | − concealed | − 95% interval | + concealed | + 95% interval |",
                   "|---|---:|---:|---:|---:|"]
        for group in [f"H{i}" for i in range(5)]:
            negative, positive = [next(a["pooled_stats"] for a in results["arms"]
                                      if a["group"] == group and a["direction"] == direction)
                                  for direction in ["decrease", "increase"]]
            interval = lambda stats: "–".join(f"{v:.1%}" for v in stats["wilson_95"])
            section.append(f"| {group} | {negative['successes']}/30 ({negative['rate']:.1%}) | {interval(negative)} | {positive['successes']}/30 ({positive['rate']:.1%}) | {interval(positive)} |")
        section += ["", f"[Full follow-up report](studies/main/reports/{report_stem}.md). The baseline remains 20/60. Separate original and follow-up batches and all retry attempts remain available for review.", "<!-- h0-h4-followup:end -->", ""]
        block = "\n".join(section)
        if "<!-- h0-h4-followup:start -->" in hypothesis_text:
            hypothesis_text = re.sub(r'<!-- h0-h4-followup:start -->.*?<!-- h0-h4-followup:end -->\n?', block, hypothesis_text, flags=re.S)
        else:
            hypothesis_text = hypothesis_text.replace("## Input review", block + "\n## Input review", 1)
        hypothesis_doc.write_text(hypothesis_text, encoding="utf8")
        temporary = viewer.with_suffix(".tmp")
        temporary.write_text(render_viewer(entries), encoding="utf8")
        os.replace(temporary, viewer)
        archive = reports / "viewer-laptop.zip"
        temporary = archive.with_suffix(".tmp")
        with ZipFile(archive) as old, ZipFile(temporary, "w", ZIP_DEFLATED) as new:
            replacements = {"viewer.html": viewer, "hypotheses.md": hypothesis_doc, report_stem + ".md": reports / (report_stem + ".md"),
                            report_stem + ".json": reports / (report_stem + ".json")}
            for name in ["research-focus.json", "archive/README.md", "archive/combination-hypotheses.md"]:
                if (ROOT / name).exists():
                    replacements[name] = ROOT / name
            for name in old.namelist():
                if name not in replacements:
                    new.writestr(name, old.read(name))
            for name, path in replacements.items():
                new.write(path, name)
        with ZipFile(temporary) as check:
            assert check.testzip() is None
        os.replace(temporary, archive)
        (ROOT / "viewer-laptop.zip").write_bytes(archive.read_bytes())
        publish_zip_bytes(archive)
        study.audit("publish_followup_export", campaign=CAMPAIGN, slots=200, entries=len(entries))
        print(json.dumps(dict(experiments=len(entries), additional_slots=200,
                              total_attempts=results["total_attempts"], report=str(reports / (report_stem + ".md")))))


if __name__ == "__main__":
    main()
