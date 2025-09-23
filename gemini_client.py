import os
import google.generativeai as genai

API_KEY = os.getenv('GENAI_API_KEY')
if API_KEY:
    try:
        genai.configure(api_key=API_KEY)
    except Exception:
        # allow mocking genai in tests which may not implement configure
        pass

def text_generate(prompt: str) -> str:
    if not API_KEY:
        return '未設定 GENAI_API_KEY'
    try:
        resp = genai.TextGeneration.create(model='gemini-lite', input=prompt)
        return resp.output[0].content[0].text if getattr(resp, 'output', None) else str(resp)
    except Exception:
        return '分析失敗'

def image_analyze(image_bytes: bytes, prompt: str) -> str:
    if not API_KEY:
        return '未設定 GENAI_API_KEY'
    try:
        resp = genai.ImageGeneration.create(model='gemini-image-beta', input=[{'mime_type': 'image/jpeg', 'data': image_bytes}, prompt])
        return getattr(resp, 'output', [{}])[0].get('content', [{}])[0].get('text', '')
    except Exception:
        return '分析失敗'
