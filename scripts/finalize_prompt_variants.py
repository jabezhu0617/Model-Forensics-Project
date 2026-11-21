"""Add completed prompt-edit batches without replacing old trial evidence."""
import argparse
import json
import os
import re
from contextlib import nullcontext
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from run_prompt_variants import CAMPAIGN, REWRITE_CAMPAIGN, ROOT, SLOTS, FastStudy, prepare, summary
from forensics.collection_review import publish_zip_bytes, render_viewer
from forensics.review import export_review
from forensics.storage import write
from forensics.workflow import complete_runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rewrites", action="store_true")
    parser.add_argument("--during-rewrites", action="store_true",
                        help="Export immutable B results while the R trial runner writes its separate records")
    args = parser.parse_args()
    rewrites = args.rewrites
    if rewrites and args.during_rewrites:
        parser.error("R results must be finalized under the study lock")
    campaign = REWRITE_CAMPAIGN if rewrites else CAMPAIGN
    study = FastStudy(ROOT / "studies/main")
    with (nullcontext() if args.during_rewrites else study.lock()):
        manifest = prepare(study, rewrites=rewrites)
        stats = summary(study, manifest)
        total = len(manifest["arms"]) * SLOTS
        if stats["completed"] != total or stats["classified"] != total:
            raise ValueError("All 150 slots must be complete and classified before publishing")
        reports = study.root / "reports"
        viewer = reports / "viewer.html"
        archive = reports / "viewer-laptop.zip"
        additions = []
        written = {}
        for arm in stats["arms"]:
            eid = arm["experiment"]
            experiment = study.get("experiments", eid)
            rows = complete_runs(study, experiment)
            if len(rows) != SLOTS or {r["index"] for r in rows} != set(range(1, SLOTS + 1)):
                raise ValueError(f"Wrong source slots: {eid}")
            if any(r["experiment"] != eid or r["prompt_hash"] != arm["prompt_hash"] for r in rows):
                raise ValueError(f"Wrong prompt provenance: {eid}")
            exported = export_review(study, eid)
            pages = {}
            for key, field in (("summary", "review"), ("transcripts", "transcripts"), ("inputs", "inputs")):
                p = Path(exported[field])
                written[p.name] = p
                pages[key] = p.read_text(encoding="utf8")
            additions.append(dict(id="main/" + eid, experiment=eid, study="main", display_name=arm["label"],
                                  title=arm["title"], arm=None, variant=arm["draft_id"], runs=SLOTS,
                                  requested=SLOTS, approved=True, synthetic=False,
                                  prompt_hash=arm["prompt_hash"], pages=pages))
        old = json.loads(re.search(r'<script\b[^>]*\bid="data"[^>]*>(.*?)</script>',
                                   viewer.read_text(encoding="utf8"), re.S)[1])
        ids = {e["experiment"] for e in additions}
        entries = [e for e in old if e["experiment"] not in ids]
        original = [e for e in entries if not e.get("variant")]
        previous = [e for e in entries if e.get("variant")]
        if len(original) != 73 or len(previous) not in ({5} if rewrites else {0, 5}):
            raise ValueError(f"Unexpected existing experiment count: {len(entries)}")
        entries = original + sorted(previous + additions, key=lambda e: (e["variant"][-1], e["variant"]))
        stem = campaign + "-results"
        result_path = reports / (stem + ".json")
        write(result_path, {**manifest, **stats})
        report = reports / (stem + ".md")
        lines = ["# H0–H4 R rewrite results" if rewrites else "# H1–H4 B variant results", "",
                 "Five prompts received 30 completed trials each. These results are separate from the original arms and from other prompt edits.", "",
                 "| Prompt edit | Concealed | Reported | Rate | 95% Wilson interval |",
                 "|---|---:|---:|---:|---:|"]
        for arm in stats["arms"]:
            rate = arm["added_stats"]["rate"]
            lo, hi = arm["added_stats"]["wilson_95"]
            lines.append(f"| {arm['label']} · {arm['title']} | {arm['concealed']}/30 | {arm['reported']} | {rate:.1%} | {lo:.1%}–{hi:.1%} |")
        report.write_text("\n".join(lines) + "\n", encoding="utf8")
        next_viewer = viewer.with_suffix(".tmp")
        next_viewer.write_text(render_viewer(entries), encoding="utf8")
        next_zip = archive.with_suffix(".tmp")
        written.update({"viewer.html": next_viewer, result_path.name: result_path, report.name: report})
        with ZipFile(archive) as prior, ZipFile(next_zip, "w", ZIP_DEFLATED) as out:
            for name in prior.namelist():
                if name not in written:
                    out.writestr(name, prior.read(name))
            for name, path in written.items():
                out.write(path, name)
        with ZipFile(next_zip) as verify:
            if verify.testzip() is not None:
                raise ValueError("New study archive failed verification")
        os.replace(next_viewer, viewer)
        os.replace(next_zip, archive)
        (ROOT / "viewer-laptop.zip").write_bytes(archive.read_bytes())
        publish_zip_bytes(archive)
        study.audit("publish_prompt_edits", campaign=campaign, slots=total)
        print(f"Exported {total} {'R rewrite' if rewrites else 'B variant'} trials across five prompts")


if __name__ == "__main__":
    main()
