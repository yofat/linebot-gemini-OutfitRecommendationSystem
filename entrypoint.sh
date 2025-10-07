#!/bin/sh
# Entrypoint script for container startup
# Loads GENAI_API_KEY from Render Secret Files if available

set -e

# If using Render Secret Files, load them first
if [ -f /etc/secrets/GENAI_API_KEY ] && [ -z "$GENAI_API_KEY" ]; then
    export GENAI_API_KEY=$(cat /etc/secrets/GENAI_API_KEY)
    echo "Startup: loaded GENAI_API_KEY from /etc/secrets"
fi

# Backward compatibility: Set GOOGLE_API_KEY from GENAI_API_KEY
# (New google-genai SDK primarily uses API key from Client(api_key=...),
# but this ensures compatibility with any code still checking env vars)
if [ -n "$GENAI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
    export GOOGLE_API_KEY="$GENAI_API_KEY"
    echo "Startup: set GOOGLE_API_KEY for compatibility"
fi

# Execute the main command (e.g., gunicorn)
exec "$@"

