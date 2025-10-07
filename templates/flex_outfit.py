# simple Python dict template for Flex message payload
# fields to fill: overall, subscores (dict), summary, suggestions (list of str)

def build_flex_payload(overall: int, subs: dict, summary: str, suggestions: list) -> dict:
    """Build a Flex Message bubble with outfit analysis results.
    
    Args:
        overall: Overall score (0-100)
        subs: Dict of subscores (fit, color, occasion, balance, shoes_bag, grooming)
        summary: Text summary from Gemini
        suggestions: List of suggestion strings (e.g., clothing items to search for)
    
    Returns:
        Dict representing LINE Flex Message bubble format
    """
    # Build contents list starting with scores and summary
    contents = [
        {"type": "text", "text": f"總分: {overall}", "weight": "bold", "size": "xl", "color": "#1DB446"},
        {"type": "separator", "margin": "md"},
        {"type": "text", "text": f"子分數: {'fit': {subs.get('fit', 0)}, 'color': {subs.get('color', 0)}, 'occasion': {subs.get('occasion', 0)}, 'balance': {subs.get('balance', 0)}, 'shoes_bag': {subs.get('shoes_bag', 0)}, 'grooming': {subs.get('grooming', 0)}}", "wrap": True, "size": "sm", "color": "#666666", "margin": "md"},
        {"type": "separator", "margin": "md"},
        {"type": "text", "text": f"摘要: {summary}", "wrap": True, "margin": "md"},
    ]
    
    # Add suggestions section if available
    if suggestions and isinstance(suggestions, list):
        contents.append({"type": "separator", "margin": "md"})
        contents.append({"type": "text", "text": "建議:", "weight": "bold", "margin": "md"})
        
        # Add each suggestion as a separate text element (max 3)
        for i, suggestion in enumerate(suggestions[:3], 1):
            if suggestion and isinstance(suggestion, str):
                contents.append({
                    "type": "text", 
                    "text": f"{i}. {suggestion}", 
                    "wrap": True, 
                    "size": "sm",
                    "margin": "sm"
                })
    
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": contents
        }
    }

