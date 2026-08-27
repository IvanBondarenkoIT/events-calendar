from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IdempotencyStore:
    """JSON-backed set of already-sent alert keys.

    Thread-safe for local single-process cron use.
    """

    path: Path
    _keys: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def load(cls, path: Path) -> "IdempotencyStore":
        store = cls(path=path)
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            keys = raw.get("sent") if isinstance(raw, dict) else raw
            if isinstance(keys, list):
                store._keys = {str(k) for k in keys}
        return store

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._keys

    def add(self, key: str) -> None:
        with self._lock:
            self._keys.add(key)
            self._persist_unlocked()

    def _persist_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "version": 1,
            "sent": sorted(self._keys),
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
