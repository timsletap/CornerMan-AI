FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    ffmpeg \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download pose weights so workers start offline. They live outside /app because
# docker-compose bind-mounts ./backend over /app; Ultralytics falls back to weights_dir
# when YOLO(<name>) is not found in the working directory.
ARG YOLO_MODEL_NAME=yolov8m-pose.pt
ENV YOLO_CONFIG_DIR=/opt/ultralytics
RUN mkdir -p /opt/models \
    && python -c "from ultralytics import settings; settings.update({'weights_dir': '/opt/models'})" \
    && python -c "from ultralytics.utils.downloads import attempt_download_asset; attempt_download_asset('/opt/models/${YOLO_MODEL_NAME}')" \
    && test -s /opt/models/${YOLO_MODEL_NAME}

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
