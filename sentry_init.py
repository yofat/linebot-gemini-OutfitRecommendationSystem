import os
try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
except Exception:
    sentry_sdk = None


def init_sentry() -> bool:
    """Initialize Sentry if SENTRY_DSN present. Returns True if initialized."""
    dsn = os.getenv('SENTRY_DSN')
    if not dsn or not sentry_sdk:
        return False

    # Capture warnings and errors from logging
    logging_integration = LoggingIntegration(level=None, event_level=None)
    try:
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration(), logging_integration],
            traces_sample_rate=float(os.getenv('SENTRY_TRACES', os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.1'))),
            environment=os.getenv('ENVIRONMENT', 'dev'),
            release=os.getenv('RELEASE', 'local'),
            send_default_pii=False,
        )
        return True
    except Exception:
        return False


def capture_exception(exc: Exception):
    if sentry_sdk:
        try:
            sentry_sdk.capture_exception(exc)
        except Exception:
            pass


def set_user(user: dict):
    if sentry_sdk and user:
        try:
            sentry_sdk.set_user(user)
        except Exception:
            pass


def set_tag(key: str, value):
    if sentry_sdk:
        try:
            sentry_sdk.set_tag(key, value)
        except Exception:
            pass


def set_extra(key: str, value):
    if sentry_sdk:
        try:
            sentry_sdk.set_extra(key, value)
        except Exception:
            pass
