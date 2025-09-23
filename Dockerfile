FROM python:3.11-slim
WORKDIR /app
# install system deps if needed (e.g., for pillow, libjpeg)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
	&& rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
EXPOSE 5000
# Run with gunicorn in production for better concurrency
# Example: docker run -e LINE_CHANNEL_ACCESS_TOKEN=... -e GENAI_API_KEY=... -p 5000:5000 image
CMD ["gunicorn", "app:app", "-c", "gunicorn.conf.py"]
