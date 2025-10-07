import os
import json
import logging
from typing import Optional

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None

try:
    from prompts import TASK_INSTRUCTION
except Exception:
    TASK_INSTRUCTION = ''

logger = logging.getLogger(__name__)


class GeminiError(Exception):
    pass


class GeminiTimeoutError(GeminiError):
    pass


class GeminiAPIError(GeminiError):
    pass


_GENAI_CLIENT = None


def _get_api_key() -> Optional[str]:
    """Get API key from environment variables."""
    key = os.getenv('GENAI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    return key


def _ensure_configured():
    """Configure genai SDK lazily if possible."""
    global _GENAI_CLIENT
    if _GENAI_CLIENT:
        return _GENAI_CLIENT

    key = _get_api_key()
    if key and genai:
        try:
            # Use new google-genai SDK with Client
            _GENAI_CLIENT = genai.Client(api_key=key)
            logger.info('Gemini client configured successfully')
            return _GENAI_CLIENT
        except Exception as e:
            logger.error('Failed to configure Gemini client: %s', e)
            return None
    return None


def analyze_outfit_image(scene: str, purpose: str, time_weather: str,
                        image_bytes: bytes, mime: str = 'image/jpeg',
                        timeout: int = 15) -> dict:
    """
    Multimodal image->JSON analyzer using the new google-genai SDK Client API.

    Returns a dict matching the expected schema. On failure, returns a fallback dict.
    """
    if not _get_api_key() or not genai:
        raise GeminiAPIError('未設定 GENAI_API_KEY or genai not available')

    client = _ensure_configured()
    if not client:
        raise GeminiAPIError('Failed to initialize Gemini client')

    # Build prompt from provided context
    base_task = TASK_INSTRUCTION if TASK_INSTRUCTION else ''

    # Provide an explicit JSON schema and an example
    schema = (
        "請依據下列 JSON schema 回傳唯一一個 JSON 物件 (只回傳 JSON, 不要任何額外說明):\n"
        "{\n"
        "  \"overall_score\": number,\n"
        "  \"subscores\": {\n"
        "    \"fit\": number,\n"
        "    \"color\": number,\n"
        "    \"occasion\": number,\n"
        "    \"balance\": number,\n"
        "    \"shoes_bag\": number,\n"
        "    \"grooming\": number\n"
        "  },\n"
        "  \"summary\": string,\n"
        "  \"suggestions\": [string, string, string],  // 每項必須是簡潔的服飾描述,格式: [顏色][材質/風格][服飾類型]\n"
        "  \"gender\": string,             // 可選: 男性/女性/不公開/空字串\n"
        "  \"preferences\": [string, ...]  // 可選: 偏好詞彙，如 [\"蕾絲\", \"合身\"]\n"
        "}\n"
        "重要規則:\n"
        "1. suggestions 使用繁體中文,格式簡潔: [顏色] + [服飾類型] (例如: '白色襯衫'、'深藍色西裝褲'、'棕色皮鞋')\n"
        "2. 避免過度描述,不要加入太多形容詞(例如: ❌'白色亞麻質地輕薄透氣長褲' → ✓'白色長褲')\n"
        "3. 僅推薦服飾或鞋類,嚴禁推薦包包、配件、飾品\n"
        "4. 每個建議應該是可以直接搜尋的商品關鍵字\n"
    )

    example = (
        "範例輸出 (僅示範格式):\n"
        "{\n"
        "  \"overall_score\": 85,\n"
        "  \"subscores\": {\n"
        "    \"fit\": 80,\n"
        "    \"color\": 90,\n"
        "    \"occasion\": 85,\n"
        "    \"balance\": 80,\n"
        "    \"shoes_bag\": 75,\n"
        "    \"grooming\": 90\n"
        "  },\n"
        "  \"summary\": \"整體搭配良好，可再調整色彩平衡。\",\n"
        "  \"suggestions\": [\"白色襯衫\", \"深藍色西裝褲\", \"棕色皮鞋\"],\n"
        "  \"gender\": \"女性\",\n"
        "  \"preferences\": [\"蕾絲\", \"合身\"]\n"
        "}\n"
    )

    # Build context text
    context_text = f"場景：{scene}\n目的：{purpose}\n時間/天氣：{time_weather}\n"
    
    # Combine to final prompt
    prompt = base_task + "\n" + schema + "\n" + example + "\n" + context_text
    
    # Use new google-genai SDK Client API
    # According to official docs, use gemini-2.5-flash for free tier
    model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    
    logger.info('Using Gemini model: %s', model_name)
    
    try:
        # Create content with text prompt and image using new SDK
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt, types.Part.from_bytes(data=image_bytes, mime_type=mime)]
        )
        
        # Extract text from response
        text = response.text
        logger.debug('Gemini response length: %d chars', len(text))
        
        # Try to parse JSON from response
        try:
            # Remove markdown code block markers if present
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0].strip()
            elif '```' in text:
                text = text.split('```')[1].split('```')[0].strip()
            
            result = json.loads(text)
            
            # Validate required fields
            if 'overall_score' not in result or 'summary' not in result:
                logger.warning('Gemini response missing required fields')
                return _fallback_outfit_json('Response missing required fields')
            
            logger.info('Successfully parsed Gemini response')
            return result
            
        except json.JSONDecodeError as je:
            logger.warning('Failed to parse Gemini JSON response: %s', je)
            logger.debug('Raw response text: %s', text[:500])
            return _fallback_outfit_json(f'Failed to parse JSON: {je}')
            
    except Exception as e:
        msg = str(e)
        msg_lower = msg.lower()
        logger.exception('Error calling Gemini API')
        
        # Handle model not found errors
        if ('not found' in msg_lower or 'does not exist' in msg_lower):
            logger.error('Model %s not available', model_name)
            return _fallback_outfit_json(f'Model {model_name} not available. Try setting GEMINI_MODEL=gemini-2.0-flash-exp or gemini-1.5-flash')
        
        # Handle quota errors
        if 'quota' in msg_lower or '429' in msg:
            return _fallback_outfit_json('API quota exceeded, please try again later')
        
        # Generic error
        return _fallback_outfit_json(f'API error: {msg}')


