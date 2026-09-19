"""Archive large generated CSVs without changing frozen plans or runner bytes."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directories", type=Path, nargs="+")
    args = parser.parse_args()
    for directory in args.directories:
        source = directory / "query_results.csv"
        target = directory / "query_results.csv.gz"
        raw = source.read_bytes()
        compressed = gzip.compress(raw, compresslevel=9, mtime=0)
        assert gzip.decompress(compressed) == raw
        with target.open("xb") as stream:
            stream.write(compressed)
        assert gzip.decompress(target.read_bytes()) == raw
        manifest = {
            "original_name": source.name,
            "original_bytes": len(raw),
            "original_sha256": hashlib.sha256(raw).hexdigest(),
            "archive_name": target.name,
            "archive_bytes": len(compressed),
            "archive_sha256": hashlib.sha256(compressed).hexdigest(),
            "round_trip_exact": True,
            "plan_and_runner_unchanged": True,
            "restore": "python -m gzip -d query_results.csv.gz",
        }
        (directory / "RESULT_ARCHIVE.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        source.unlink()
        print(json.dumps({"directory": str(directory), **manifest}))


if __name__ == "__main__":
    main()
