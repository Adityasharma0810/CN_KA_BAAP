"""Unit test: the classifier training split is by RUN with no leakage."""

from __future__ import annotations

import pytest

from ml.classifier.train import MIN_RUNS, split_run_ids


def test_no_run_appears_in_both_train_and_test():
    run_ids = [f"run-{i:02d}" for i in range(12)]
    train, test = split_run_ids(run_ids)
    assert set(train).isdisjoint(set(test))
    assert set(train) | set(test) == set(run_ids)


def test_split_is_deterministic():
    run_ids = [f"run-{i}" for i in range(10)]
    first = split_run_ids(run_ids)
    second = split_run_ids(run_ids)
    assert first == second


def test_test_set_nonempty_for_enough_runs():
    run_ids = [f"run-{i}" for i in range(8)]
    train, test = split_run_ids(run_ids)
    assert len(test) >= 1
    assert len(train) >= len(test)


def test_too_few_runs_yields_no_held_out_split():
    run_ids = [f"run-{i}" for i in range(MIN_RUNS - 1)]
    train, test = split_run_ids(run_ids)
    assert test == []
    assert set(train) == set(run_ids)


def test_repeated_run_ids_are_deduplicated():
    run_ids = ["run-a", "run-a", "run-b", "run-c", "run-d", "run-e"]
    train, test = split_run_ids(run_ids)
    assert len(set(train) | set(test)) == len(set(run_ids))
    assert set(train).isdisjoint(set(test))
