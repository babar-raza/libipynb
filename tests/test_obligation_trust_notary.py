"""Obligation tests for content-addressed, pluggable notebook trust."""

from __future__ import annotations

from copy import deepcopy

import nbformat
from nbformat.sign import NotebookNotary as ReferenceNotebookNotary
import pytest
from libipynb.errors import NotebookResourceLimitError as ResourceLimitError
from libipynb.security.limits import NotebookResourceLimits as ResourceLimits
from libipynb import (
    HmacNotebookNotary,
    IpynbDocument,
    MemorySignatureStore,
    TrustStatus,
    validate,
)


SECRET = b"format-factory-test-notary-key-" * 2


def _document() -> IpynbDocument:
    return IpynbDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernel": {"name": "python3"}},
            "cells": [
                {
                    "cell_type": "code",
                    "id": "trusted-cell",
                    "metadata": {},
                    "source": "print('reviewed')",
                    "execution_count": 1,
                    "outputs": [
                        {
                            "output_type": "stream",
                            "name": "stdout",
                            "text": "reviewed\n",
                        }
                    ],
                }
            ],
        }
    )


def test_signature_matches_the_pinned_official_nbformat_notary() -> None:
    document = _document()
    reference_notebook = nbformat.from_dict(deepcopy(document.raw))
    reference = ReferenceNotebookNotary(
        secret=SECRET,
        data_dir="",
        db_file=":memory:",
    )
    notary = HmacNotebookNotary(secret=SECRET)

    assert notary.compute_signature(document) == reference.compute_signature(
        reference_notebook
    )


def test_content_edit_invalidates_trust_without_affecting_validity() -> None:
    document = _document()
    notary = HmacNotebookNotary(secret=SECRET)

    record = notary.sign(document)
    trusted = notary.verify(document)
    assert trusted.status is TrustStatus.TRUSTED
    assert trusted.record == record
    assert notary.check_signature(document) is True
    assert bool(validate(document)) is True
    assert "trusted" not in document.cells[0]["metadata"]

    document.cells[0]["source"] = "print('changed after review')"
    untrusted = notary.verify(document)
    assert untrusted.status is TrustStatus.UNTRUSTED
    assert untrusted.reason == "signature_not_found"
    assert notary.check_signature(document) is False
    assert bool(validate(document)) is True
    assert "trusted" not in document.cells[0]["metadata"]


def test_reverting_exact_content_restores_content_addressed_trust() -> None:
    document = _document()
    original = deepcopy(document.raw)
    notary = HmacNotebookNotary(secret=SECRET)
    notary.sign(document)

    document.cells[0]["source"] = "changed"
    assert notary.check_signature(document) is False
    document.raw.clear()
    document.raw.update(original)
    assert notary.check_signature(document) is True


def test_revoke_removes_only_the_selected_content_signature() -> None:
    first = _document()
    second = _document()
    second.cells[0]["source"] = "print('second')"
    notary = HmacNotebookNotary(secret=SECRET)
    first_record = notary.sign(first)
    notary.sign(second)

    assert notary.revoke(first) is True
    assert notary.check_signature(first) is False
    assert notary.check_signature(second) is True
    assert notary.revoke_record(first_record) is False


class RecordingStore:
    def __init__(self) -> None:
        self.values: set[tuple[str, str]] = set()
        self.calls: list[tuple[str, str, str]] = []

    def store_signature(self, digest: str, algorithm: str) -> None:
        self.calls.append(("store", digest, algorithm))
        self.values.add((digest, algorithm))

    def check_signature(self, digest: str, algorithm: str) -> bool:
        self.calls.append(("check", digest, algorithm))
        return (digest, algorithm) in self.values

    def remove_signature(self, digest: str, algorithm: str) -> None:
        self.calls.append(("remove", digest, algorithm))
        self.values.discard((digest, algorithm))


def test_signature_store_is_pluggable_and_uses_official_method_contract() -> None:
    store = RecordingStore()
    document = _document()
    notary = HmacNotebookNotary(secret=SECRET, store=store)

    record = notary.sign(document)
    assert notary.check_signature(document) is True
    assert notary.revoke(document) is True

    assert store.calls == [
        ("store", record.digest, "sha256"),
        ("check", record.digest, "sha256"),
        ("check", record.digest, "sha256"),
        ("remove", record.digest, "sha256"),
    ]


def test_memory_store_is_bounded_and_deterministically_culls_oldest() -> None:
    store = MemorySignatureStore(max_signatures=2)
    store.store_signature("first", "sha256")
    store.store_signature("second", "sha256")
    store.store_signature("third", "sha256")

    assert store.check_signature("first", "sha256") is False
    assert store.check_signature("second", "sha256") is True
    assert store.check_signature("third", "sha256") is True
    assert len(store) == 2


def test_signature_computation_is_non_mutating_and_ignores_legacy_signature() -> None:
    document = _document()
    document.raw["metadata"]["signature"] = "legacy-untrusted-value"
    before = deepcopy(document.raw)
    notary = HmacNotebookNotary(secret=SECRET)

    with_legacy = notary.compute_signature(document)
    del document.raw["metadata"]["signature"]
    without_legacy = notary.compute_signature(document)
    document.raw["metadata"]["signature"] = "legacy-untrusted-value"

    assert with_legacy == without_legacy
    assert document.raw == before


def test_secret_algorithm_and_resource_limits_fail_closed() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        HmacNotebookNotary(secret=b"short")
    with pytest.raises(ValueError, match="algorithm"):
        HmacNotebookNotary(secret=SECRET, algorithm="sha1")

    document = _document()
    document.cells[0]["metadata"]["nested"] = {"one": {"two": {"three": 3}}}
    notary = HmacNotebookNotary(secret=SECRET)
    limits = ResourceLimits(max_nesting_depth=2)
    with pytest.raises(ResourceLimitError, match="max_nesting_depth"):
        notary.compute_signature(document, limits=limits)


def test_notary_never_calls_notebook_objects_or_payloads() -> None:
    class HostileValue:
        def __str__(self) -> str:
            raise AssertionError("non-JSON payload was evaluated")

    document = _document()
    document.raw["metadata"]["hostile"] = HostileValue()
    notary = HmacNotebookNotary(secret=SECRET)

    with pytest.raises(TypeError, match="JSON-compatible"):
        notary.compute_signature(document)