def _fallback_outfit_json(reason: str) -> dict:
    """Return a fallback JSON response when analysis fails."""
    logger.warning('Returning fallback outfit JSON: %s', reason)
    return {
        "overall_score": 0,
        "subscores": {
            "fit": 0,
            "color": 0,
            "occasion": 0,
            "balance": 0,
            "shoes_bag": 0,
            "grooming": 0
        },
        "summary": f"無法分析圖片: {reason}",
        "suggestions": [],
        "gender": "",
        "preferences": []
    }


# Compatibility functions for existing code that may call these
def text_generate(prompt: str, retries: int = 3, timeout: Optional[float] = None) -> str:
    """Legacy function for text generation."""
    if not _get_api_key() or not genai:
        return '未設定 GENAI_API_KEY'
    
    client = _ensure_configured()
    if not client:
        return '無法初始化 Gemini client'
    
    try:
        model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text
    except Exception as e:
        logger.exception('Error in text_generate')
        return f'Error: {e}'


def image_analyze(image_bytes: bytes, prompt: str, retries: int = 3, timeout: Optional[float] = None) -> str:
    """Legacy function for image analysis."""
    if not _get_api_key() or not genai:
        return '未設定 GENAI_API_KEY'
    
    client = _ensure_configured()
    if not client:
        return '無法初始化 Gemini client'
    
    try:
        model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt, types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg')]
        )
        return response.text
    except Exception as e:
        logger.exception('Error in image_analyze')
        return f'Error: {e}'


def translate_to_japanese_keywords(chinese_suggestions: list) -> list:
    """Translate Chinese clothing suggestions to Japanese search keywords for Rakuten API.
    
    Args:
        chinese_suggestions: List of Chinese clothing descriptions (e.g., ["白色襯衫", "深藍色西裝褲"])
    
    Returns:
        List of Japanese search keywords (e.g., ["ホワイト シャツ", "ネイビー スラックス"])
    """
    if not chinese_suggestions or not isinstance(chinese_suggestions, list):
        return []
    
    client = _ensure_configured()
    if not client:
        logger.warning('Cannot translate suggestions: Gemini client not configured')
        return chinese_suggestions  # Fallback to original
    
    try:
        # Build translation prompt
        items_text = '\n'.join([f'{i+1}. {s}' for i, s in enumerate(chinese_suggestions)])
        prompt = (
            f"將以下中文服飾翻譯成日文搜尋關鍵字(用於日本樂天購物網站):\n\n"
            f"{items_text}\n\n"
            f"翻譯規則:\n"
            f"1. 顏色用片假名: 白色→ホワイト、黑色→ブラック、藍色→ブルー、深藍色→ネイビー、紅色→レッド、灰色→グレー、棕色→ブラウン\n"
            f"2. 服飾類型:\n"
            f"   - 襯衫→シャツ\n"
            f"   - 西裝褲→スラックス\n"
            f"   - 長褲→パンツ\n"
            f"   - 皮鞋/樂福鞋→ローファー\n"
            f"   - 涼鞋→サンダル\n"
            f"   - T恤→Tシャツ\n"
            f"   - 外套→ジャケット\n"
            f"3. 保持簡潔,去除不必要的形容詞\n"
            f"4. 每行一個翻譯,不要編號,不要其他文字\n\n"
            f"日文關鍵字:"
        )
        
        model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        
        # Parse response - expect one keyword per line
        japanese_keywords = []
        for line in response.text.strip().split('\n'):
            line = line.strip()
            # Remove numbering if present (e.g., "1. " or "1) ")
            if line and len(line) > 0:
                # Remove leading numbers and punctuation
                import re
                cleaned = re.sub(r'^\d+[\.\)]\s*', '', line)
                if cleaned:
                    japanese_keywords.append(cleaned)
        
        # Ensure we have same number of translations
        if len(japanese_keywords) != len(chinese_suggestions):
            logger.warning('Translation count mismatch: %d vs %d, using original', 
                         len(japanese_keywords), len(chinese_suggestions))
            return chinese_suggestions
        
        logger.info('Translated suggestions: %s -> %s', chinese_suggestions, japanese_keywords)
        return japanese_keywords
        
    except Exception as e:
        logger.exception('Failed to translate suggestions to Japanese')
        return chinese_suggestions  # Fallback to original

