FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg fonts-dejavu-core fonts-crosextra-carlito \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY worker/requirements.txt worker/requirements.txt
RUN pip install --no-cache-dir -r worker/requirements.txt

COPY render_core/ render_core/
COPY tools/ tools/
COPY assets/ assets/
COPY worker/ worker/

ENV OUTPUT_DIR=/var/data/renders
EXPOSE 10000
CMD ["uvicorn", "worker.app:app", "--host", "0.0.0.0", "--port", "10000"]
