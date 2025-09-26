import re
from typing import Optional, Tuple

PRICE_RE = re.compile(r'(NT\$|NT\s*|\$|＄)\s*([0-9]{1,3}(?:[,，][0-9]{3})*(?:\.[0-9]+)?)', re.I)


Price = Tuple[str, int]


def extract_price(text: str) -> Optional[Price]:
    if not text:
        return None
    m = PRICE_RE.search(text)
    if not m:
        return None
    price_text = m.group(0)
    num = m.group(2)
    num_clean = int(re.sub(r'[,，]', '', num).split('.')[0])
    return (price_text, num_clean)
