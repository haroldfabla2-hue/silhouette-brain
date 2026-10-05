"""Pure bounded procedure preview, NOT an OS security sandbox or executor.

Only literals and explicit selection are supported. No eval, shell, subprocess,
network, filesystem writes, imports or dynamic code. Reviewed natural-language
steps are never translated to actions and approval does not authorize execution.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def preview(spec: dict[str, Any], *, expected_sha256: str) -> dict[str, Any]:
    """Evaluate a tiny declarative plan into in-memory values with bounded input."""
    raw = json.dumps(spec, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(raw.encode()) > 16384:
        raise ValueError('Preview input exceeds 16 KiB')
    if hashlib.sha256(raw.encode()).hexdigest() != expected_sha256:
        raise ValueError('Plan differs from exact reviewed snapshot')
    if set(spec) != {'version', 'operations'} or spec['version'] != 1:
        raise ValueError('Unsupported preview schema')
    operations = spec['operations']
    if not isinstance(operations, list) or not 1 <= len(operations) <= 32:
        raise ValueError('Preview requires 1 to 32 operations')
    values: dict[str, Any] = {}
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValueError('Invalid operation')
        name = operation.get('name')
        if not isinstance(name, str) or not name.isidentifier() or name in values:
            raise ValueError('Unique simple result name required')
        if operation.get('op') == 'literal' and set(operation) == {'op', 'name', 'value'}:
            value = operation['value']
            if not isinstance(value, (str, int, float, bool, type(None))):
                raise ValueError('Literal must be a JSON scalar')
            values[name] = value
        elif operation.get('op') == 'select' and set(operation) == {'op', 'name', 'source'}:
            source = operation['source']
            if not isinstance(source, str) or source not in values:
                raise ValueError('Select requires an earlier result')
            values[name] = values[source]
        else:
            raise ValueError('Unsupported operation; no external effects permitted')
    return {'status': 'PREVIEW_ONLY', 'plan_sha256': expected_sha256, 'values': values,
            'external_effects': False}
