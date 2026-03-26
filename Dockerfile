FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Pillow + onnxruntime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Pre-download the model at build time so first request is fast
RUN python -c "from rembg import new_session; new_session('isnet-general-use')"

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
