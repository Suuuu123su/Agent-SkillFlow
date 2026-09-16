"""Public, read-only progress projection. No SDK, subprocess, or experiment imports.
The experiment's durable ledger, not this file, remains the source of truth.
"""
from __future__ import annotations
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

STATES = {'NOT_CONNECTED', 'READY', 'RUNNING', 'PAUSED', 'BLOCKED',
          'COMPLETED', 'COMPLETED_WITH_GAPS', 'STOPPED'}
UNIT_STATES = {'not_started', 'running', 'awaiting_judge', 'complete',
               'technical_error', 'response_unknown', 'blocked', 'technical_complete'}
VERDICTS = {'compromised', 'partial', 'safe'}
ROLES = {'actor', 'semantic', 'content', 'derived', 'judge', 'idle'}
MATCHES = {'UNVERIFIED', 'MATCHED_OBSERVED_CONTRACT', 'TRANSPORT_MISMATCH',
           'JUDGE_MISMATCH', 'LIBRARY_MISMATCH', 'MULTIPLE_MISMATCHES', 'HISTORY_ONLY'}
EVENT_CODES = {'RUN_READY', 'RUN_STARTED', 'UNIT_STARTED', 'ACTOR_DONE',
               'REQUEST_SENT', 'REQUEST_SETTLED', 'REQUEST_UNKNOWN', 'REVIEW_STARTED',
               'JUDGE_STARTED', 'JUDGE_DONE', 'UNIT_ERROR', 'RUN_PAUSED',
               'RUN_BLOCKED', 'RUN_STOPPED', 'RUN_COMPLETED', 'SNAPSHOT_RECOVERED'}
IDENT = re.compile(r'^[A-Za-z0-9_.:\-]{1,120}$')
CODE = re.compile(r'^[A-Z0-9_]{1,80}$')


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _enum(value: Any, allowed: set[str], default: str) -> str:
    x = default if value is None else value
    if not isinstance(x, str) or x not in allowed:
        raise ValueError('invalid public enum')
    return x


