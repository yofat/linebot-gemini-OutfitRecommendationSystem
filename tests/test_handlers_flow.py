import types
import pytest

import handlers
from state import user_state


class DummyLineApi:
    def __init__(self):
        self.replies = []

    def reply_message(self, reply_token, message):
        self.replies.append((reply_token, getattr(message, 'text', str(message))))

    def get_message_content(self, message_id):
        return [b'fakeimagebytes']


class DummyHandler:
    def __init__(self):
        self._callbacks = []

    def add(self, *args, **kwargs):
        # handlers.register_handlers calls handler.add(MessageEvent, message=TextMessage)
        # so message class may be in kwargs['message'] or as second positional arg
        expected_msg = None
        if 'message' in kwargs:
            expected_msg = kwargs['message']
        elif len(args) >= 2:
            # assume args[1] is the message class
            expected_msg = args[1]

        def _decor(f):
            # wrap with a guard that checks the event.message type if provided
            def guarded(event):
                if expected_msg is None:
                    return f(event)
                ok = isinstance(event.message, expected_msg)
                if not ok:
                    # fallback heuristics: allow duck-typed test doubles
                    name = getattr(expected_msg, '__name__', '')
                    if name == 'TextMessage' and hasattr(event.message, 'text'):
                        ok = True
                    if name == 'ImageMessage' and hasattr(event.message, 'id'):
                        ok = True
                if ok:
                    return f(event)
                return None

            self._callbacks.append(guarded)
            return f

        return _decor

    # helper to invoke registered callbacks
    def invoke_all(self, event):
        for cb in self._callbacks:
            cb(event)


class DummyEvent:
    def __init__(self, source_user_id, message):
        self.source = types.SimpleNamespace(user_id=source_user_id)
        self.message = message
        self.reply_token = 'rt'


class DummyTextMessage:
    def __init__(self, text):
        self.text = text


class DummyImageMessage:
    def __init__(self, mid):
        self.id = mid


def test_text_then_image_flow(monkeypatch):
    api = DummyLineApi()
    handler = DummyHandler()
    # register handlers with our dummy
    handlers.register_handlers(api, handler)

    # simulate text event
    text_event = DummyEvent('u1', DummyTextMessage('參加面試'))
    handler.invoke_all(text_event)
    # new state-machine asks for location/scene first
    assert api.replies and '請描述地點或場景' in api.replies[-1][1]

    # simulate image event
    img_event = DummyEvent('u1', DummyImageMessage('m1'))
    handler.invoke_all(img_event)
    # should have replied again (either analysis or error string)
    assert len(api.replies) >= 2
