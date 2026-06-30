import json
from src.adapters.csv_adapter import CSVAdapter
from src.adapters.ats_json_adapter import ATSJSONAdapter


def test_csv_adapter_basic():
    csv = """name,email,phone,location
John Doe,john.doe@example.com,+1 415 555 2671,San Francisco
"""
    a = CSVAdapter()
    frag = a.adapt(csv, None)
    assert frag.full_name == "John Doe"
    assert len(frag.emails) == 1
    assert frag.field_evidence
    for fe in frag.field_evidence:
        assert fe.transformation_ref is not None
    assert frag.transformation_history


def test_ats_json_adapter_basic():
    payload = {"id": "123", "candidateName": "Jane Smith", "emails": ["jane@example.com"], "location": "London"}
    a = ATSJSONAdapter()
    frag = a.adapt(payload, None)
    assert frag.full_name == "Jane Smith"
    assert len(frag.emails) == 1
    assert any(fe.field == "full_name" for fe in frag.field_evidence)
    assert frag.transformation_history