def _id(value: Any, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise ValueError('invalid public identifier')
    return value


def _integer(value: Any, default: int = 0) -> int:
    x = default if value is None else value
    if isinstance(x, bool) or not isinstance(x, int) or x < 0:
        raise ValueError('invalid public counter')
    return x


def _time(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('invalid timestamp')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('timestamp must include timezone')
    return dt.isoformat(timespec='seconds')


def project_snapshot(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and retain only public, typed fields; never return arbitrary payloads.

    Unknown keys (including raw errors/prompts/credentials) are deliberately not copied.
    This is an exposure-minimization layer, not an independent correctness auditor.
    """
    if not isinstance(data, Mapping):
        raise ValueError('snapshot must be an object')
    state = _enum(data.get('state'), STATES, 'NOT_CONNECTED')
    if data.get('model', 'gpt-5.6-luna') != 'gpt-5.6-luna':
        raise ValueError('this monitor is for the requested Luna stage only')
    transport = _enum(data.get('transport'), {'UNBOUND', 'API', 'ISOLATED_CODEX_CLI'}, 'UNBOUND')
    raw_units = data.get('units', [])
    if not isinstance(raw_units, list) or len(raw_units) > 43:
        raise ValueError('invalid unit list')
    units, seen, seen_core = [], set(), set()
    for raw in raw_units:
        if not isinstance(raw, dict):
            raise ValueError('unit must be an object')
        uid = _id(raw.get('unit_id'), required=True)
        if uid in seen:
            raise ValueError('duplicate unit_id')
        seen.add(uid)
        phase = _enum(raw.get('phase'), {'CORE', 'TECH'}, 'CORE')
        eval_id = _id(raw.get('eval_id'), required=True)
        if phase == 'CORE':
            if eval_id in seen_core:
                raise ValueError('duplicate core eval_id')
            seen_core.add(eval_id)
        attack = raw.get('attack')
        if phase == 'CORE' and not isinstance(attack, bool):
            raise ValueError('CORE attack must be boolean')
        if attack is not None and not isinstance(attack, bool):
            raise ValueError('invalid condition')
        status = _enum(raw.get('status'), UNIT_STATES, 'not_started')
        if status == 'technical_complete' and phase != 'TECH':
            raise ValueError('technical_complete is TECH only')
        if status == 'technical_complete' and phase != 'TECH':
            raise ValueError('technical_complete is TECH only')
        verdict = raw.get('verdict')
        if verdict is not None and verdict not in VERDICTS:
            raise ValueError('invalid verdict')
        if status == 'complete' and verdict is None:
            raise ValueError('complete requires a saved valid judgment')
        if status in {'not_started', 'running', 'awaiting_judge', 'blocked'} and verdict is not None:
            raise ValueError('judgment not yet finalized')
        error = raw.get('error_code')
        if error is not None and (not isinstance(error, str) or not CODE.fullmatch(error)):
            raise ValueError('use a fixed error code, not a raw error message')
        units.append({'unit_id':uid, 'eval_id':eval_id, 'phase':phase, 'attack':attack,
                      'status':status, 'verdict':verdict, 'actor_turn':_integer(raw.get('actor_turn')),
                      'error_code':error, 'reference_match':_enum(raw.get('reference_match'), MATCHES, 'UNVERIFIED')})
    core = [u for u in units if u['phase']=='CORE']
    tech = [u for u in units if u['phase']=='TECH']
    if len(core)>39 or len(tech)>4:
        raise ValueError('unit capacity exceeded')
    if sum(u['attack'] for u in core)>26 or sum(not u['attack'] for u in core)>13:
        raise ValueError('condition capacity exceeded')
    ended = {'awaiting_judge','complete','technical_error','response_unknown','technical_complete'}
    def counts(rows: list[dict[str, Any]]) -> dict[str, int]:
        return {'registered':len(rows), 'started':sum(u['status'] not in {'not_started','blocked'} for u in rows),
                'actor_terminal':sum(u['status'] in ended for u in rows),
                'judged':sum(u['verdict'] in VERDICTS for u in rows),
                'running':sum(u['status']=='running' for u in rows),
                'awaiting_judge':sum(u['status']=='awaiting_judge' for u in rows),
                'technical_error':sum(u['status']=='technical_error' for u in rows),
                'response_unknown':sum(u['status']=='response_unknown' for u in rows),
                'blocked':sum(u['status']=='blocked' for u in rows),
                'not_started':sum(u['status']=='not_started' for u in rows)}
    def verdicts(rows: list[dict[str, Any]], planned: int) -> dict[str, Any]:
        counted = {v:sum(u['verdict']==v for u in rows) for v in sorted(VERDICTS)}
        n = sum(counted.values())
        return {'planned':planned, 'judged':n, **counted,
                'observed_asr':counted['compromised']/n if n else None,
                'observed_safe_fraction':counted['safe']/n if n else None}
    req = data.get('requests', {})
    if not isinstance(req, dict):
        raise ValueError('invalid request counters')
    requests = {k:_integer(req.get(k)) for k in ('attempts','settled','in_flight','response_unknown')}
    if requests['attempts'] != sum(requests[k] for k in ('settled','in_flight','response_unknown')):
        raise ValueError('request ledger does not reconcile')
    # Preserve and visibly flag cap violations rather than concealing an already observed count.
    role_counts = req.get('by_role', {})
    if not isinstance(role_counts, dict):
        raise ValueError('invalid role counters')
    requests['by_role'] = {r:_integer(role_counts[r]) for r in sorted(ROLES-{'idle'}) if r in role_counts}
    if requests['by_role'] and sum(requests['by_role'].values()) > requests['attempts']:
        raise ValueError('role counters exceed observed requests')
    cur = data.get('current') or {}
    if not isinstance(cur, dict):
        raise ValueError('invalid current state')
    current = {'unit_id':_id(cur.get('unit_id')), 'eval_id':_id(cur.get('eval_id')),
               'role':_enum(cur.get('role'),ROLES,'idle'), 'actor_turn':_integer(cur.get('actor_turn'))}
    if current['unit_id'] is not None and current['unit_id'] not in seen:
        raise ValueError('current unit not in ledger snapshot')
    events = []
    raws = data.get('events', [])
    if not isinstance(raws, list):
        raise ValueError('invalid events')
    for e in raws[-12:]:
        if not isinstance(e, dict):
            raise ValueError('invalid event')
        events.append({'at':_time(e.get('at')), 'code':_enum(e.get('code'),EVENT_CODES,'RUN_READY'),
                       'unit_id':_id(e.get('unit_id'))})
    cc, tc = counts(core), counts(tech)
    if state == 'COMPLETED' and (len(core)!=39 or cc['judged']!=39 or cc['technical_error'] or cc['response_unknown'] or requests['in_flight']):
        raise ValueError('COMPLETED inconsistent; use documented gap state when applicable')
    return {'schema_version':1,'run_id':_id(data.get('run_id')), 'state':state,
            'phase':_enum(data.get('phase'),{'BINDING','TECH','CORE','JUDGING','REPORT','IDLE'},'IDLE'),
            'model':'gpt-5.6-luna','transport':transport,
            'started_at':_time(data.get('started_at')), 'heartbeat_at':_time(data.get('heartbeat_at')),
            'last_event_at':_time(data.get('last_event_at')), 'written_at':_time(data.get('written_at')),
            'current':current,'requests':requests,'request_cap':min(5600,_integer(data.get('request_cap'),4096)),'over_request_cap':requests['attempts']>min(5600,_integer(data.get('request_cap'),4096)),
            'core':{'planned':39,**cc}, 'tech':{'capacity':4,**tc},
            'attack':verdicts([u for u in core if u['attack']],26),
            'clean':verdicts([u for u in core if not u['attack']],13),
            'units':units,'events':events}


def write_snapshot(destination: Path, view: Mapping[str, Any]) -> dict[str, Any]:
    """Single-writer atomic projection; call only with this run's real ledger facts."""
    destination = Path(destination)
    state = dict(view)
    state['written_at'] = utc_now()  # File generation time, not experiment heartbeat.
    projected = project_snapshot(state)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent,
                                         prefix='.progress-', suffix='.tmp', delete=False) as stream:
            temp = stream.name
            json.dump(projected,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        for attempt in range(10):
            try:
                os.replace(temp,destination)
                break
            except PermissionError:
                if attempt==9: raise
                time.sleep(0.02)
        temp = None
    finally:
        if temp is not None:
            Path(temp).unlink(missing_ok=True)
    return projected
