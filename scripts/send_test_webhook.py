"""send_test_webhook.py

用法：
  PS> $env:LINE_CHANNEL_SECRET="your_secret"; python .\scripts\send_test_webhook.py --url https://xxxx.ngrok.io/callback

會讀取環境變數 `LINE_CHANNEL_SECRET` 作為簽章 key，並將示例事件 POST 到指定 URL，包含正確的 `X-Line-Signature`。
"""
import os
import argparse
import hmac
import hashlib
import base64
import json
import requests

SAMPLE_EVENT = {
    "events": [
        {
            "type": "message",
            "message": {"type": "text", "text": "hello from test script"},
            "replyToken": "00000000000000000000000000000000",
            "source": {"userId": "U1234567890", "type": "user"}
        }
    ]
}


def make_signature(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode('utf-8'), body, hashlib.sha256)
    sig = base64.b64encode(mac.digest()).decode('utf-8')
    return sig


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--url', '-u', default=os.environ.get('WEBHOOK_URL', 'http://localhost:5000/callback'))
    p.add_argument('--text', '-t', default='hello from test script')
    args = p.parse_args()

    secret = os.environ.get('LINE_CHANNEL_SECRET')
    if not secret:
        print('ERROR: set LINE_CHANNEL_SECRET env var first')
        return

    event = SAMPLE_EVENT.copy()
    event['events'][0]['message']['text'] = args.text
    body = json.dumps(event).encode('utf-8')
    sig = make_signature(secret, body)

    headers = {
        'Content-Type': 'application/json',
        'X-Line-Signature': sig
    }

    print(f'POST {args.url} with X-Line-Signature: {sig}')
    r = requests.post(args.url, headers=headers, data=body, timeout=10)
    print('status:', r.status_code)
    try:
        print('resp:', r.text)
    except Exception:
        pass


if __name__ == '__main__':
    main()
