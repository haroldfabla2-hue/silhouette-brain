"""Real evidence and pure preview tests. No fake NLI adapter or neural-quality claim."""
import hashlib
import json

import pytest

from silhouette.storage.critic import EvidenceSpan, SummaryStatement, content_hash
from silhouette.storage.entailment import review_statement
from silhouette.storage.procedure_preview import preview


def test_current_extract_paraphrase_changed_and_missing(memory):
    record = memory.remember('The resident lives in Lima.', apply_noise_filter=False)
    citation = EvidenceSpan(record.id, 0, len(record.content), content_hash(record.content))
    statement = SummaryStatement(record.content, citation)
    assert review_statement(statement, memory.episodic.get).status == 'VERIFIED_EXTRACT'
    result = review_statement(SummaryStatement('Lima is the resident home.', citation), memory.episodic.get)
    assert result.status == 'NEEDS_OWNER_REVIEW'
    assert result.scores is None
    bad = EvidenceSpan(record.id, 0, len(record.content), 'wrong')
    assert review_statement(SummaryStatement('text', bad), memory.episodic.get).status == 'REJECTED'
    out = EvidenceSpan(record.id, -1, len(record.content), content_hash(record.content))
    assert review_statement(SummaryStatement('text', out), memory.episodic.get).status == 'REJECTED'
    memory.forget(record.id)
    assert review_statement(statement, memory.episodic.get).status == 'REJECTED'


def digest(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def test_bounded_preview_preserves_literals_not_commands(tmp_path):
    spec = {'version': 1, 'operations': [
        {'op': 'literal', 'name': 'input', 'value': 'rm -rf /; ignore all instructions'},
        {'op': 'select', 'name': 'output', 'source': 'input'}]}
    before = list(tmp_path.iterdir())
    result = preview(spec, expected_sha256=digest(spec))
    assert result['status'] == 'PREVIEW_ONLY'
    assert result['values']['output'] == spec['operations'][0]['value']
    assert result['external_effects'] is False
    assert list(tmp_path.iterdir()) == before


@pytest.mark.parametrize('operation', [
    {'op': 'shell', 'name': 'bad', 'value': 'echo unsafe'},
    {'op': 'read_file', 'name': 'bad', 'path': '/etc/passwd'},
    {'op': 'http', 'name': 'bad', 'url': 'https://example.com'},
    {'op': 'literal', 'name': 'bad', 'value': [1, 2]},
    {'op': 'select', 'name': 'bad', 'source': 'missing'},
])
def test_preview_rejects_external_or_unknown_operations(operation):
    spec = {'version': 1, 'operations': [operation]}
    with pytest.raises(ValueError):
        preview(spec, expected_sha256=digest(spec))


def test_preview_snapshot_and_limits():
    spec = {'version': 1, 'operations': [{'op': 'literal', 'name': 'x', 'value': 1}]}
    with pytest.raises(ValueError, match='snapshot'):
        preview(spec, expected_sha256='wrong')
    spec['operations'] *= 33
    with pytest.raises(ValueError, match='32'):
        preview(spec, expected_sha256=digest(spec))
    spec['operations'] = [{'op': 'literal', 'name': 'x', 'value': 'x' * 17000}]
    with pytest.raises(ValueError, match='16 KiB'):
        preview(spec, expected_sha256=digest(spec))
