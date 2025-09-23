LINE_MAX = 2000

def truncate(text: str, limit: int = LINE_MAX) -> str:
    if not text:
        return ''
    return text if len(text) <= limit else text[: limit - 10] + '\n...(內容過長已截斷)'
