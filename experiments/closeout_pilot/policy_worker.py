"""Line-based IPC worker. Receives only licensed inputs; no raw/oracle paths."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.closeout_pilot.predictor import predict
from experiments.evidence_contract_validation.policy import choose


def respond(message):
    # Whitelist extraction: injected labels/Full/raw values cannot enter decisions.
    metric = message['metric']
    prediction = predict(metric, message['visible'])
    selected = None if prediction['status'] in ('point', 'not_applicable') else choose(
        metric, message['policy'], prediction, message['acquired'], message['order'],
        message['quotes'], message['remaining'])
    return {'prediction': prediction, 'selected': selected}


if __name__ == '__main__':
    for line in sys.stdin:
        try:
            answer = respond(json.loads(line))
            print(json.dumps(answer, ensure_ascii=True, sort_keys=True), flush=True)
        except Exception as exc:
            print(json.dumps({'error': type(exc).__name__ + ': ' + str(exc)}), flush=True)
