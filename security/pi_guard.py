import re
from typing import Dict

# keywords/patterns that commonly indicate prompt injection attempts
_PI_PATTERNS = [
    r'ignore previous', r'disregard previous', r'ignore the above', r'overrule', r'override',
    r'act as system', r'reveal system prompt', r'show your prompt', r'print env', r'print environment',
    r'api ?key', r'secret', r'token', r'\$\{\{.*\}\}', r'\{\{.*\}\}', r'密鑰', r'金鑰', r'環境變數',
    r'系統提示', r'顯示程式碼', r'顯示原文', r'忽略前面', r'請用root', r'sudo', r'/etc/passwd',
]

# compile regex for performance
_PI_RE = re.compile('|'.join(_PI_PATTERNS), flags=re.IGNORECASE)
_URL_RE = re.compile(r'https?://\S+|www\.\S+', flags=re.IGNORECASE)
_ZERO_WIDTH_RE = re.compile(r'[\u200B-\u200D\uFEFF]')


def scan_prompt_injection(text: str) -> Dict[str, str]:
    """Scan text for prompt injection keywords/patterns.

    Returns dict: {"detected": bool, "reason": str}
    """
    if not text:
        return {"detected": False, "reason": ""}

    # quick checks
    if _PI_RE.search(text):
        return {"detected": True, "reason": "matched pi pattern"}
    if _URL_RE.search(text):
        # URLs may contain tokens/paths; flag for manual review
        return {"detected": True, "reason": "contains url"}
    return {"detected": False, "reason": ""}


def sanitize_user_text(text: str, max_len: int = 4096) -> str:
    """Sanitize user input before composing prompt.

    - remove zero-width/control characters
    - truncate long text
    - strip leading/trailing whitespace
    """
    if not text:
        return ''
    s = _ZERO_WIDTH_RE.sub('', text)
    s = s.replace('\r', '\n')
    # collapse multiple newlines
    s = re.sub(r'\n{3,}', '\n\n', s)
    if len(s) > max_len:
        s = s[:max_len]
    return s.strip()
