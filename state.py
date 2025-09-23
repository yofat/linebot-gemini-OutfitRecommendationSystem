from datetime import datetime, timedelta
import threading
from typing import Dict, Any, Optional

_lock = threading.Lock()
_states: Dict[str, Dict[str, Any]] = {}
EXP_MIN = 10

def set_state(user_id: str, **kwargs: Any) -> None:
    with _lock:
        s = _states.get(user_id, {})
        s.update(kwargs)
        s['ts'] = datetime.utcnow()
        _states[user_id] = s

def get_state(user_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return _states.get(user_id)

def clear_state(user_id: str) -> None:
    with _lock:
        _states.pop(user_id, None)

def cleanup():
    now = datetime.utcnow()
    with _lock:
        for uid, s in list(_states.items()):
            if 'ts' in s and now - s['ts'] > timedelta(minutes=EXP_MIN):
                _states.pop(uid, None)


# backward-compatible alias for tests / external inspection
user_state = _states
