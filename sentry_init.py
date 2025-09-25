import os
try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
except Exception:
    sentry_sdk = None


def init_sentry():
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
            traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.0')),
            send_default_pii=False,
        )
        return True
    except Exception:
        return False
