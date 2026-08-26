"""Typed-option validation for libipynb.execution -- no kernel required.

Deliberately separate from tests/integration/test_obligation_jupyter_
execution_adapter.py (which pytest.importorskip-gates the whole module on
nbclient/a real kernel being present): everything here must run on any
machine, with or without the ``exec`` extra installed, because
``ExecutionOptions``/``ExecutionResult``/the exception hierarchy are all
importable and usable without nbclient (see tests/unit/test_execution_core_
independence.py for the dedicated proof of that property).
"""

from __future__ import annotations

import pytest

from libipynb.execution import ExecutionOptions


def test_defaults_are_a_safe_non_mutating_trusted_local_posture() -> None:
    options = ExecutionOptions()

    assert options.acknowledge_unsandboxed is False
    assert options.in_place is False
    assert options.stop_on_error is True
    assert options.interrupt_on_timeout is True
    assert options.record_timing is False
    assert options.skip_tag == "skip-execution"


def test_cell_timeout_of_zero_or_negative_is_rejected() -> None:
    with pytest.raises(ValueError, match="cell_timeout"):
        ExecutionOptions(cell_timeout=0)
    with pytest.raises(ValueError, match="cell_timeout"):
        ExecutionOptions(cell_timeout=-1)


def test_cell_timeout_none_disables_the_per_cell_timeout() -> None:
    options = ExecutionOptions(cell_timeout=None)
    assert options.cell_timeout is None


def test_kernel_startup_timeout_must_be_positive() -> None:
    with pytest.raises(ValueError, match="kernel_startup_timeout"):
        ExecutionOptions(kernel_startup_timeout=0)
    with pytest.raises(ValueError, match="kernel_startup_timeout"):
        ExecutionOptions(kernel_startup_timeout=-5)


def test_skip_tag_must_be_non_empty() -> None:
    with pytest.raises(ValueError, match="skip_tag"):
        ExecutionOptions(skip_tag="")


# ── LIBIPYNB-Q2b: hard_kill_grace_period validation ─────────────────────────


def test_hard_kill_grace_period_of_zero_or_negative_is_rejected() -> None:
    with pytest.raises(ValueError, match="hard_kill_grace_period"):
        ExecutionOptions(cell_timeout=5, hard_kill_grace_period=0)
    with pytest.raises(ValueError, match="hard_kill_grace_period"):
        ExecutionOptions(cell_timeout=5, hard_kill_grace_period=-1)


def test_hard_kill_grace_period_requires_cell_timeout() -> None:
    with pytest.raises(ValueError, match="cell_timeout"):
        ExecutionOptions(cell_timeout=None, hard_kill_grace_period=5)


def test_hard_kill_grace_period_requires_interrupt_on_timeout() -> None:
    with pytest.raises(ValueError, match="interrupt_on_timeout"):
        ExecutionOptions(cell_timeout=5, interrupt_on_timeout=False, hard_kill_grace_period=5)


def test_hard_kill_grace_period_none_disables_hard_kill_by_default() -> None:
    options = ExecutionOptions()
    assert options.hard_kill_grace_period is None


def test_hard_kill_grace_period_accepts_a_valid_configuration() -> None:
    options = ExecutionOptions(cell_timeout=5, interrupt_on_timeout=True, hard_kill_grace_period=3)
    assert options.hard_kill_grace_period == 3


def test_options_are_frozen() -> None:
    options = ExecutionOptions()
    with pytest.raises(AttributeError):
        options.stop_on_error = False  # type: ignore[misc]


class TestQ43ExtraEnvIsNotAMutationAfterAccessLeak:
    """LIBIPYNB-Q43 Gate-G2 review finding: extra_env was not copied at
    all, so an ExecutionOptions instance aliased whatever dict the
    caller passed in -- ExecutionOptions is meant to be built once and
    reused (the whole point of freezing it), so a caller mutating their
    own dict *after* construction silently changed what a later
    execute() call using the same options instance would see, despite
    frozen=True."""

    def test_mutating_the_callers_own_dict_after_construction_does_not_leak_in(self) -> None:
        my_env = {"TOKEN": "original"}
        options = ExecutionOptions(acknowledge_unsandboxed=True, extra_env=my_env)

        my_env["TOKEN"] = "MUTATED-AFTER-CONSTRUCTION"

        assert dict(options.extra_env) == {"TOKEN": "original"}

    def test_extra_env_is_not_the_same_object_as_the_callers_dict(self) -> None:
        my_env = {"TOKEN": "original"}
        options = ExecutionOptions(acknowledge_unsandboxed=True, extra_env=my_env)

        assert options.extra_env is not my_env

    def test_mutating_extra_env_directly_is_rejected(self) -> None:
        options = ExecutionOptions(acknowledge_unsandboxed=True, extra_env={"TOKEN": "original"})

        with pytest.raises(TypeError):
            options.extra_env["TOKEN"] = "DIRECT-MUTATION"  # type: ignore[index]

    def test_extra_env_none_stays_none(self) -> None:
        options = ExecutionOptions(acknowledge_unsandboxed=True)
        assert options.extra_env is None
