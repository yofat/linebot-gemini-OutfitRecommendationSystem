import os
try:
    import sentry_sdk
except Exception:
    sentry_sdk = None

def init_sentry():
    dsn = os.getenv('SENTRY_DSN')
    if not dsn or not sentry_sdk:
        return False
    sentry_sdk.init(dsn)
    return True
