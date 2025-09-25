import logging
from typing import List

LINE_MAX = 2000

logger = logging.getLogger(__name__)


def truncate(text: str, limit: int = LINE_MAX) -> str:
    if not text:
        return ''
    return text if len(text) <= limit else text[: limit - 10] + '\n...(內容過長已截斷)'


def split_message(text: str, limit: int = LINE_MAX) -> List[str]:
    """Split a long text into pieces not exceeding `limit` (tries to split on newlines/space)."""
    if not text:
        return []
    parts: List[str] = []
    cur = ''
    for line in text.splitlines(True):
        if len(cur) + len(line) <= limit:
            cur += line
        else:
            if cur:
                parts.append(cur)
            if len(line) <= limit:
                cur = line
            else:
                # line itself too long; chunk it
                for i in range(0, len(line), limit):
                    parts.append(line[i:i+limit])
                cur = ''
    if cur:
        parts.append(cur)
    return parts


def safe_log_event(logger: logging.Logger, message: str, **kwargs) -> None:
    """Log an event without dumping sensitive payloads. kwargs should only contain non-sensitive tags."""
    # Only include allowed tags
    allowed = {k: v for k, v in kwargs.items() if k in ('user_id', 'event_type', 'image_size')}
    logger.info('%s %s', message, allowed)
