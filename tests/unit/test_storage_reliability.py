from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3
import threading

import pytest

from backend.app.models.schemas import (
    ObservationEnvironment,
    ObservationScope,
    ObservationSource,
    TelemetryObservation,
    ValueQuality,
)
from network.telemetry.metrics_store import MAX_HISTORY_LIMIT, MetricsStore


T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def aggregate(observed_at=T0, download_mbps=1.0):
    return TelemetryObservation(
        metadata={
            "observed_at": observed_at,
            "source": ObservationSource.WINDOWS_HOST,
            "scope": ObservationScope.AGGREGATE_GATEWAY,
            "quality": ValueQuality.MEASURED,
            "environment": ObservationEnvironment.PHYSICAL_HOST,
        },
        download_mbps=download_mbps,
    )


def test_concurrent_writers_serialize_without_corruption(tmp_path):
    store = MetricsStore(tmp_path / "concurrent-writes.sqlite3")
    errors = []

    def write(worker):
        try:
            for index in range(10):
                store.save_observation(
                    aggregate(
                        T0 + timedelta(seconds=worker * 100 + index),
                        download_mbps=float(worker * 10 + index),
                    )
                )
        except Exception as error:  # pragma: no cover - failure path
            errors.append(error)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(write, range(4)))

    assert errors == []
    assert store.count_observations() == 40
    history = store.query_history(limit=MAX_HISTORY_LIMIT, order="oldest")
    assert len(history) == 40
    assert [item.observation.download_mbps for item in history] == sorted(
        item.observation.download_mbps for item in history
    )


def test_concurrent_reads_and_writes_do_not_fail(tmp_path):
    store = MetricsStore(tmp_path / "concurrent-reads.sqlite3")
    errors = []

    def write():
        try:
            for index in range(20):
                store.save_observation(
                    aggregate(T0 + timedelta(milliseconds=index))
                )
        except Exception as error:  # pragma: no cover - failure path
            errors.append(error)

    def read():
        try:
            for _ in range(20):
                store.query_history(limit=10)
                store.count_observations()
                store.get_aggregate_history(limit=10)
        except Exception as error:  # pragma: no cover - failure path
            errors.append(error)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(write)]
        futures.extend(executor.submit(read) for _ in range(3))
        for future in futures:
            future.result()

    assert errors == []
    assert store.count_observations() == 20


def test_write_waits_for_short_lock_and_then_succeeds(tmp_path):
    store = MetricsStore(tmp_path / "locked.sqlite3")
    store.save_observation(aggregate())
    lock_ready = threading.Event()
    release = threading.Event()

    def hold_lock():
        connection = sqlite3.connect(store.db_path, timeout=5.0)
        try:
            connection.execute("BEGIN IMMEDIATE")
            lock_ready.set()
            release.wait(5.0)
            connection.commit()
        finally:
            connection.close()

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert lock_ready.wait(5.0)

    timer = threading.Timer(0.2, release.set)
    timer.start()
    try:
        store.save_observation(aggregate(T0 + timedelta(seconds=1)))
    finally:
        holder.join(5.0)
        timer.cancel()

    assert not holder.is_alive()
    assert store.count_observations() == 2


def test_large_history_query_is_bounded_and_complete(tmp_path):
    store = MetricsStore(tmp_path / "large.sqlite3")
    total = MAX_HISTORY_LIMIT + 5

    batch = []
    for index in range(total):
        batch.append(aggregate(T0 + timedelta(milliseconds=index)))
        if len(batch) == 500:
            store.save_observations(batch)
            batch = []
    if batch:
        store.save_observations(batch)

    assert store.count_observations() == total

    newest = store.query_history(limit=MAX_HISTORY_LIMIT, order="newest")
    oldest = store.query_history(limit=MAX_HISTORY_LIMIT, order="oldest")
    remainder = store.query_history(
        limit=MAX_HISTORY_LIMIT,
        offset=MAX_HISTORY_LIMIT,
        order="oldest",
    )

    assert len(newest) == MAX_HISTORY_LIMIT
    assert len(oldest) == MAX_HISTORY_LIMIT
    assert len(remainder) == 5
    assert newest[0].id > newest[-1].id
    assert oldest[0].id < oldest[-1].id
    assert oldest[0].id == 1
    assert remainder[-1].id == total

    with pytest.raises(ValueError, match="limit"):
        store.query_history(limit=MAX_HISTORY_LIMIT + 1)
