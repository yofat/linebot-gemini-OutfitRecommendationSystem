# Gunicorn config - simple sensible defaults
bind = '0.0.0.0:5000'
workers = 2
timeout = 30
accesslog = '-'  # stdout
errorlog = '-'   # stderr
