from datetime import datetime, timedelta, timezone
import threading
from typing import Dict, Any, Optional
import json

try:
    import redis
except Exception:
    redis = None


class StateBackend:
    def set_state(self, user_id: str, **kwargs: Any) -> None:
        raise NotImplementedError

    def get_state(self, user_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def clear_state(self, user_id: str) -> None:
        raise NotImplementedError

    def cleanup(self) -> None:
        raise NotImplementedError


class MemoryState(StateBackend):
    def __init__(self, exp_min: int = 60):
        self._lock = threading.Lock()
        self._states: Dict[str, Dict[str, Any]] = {}
        self.exp_min = exp_min

    def set_state(self, user_id: str, **kwargs: Any) -> None:
        with self._lock:
            s = self._states.get(user_id, {})
            # merge provided keys into existing state
            s.update(kwargs)
            # ensure timestamp for expiry checks
            s['ts'] = datetime.now(timezone.utc)
            self._states[user_id] = s

    def get_state(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._states.get(user_id)

    def clear_state(self, user_id: str) -> None:
        with self._lock:
            self._states.pop(user_id, None)

    def cleanup(self) -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            for uid, s in list(self._states.items()):
                if 'ts' in s and now - s['ts'] > timedelta(minutes=self.exp_min):
                    self._states.pop(uid, None)


class RedisState(StateBackend):
    def __init__(self, url: str = 'redis://localhost:6379/0', ttl_seconds: int = 3600):
        if not redis:
            raise RuntimeError('redis package not available')
        self._client = redis.from_url(url)
        self.ttl = ttl_seconds

    def _key(self, user_id: str) -> str:
        return f'state:{user_id}'

    def set_state(self, user_id: str, **kwargs: Any) -> None:
        key = self._key(user_id)
        data = {k: v for k, v in kwargs.items()}
        data['ts'] = datetime.now(timezone.utc).isoformat()
        self._client.hset(key, mapping=data)
        self._client.expire(key, self.ttl)

    def get_state(self, user_id: str) -> Optional[Dict[str, Any]]:
        key = self._key(user_id)
        if not self._client.exists(key):
            return None
        raw = self._client.hgetall(key)
        # decode bytes to str on py3
        out = {k.decode() if isinstance(k, bytes) else k: (v.decode() if isinstance(v, bytes) else v) for k, v in raw.items()}
        # if ts exists, parse to timezone-aware datetime
        if 'ts' in out:
            try:
                out['ts'] = datetime.fromisoformat(out['ts'])
            except Exception:
                # keep raw string if parse fails
                pass
        return out

    def clear_state(self, user_id: str) -> None:
        self._client.delete(self._key(user_id))

    def cleanup(self) -> None:
        # Redis keys expire automatically
        return


# default backend selection
_backend: StateBackend = MemoryState()


def set_backend(backend: StateBackend):
    global _backend
    _backend = backend


def set_state(user_id: str, **kwargs: Any) -> None:
    _backend.set_state(user_id, **kwargs)


def get_state(user_id: str) -> Optional[Dict[str, Any]]:
    return _backend.get_state(user_id)


def clear_state(user_id: str) -> None:
    _backend.clear_state(user_id)


def cleanup() -> None:
    _backend.cleanup()


# backward-compatible alias
user_state = None
