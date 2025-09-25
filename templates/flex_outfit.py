# simple Python dict template for Flex message payload
# fields to fill: overall, subscores (dict), summary, suggestions (list of str)

def build_flex_payload(overall: int, subs: dict, summary: str, suggestions: list) -> dict:
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": f"總分: {overall}", "weight": "bold", "size": "lg"},
                {"type": "text", "text": f"子分數: {subs}", "wrap": True},
                {"type": "text", "text": f"摘要: {summary}", "wrap": True},
            ]
        },
        "footer": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "建議:"}]}
    }
