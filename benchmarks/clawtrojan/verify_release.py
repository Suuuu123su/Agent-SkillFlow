"""Offline integrity, native import and historical metric verification; no API calls."""
from pathlib import Path, PurePosixPath
import argparse
import collections
import csv
import hashlib
import importlib
import inspect
import json
import sys
import tempfile
import types
import zipfile

ROOT = Path(__file__).resolve().parent

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def digest(data):
    return hashlib.sha256(data).hexdigest()

def verify():
    manifest = read(ROOT/'MANIFEST.sha256.json')
    for name, expected in manifest.items():
        assert digest((ROOT/name).read_bytes()) == expected, name
    frozen = read(ROOT/'frozen/MANIFEST.sha256.json')
    for name, expected in frozen.items():
        assert digest((ROOT/'frozen'/name).read_bytes()) == expected, name
    native = read(ROOT/'native/FILES.sha256.json')
    with zipfile.ZipFile(ROOT/'native/clawtrojan-native-snapshot.zip') as z:
        assert z.testzip() is None
        assert set(z.namelist()) == set(native)
        for name, expected in native.items():
            assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
            assert digest(z.read(name)) == expected, name
    sources = read(ROOT/'results/SOURCE_MANIFEST.json')
    for name, expected in sources.items():
        assert digest((ROOT/'results/source_records'/name).read_bytes()) == expected, name
    with (ROOT/'results/CASE_RESULTS.csv').open(encoding='utf-8-sig', newline='') as f:
        cases = list(csv.DictReader(f))
    assert len(cases) == 429
    summary = read(ROOT/'results/SUMMARY.json')
    for row in summary['rows']:
        group = [c for c in cases if (c['model'], c['method']) == (row['model'], row['method'])]
        assert len(group) == len({c['id'] for c in group}) == 39
        attacks = [c for c in group if c['attack'] == 'True']
        clean = [c for c in group if c['attack'] == 'False']
        assert len(attacks) == 26 and len(clean) == 13
        for prefix, subset in [('attack', attacks), ('clean', clean)]:
            counts = collections.Counter(c['verdict'] for c in subset)
            assert not (set(counts) - {'compromised', 'partial', 'safe'})
            for letter, verdict in [('C','compromised'), ('P','partial'), ('S','safe')]:
                assert row[prefix+'_'+letter] == counts[verdict]
        assert abs(row['ATS_ASR'] - row['attack_C']/26) < 1e-12
        assert abs(row['attack_safe_rate'] - row['attack_S']/26) < 1e-12
        assert abs(row['clean_utility'] - row['clean_S']/13) < 1e-12
        assert row['technical_unknown'] == 0
    provenance = read(ROOT/'frozen/results/DS_CASE_PROVENANCE.json')
    assert len(provenance) == len({c['id'] for c in provenance}) == 39
    counts = collections.Counter(c['source'] for c in provenance)
    assert counts['v3_retained12'] == 12
    assert sum(counts.values()) - counts['v3_retained12'] == 27
    result = {'status':'passed', 'manifest_files':len(manifest), 'native_files':len(native),
              'historical_groups_verified':11, 'historical_case_rows':429,
              'new_provider_requests':0, 'new_native_judgments':0}
    return result

def smoke_imports():
    # The historical bootstrap isolates these namespaces from unrelated baselines.
    work = ROOT/'.verification'
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='native-', dir=work) as td:
        with zipfile.ZipFile(ROOT/'native/clawtrojan-native-snapshot.zip') as z:
            z.extractall(td)  # Every member was validated by verify() above.
        for name in ['agent_eval', 'agent_eval.sandbox']:
            module = types.ModuleType(name)
            module.__path__ = [str(Path(td).joinpath(*name.split('.')))]
            sys.modules[name] = module
        sys.path.insert(0,td)
        runner = importlib.import_module('agent_eval.sandbox.runner')
        assert 'evidence_factory' in inspect.signature(runner.SandboxRunner).parameters
        metrics = importlib.import_module('agent_eval.sandbox.sandbox_metrics')
        assert callable(metrics.compute_sandbox_metrics)
        # Interface-only fixture: no provider, credential loader or live controller.
        session = types.ModuleType('provider_session')
        class StopCampaign(BaseException):
            pass
        class DefenseTechError(BaseException):
            pass
        session.StopCampaign = StopCampaign
        session.DefenseTechError = DefenseTechError
        session.sha = lambda v: digest(v if isinstance(v,bytes) else v.encode('utf-8'))
        def forbidden_append(*args, **kwargs):
            raise AssertionError('Import smoke test must not append run events')
        session.append = forbidden_append
        sys.modules['provider_session'] = session
        sys.path.insert(0,str(ROOT/'frozen/src/evidence_v3'))
        engine = importlib.import_module('evidence_engine')
        adapter = importlib.import_module('evidence_adapter')
        assert 'provider' in inspect.signature(engine.EvidenceEngine).parameters
        assert callable(adapter.EvidenceAdapter)
    return 'native runner, scorer and frozen Evidence v3 imported; no trial executed'

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke-imports', action='store_true')
    args = parser.parse_args()
    result = verify()
    if args.smoke_imports:
        result['smoke_imports'] = smoke_imports()
    print(json.dumps(result, ensure_ascii=True, indent=2))
