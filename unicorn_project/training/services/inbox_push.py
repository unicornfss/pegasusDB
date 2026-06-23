"""Real-time inbox push via in-process queues + shared cache stamps."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from django.core.cache import cache

_lock = threading.Lock()
_subscribers: dict[str, list[queue.Queue]] = {}


def _cache_key(personnel_id) -> str:
    return f"inbox:notify:{personnel_id}"


def build_inbox_payload(personnel) -> dict[str, int]:
    from .staff_inbox import unread_inbox_count

    staff = unread_inbox_count(personnel, scope="staff")
    admin = unread_inbox_count(personnel, scope="admin")
    return {
        "staff_unread_count": staff,
        "admin_unread_count": admin,
        "unread_count": staff + admin,
    }


def get_cache_stamp(personnel_id) -> float | None:
    return cache.get(_cache_key(str(personnel_id)))


def publish(personnel_id, payload: dict[str, Any]) -> None:
    personnel_id = str(personnel_id)
    cache.set(_cache_key(personnel_id), time.time(), timeout=86400)
    with _lock:
        for subscriber in _subscribers.get(personnel_id, []):
            try:
                subscriber.put_nowait(payload)
            except queue.Full:
                pass


def notify_personnel(personnel) -> None:
    if not personnel:
        return
    publish(personnel.pk, build_inbox_payload(personnel))


def subscribe(personnel_id) -> queue.Queue:
    personnel_id = str(personnel_id)
    subscriber = queue.Queue(maxsize=16)
    with _lock:
        _subscribers.setdefault(personnel_id, []).append(subscriber)
    return subscriber


def unsubscribe(personnel_id, subscriber: queue.Queue) -> None:
    personnel_id = str(personnel_id)
    with _lock:
        queues = _subscribers.get(personnel_id, [])
        if subscriber in queues:
            queues.remove(subscriber)
        if not queues:
            _subscribers.pop(personnel_id, None)
