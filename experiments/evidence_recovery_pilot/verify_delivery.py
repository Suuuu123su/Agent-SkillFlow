"""Read-only validation of frozen inputs, plans and compressed result bytes."""
import gzip
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "论文材料/修复与补强_20260919"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    checks = []
    for item in read(BASE / "hiaa/INPUT_MANIFEST.json")["sources"]:
        location = item["path"]
        if "!" in location:
            archive, member = location.split("!", 1)
            with zipfile.ZipFile(ROOT / archive) as bundle:
                raw = bundle.read(member)
        else:
            raw = (ROOT / location).read_bytes()
        assert sha(raw) == item["sha256"], location
        checks.append({"check": "hiaa_input_hash", "path": location, "pass": True})
    for folder in ["evidence_pilot", "evidence_pilot_reference"]:
        directory = BASE / folder
        plan = read(directory / "PLAN.json")
        assert sha((directory / "PLAN.json").read_bytes()) == (directory / "PLAN.sha256").read_text().strip()
        assert sha((ROOT / plan["archive_relative_path"]).read_bytes()) == plan["archive_sha256"]
        assert sha((ROOT / "experiments/evidence_recovery_pilot/run.py").read_bytes()) == plan["runner_sha256"]
        if "reference_wrapper_sha256" in plan:
            assert sha((ROOT / "experiments/evidence_recovery_pilot/reference_check.py").read_bytes()) == plan["reference_wrapper_sha256"]
        archive = read(directory / "RESULT_ARCHIVE.json")
        raw = (directory / archive["archive_name"]).read_bytes()
        assert sha(raw) == archive["archive_sha256"]
        assert sha(gzip.decompress(raw)) == archive["original_sha256"]
        checks.append({"check": "frozen_plan_and_archived_result", "path": folder, "pass": True})
    for page in [ROOT / "README.md", ROOT / "论文材料/README.md", *BASE.rglob("*.md")]:
        for _, url in re.findall(r"\[([^\]]*)\]\(([^)]+)\)", page.read_text(encoding="utf-8")):
            if "://" in url or url.startswith("#"):
                continue
            assert (page.parent / url.split("#")[0]).exists(), (page, url)
    checks.append({"check": "current_and_supplement_markdown_local_links", "pass": True})
    result = {"status": "PASS", "checks": checks, "new_predictions": 0,
              "scope": "Hash bindings, gzip round trips and local links; does not repeat experimental runs."}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
