#!/bin/sh
# Entrypoint script for container startup
# This ensures GOOGLE_API_KEY is set from GENAI_API_KEY BEFORE Python starts,
# avoiding DefaultCredentialsError from google.auth.default() during module import.

set -e

# Synchronize GENAI_API_KEY -> GOOGLE_API_KEY at the OS level (before Python runs)
if [ -n "$GENAI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
    export GOOGLE_API_KEY="$GENAI_API_KEY"
    echo "Startup: synchronized GENAI_API_KEY -> GOOGLE_API_KEY"
fi

# If using Render Secret Files, load them first (optional check)
if [ -f /etc/secrets/GENAI_API_KEY ] && [ -z "$GENAI_API_KEY" ]; then
    export GENAI_API_KEY=$(cat /etc/secrets/GENAI_API_KEY)
    echo "Startup: loaded GENAI_API_KEY from /etc/secrets"
fi

if [ -n "$GENAI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
    export GOOGLE_API_KEY="$GENAI_API_KEY"
    echo "Startup: synchronized GENAI_API_KEY -> GOOGLE_API_KEY (from secret file)"
fi

# Execute the main command (e.g., gunicorn)
exec "$@"
