import os
import sys
import types


def _make_linebot_fake():
    mod = types.ModuleType("linebot")

    class LineBotApi:
        def __init__(self, token=None):
            self.token = token

        def get_profile(self, user_id):
            class P:
                display_name = "測試用戶"

            return P()

        def get_message_content(self, message_id):
            # return bytes-like iterable
            return [b"fakeimage"]

        def reply_message(self, reply_token, message):
            return None

    class WebhookHandler:
        def __init__(self, secret=None):
            self.secret = secret

        def handle(self, body, signature):
            return None

        def add(self, *args, **kwargs):
            # return a decorator that returns the function unchanged
            def _decorator(func):
                return func

            return _decorator

    mod.LineBotApi = LineBotApi
    mod.WebhookHandler = WebhookHandler

    # exceptions submodule
    exc = types.ModuleType("linebot.exceptions")

    class InvalidSignatureError(Exception):
        pass

    exc.InvalidSignatureError = InvalidSignatureError

    models = types.ModuleType("linebot.models")

    class MessageEvent:
        pass

    class TextMessage:
        pass

    class ImageMessage:
        pass

    class TextSendMessage:
        def __init__(self, text=""):
            self.text = text

    models.MessageEvent = MessageEvent
    models.TextMessage = TextMessage
    models.ImageMessage = ImageMessage
    models.TextSendMessage = TextSendMessage

    sys.modules['linebot'] = mod
    sys.modules['linebot.exceptions'] = exc
    sys.modules['linebot.models'] = models


def _make_genai_fake():
    mod = types.ModuleType("google.generativeai")

    def configure(api_key=None):
        return None

    class GenerativeModel:
        def __init__(self, name=None):
            self.name = name

        def generate_content(self, parts, request_options=None):
            class R:
                text = "(fake)"

            return R()

    mod.configure = configure
    mod.GenerativeModel = GenerativeModel

    sys.modules['google'] = types.ModuleType('google')
    sys.modules['google.generativeai'] = mod


def pytest_configure(config):
    # 設定環境變數以避免 app 在 import 時失敗
    os.environ.setdefault('GENAI_API_KEY', 'fake_key')
    os.environ.setdefault('LINE_CHANNEL_ACCESS_TOKEN', 'fake_token')
    os.environ.setdefault('LINE_CHANNEL_SECRET', 'fake_secret')

    _make_linebot_fake()
    _make_genai_fake()
