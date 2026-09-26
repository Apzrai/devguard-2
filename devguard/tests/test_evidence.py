"""
test_evidence.py — Tests for devguard/evidence.py
"""

import pytest
from pathlib import Path

from devguard.understand import understand
from devguard.evidence import collect_evidence, Evidence

SAMPLE_APP = Path(__file__).parent.parent.parent / "sample_app"


@pytest.fixture(scope="module")
def evidence():
    u = understand(SAMPLE_APP)
    return collect_evidence(u)


class TestEvidenceStructure:
    def test_returns_evidence_instance(self, evidence):
        assert isinstance(evidence, Evidence)

    def test_has_evidence_id(self, evidence):
        assert len(evidence.evidence_id) == 36   # UUID

    def test_has_aggregate_hash(self, evidence):
        assert len(evidence.aggregate_hash) == 64
        assert evidence.aggregate_hash.isalnum()

    def test_recorded_at_is_set(self, evidence):
        ts = evidence.to_dict()["recorded_at"]
        assert "T" in ts

    def test_file_hashes_is_non_empty(self, evidence):
        assert len(evidence.file_hashes) > 0

    def test_total_files_matches_file_hashes(self, evidence):
        assert evidence.to_dict()["total_files"] == len(evidence.file_hashes)

    def test_total_test_functions_is_reasonable(self, evidence):
        assert evidence.to_dict()["total_test_functions"] >= 100


class TestFileHashes:
    def test_each_hash_is_64_hex_chars(self, evidence):
        for fh in evidence.file_hashes:
            assert len(fh["sha256"]) == 64
            assert fh["sha256"].isalnum()

    def test_all_hashes_have_file_type(self, evidence):
        valid_types = {"source", "test", "doc", "other"}
        for fh in evidence.file_hashes:
            assert fh["file_type"] in valid_types

    def test_source_files_are_classified_correctly(self, evidence):
        source_files = [fh for fh in evidence.file_hashes if fh["file_type"] == "source"]
        names = {Path(fh["path"]).name for fh in source_files}
        assert "customers.py" in names
        assert "discount.py" in names
        assert "tax.py" in names

    def test_test_files_are_classified_correctly(self, evidence):
        test_files = [fh for fh in evidence.file_hashes if fh["file_type"] == "test"]
        names = {Path(fh["path"]).name for fh in test_files}
        assert "test_customers.py" in names
        assert "test_discount.py" in names

    def test_doc_files_are_classified_correctly(self, evidence):
        doc_files = [fh for fh in evidence.file_hashes if fh["file_type"] == "doc"]
        names = {Path(fh["path"]).name for fh in doc_files}
        assert "BUSINESS_RULES.md" in names

    def test_all_file_hashes_have_provenance_observed(self, evidence):
        for fh in evidence.file_hashes:
            assert fh["provenance"] == "OBSERVED"

    def test_customers_py_hash_matches_direct_read(self, evidence):
        """The hash in Evidence must match the actual file on disk."""
        import hashlib
        actual = hashlib.sha256((SAMPLE_APP / "customers.py").read_bytes()).hexdigest()
        recorded = evidence.get_hash("customers.py")
        assert recorded == actual

    def test_test_customers_py_hash_matches_direct_read(self, evidence):
        import hashlib
        actual = hashlib.sha256(
            (SAMPLE_APP / "tests" / "test_customers.py").read_bytes()
        ).hexdigest()
        recorded = evidence.get_hash("test_customers.py")
        assert recorded == actual


class TestAggregateHash:
    def test_aggregate_hash_is_deterministic_for_same_state(self):
        """Running evidence twice on the same project yields the same aggregate hash."""
        u1 = understand(SAMPLE_APP)
        u2 = understand(SAMPLE_APP)
        e1 = collect_evidence(u1)
        e2 = collect_evidence(u2)
        assert e1.aggregate_hash == e2.aggregate_hash

    def test_matches_method_true_for_same_state(self):
        u1 = understand(SAMPLE_APP)
        u2 = understand(SAMPLE_APP)
        e1 = collect_evidence(u1)
        e2 = collect_evidence(u2)
        assert e1.matches(e2)

    def test_get_hash_returns_none_for_nonexistent_file(self, evidence):
        assert evidence.get_hash("nonexistent_file.py") is None
