"""Read-only verification of delivered pilot evidence; no gateway or prediction runs."""
import argparse
import json
from pathlib import Path
import subprocess
import tarfile

from experiments.evidence_contract_validation.common import ROOT, load_frozen, read_json, sha
from .paths import confined
from .pilot_report import verify_and_summarize


def verify(out, package=None, original=None):
    result, _, _, _ = verify_and_summarize(out)
    assert result == read_json(out/'SUMMARY.json')
    env = load_frozen(out/'ENVIRONMENT_BINDING.json')
    for stem in ('WORKSPACES', 'WORKSPACES_EXTRA', 'NATIVE_AUXILIARY'):
        manifest = read_json(out/(stem+'_MANIFEST.json'))
        archive = out/(stem+'.tar.gz')
        assert sha(archive.read_bytes()) == manifest['archive_sha256']
        recovered = {}
        with tarfile.open(archive, 'r:gz') as tar:
            for member in tar.getmembers():
                confined(out, member.name)
                assert member.isfile() and member.name not in recovered
                recovered[member.name] = sha(tar.extractfile(member).read())
        assert recovered == manifest['files']
    for rel, digest in env['source_hashes'].items():
        assert sha(confined(out, rel).read_bytes()) == digest, rel
    package_status = 'NOT_REQUESTED'
    if package is not None:
        expected = env['installed_package_file_hashes']
        actual = {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()}
        assert actual == set(expected)
        for rel, digest in expected.items():
            assert sha(confined(package, rel).read_bytes()) == digest, rel
        assert sha((package.parent.parent/'package-lock.json').read_bytes()) == env['package_lock_sha256']
        package_status = 'PASSED'
    preservation = 'NOT_REQUESTED'
    if original is not None:
        baseline = read_json(out.parent/'PRESERVATION_BASELINE.json')
        actual = {}
        for key, args in [('diff', ['diff', '--binary']), ('status', ['status', '--porcelain=v1', '-z'])]:
            actual[key] = sha(subprocess.check_output(['git', '-C', str(original), *args], stderr=subprocess.DEVNULL))
        assert actual == baseline, actual
        preservation = 'PASSED'
    return dict(status='PASSED', executions=result['new_sandbox_executions'], model_calls=0,
                new_executions=0, new_predictions=0, native_calls=result['formal_native_tool_calls'],
                frozen_sources_and_raw_effects='PASSED', environment_package=package_status,
                package_files=len(env['installed_package_file_hashes']), user_workspace=preservation)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--package', type=Path)
    p.add_argument('--original-workspace', type=Path)
    a = p.parse_args()
    print(json.dumps(verify(a.out.resolve(), a.package, a.original_workspace), indent=2))
