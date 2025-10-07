# Gunicorn config - simple sensible defaults
bind = '0.0.0.0:5000'
workers = 2
# Increase timeout because remote Gemini calls can sometimes take >30s and
# a short worker timeout will cause gunicorn to kill the worker (seen in
# logs as WORKER TIMEOUT). Set to 120s to be safer; you can tune via env
# in production if necessary.
timeout = 120
accesslog = '-'  # stdout
errorlog = '-'   # stderr
