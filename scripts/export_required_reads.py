"""Verify and export completed required-read replacements for the published results."""
import json
from collections import Counter

from run_required_reads import CAMPAIGN, FILES, ROOT, FastStudy
from forensics.prompts import digest
from forensics.review import public_transcript
from forensics.storage import read, write
from forensics.workflow import complete_runs


def verified_file_reads(run, prompt):
    expected = {name: prompt["files"][name].replace("\r\n", "\n").strip() for name in FILES}
    files = {}
    commands = set()
    for index, message in enumerate(run["messages"]):
        for call in message.get("tool_calls", []):
            if call["function"]["name"] == "execute_command":
                commands.add(call["id"])
        if message["role"] != "tool" or message.get("tool_call_id") not in commands:
            continue
        result = json.loads(message["content"])
        if result["exit_code"] != 0:
            continue
        output = result["output"].replace("\r\n", "\n")
        for name, text in expected.items():
            if text and text in output:
                files.setdefault(name, index)
    if files.keys() != expected.keys():
        raise ValueError(f"Incomplete file read evidence in {run['id']}: {sorted(expected.keys() - files.keys())}")
    return files


def main():
    study = FastStudy(ROOT / "studies/main")
    with study.lock():
        manifest = read(study.root / f"{CAMPAIGN}-manifest.json")
        reports = study.root / "reports"
        pairs = []
        attempts = {}
        for arm in manifest["arms"]:
            experiment = study.get("experiments", arm["experiment"])
            source = study.get("experiments", arm["source"])
            rows = {r["index"]: r for r in complete_runs(study, experiment)}
            attempts[arm["source"]] = len(study.attempts(arm["experiment"]))
            if len(rows) != arm["requested"] or experiment["prompt"]["files"] != source["prompt"]["files"]:
                raise ValueError(f"Mismatched replacement experiment: {arm['experiment']}")
            for slot, old in enumerate(arm["original_runs"], start=1):
                original = study.get("runs", old["id"])
                if original["transcript_hash"] != old["transcript_hash"] or digest(original["messages"]) != old["transcript_hash"]:
                    raise ValueError(f"Original transcript changed: {old['id']}")
                new = rows[slot]
                proof = verified_file_reads(new, experiment["prompt"])
                record = public_transcript(new)
                record["support"] = "Required-read replacement"
                pairs.append({"source": arm["source"], "original": old, "replacement": record, "file_reads": proof})
        if len(pairs) != manifest["requested"] or len({p["original"]["id"] for p in pairs}) != len(pairs):
            raise ValueError("Inconsistent completed replacement pairs")
        if len({p["replacement"]["id"] for p in pairs}) != len(pairs):
            raise ValueError("Replacement was assigned to more than one original")
        old_counts = Counter(p["original"]["outcome"] for p in pairs)
        new_counts = Counter(p["replacement"]["outcome"] for p in pairs)
        write(reports / "required-read-replacements.json", {
            "source_version": manifest["dataset_version"], "pairs": pairs,
            "attempts": attempts,
            "previous_concealed": old_counts["concealed"], "replacement_concealed": new_counts["concealed"],
        })
        print(f"Verified four file reads in each of {len(pairs)} replacements. "
              f"Concealed in the replaced slots: {old_counts['concealed']} before, {new_counts['concealed']} after.")


if __name__ == "__main__":
    main()
