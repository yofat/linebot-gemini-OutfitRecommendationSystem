FROM python:3.11-slim
WORKDIR /app

# Install minimal OS deps required by many wheels (openssl, zlib). Avoid heavy build tools
# unless a package needs to be compiled — this keeps image smaller and CI faster.
RUN apt-get update \
	 && apt-get install -y --no-install-recommends \
		 ca-certificates \
	 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# Install Python deps. If any package truly needs compilation, consider adding a
# small build stage or temporarily enabling build-essential in CI only.
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
EXPOSE 5000

# Run with gunicorn in production for better concurrency.
CMD ["gunicorn", "app:app", "-c", "gunicorn.conf.py"]
