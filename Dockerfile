# Dockerfile 

FROM python:3.12-slim as builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

ARG FFMPEG_VERSION=6.0
ARG FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
WORKDIR /tmp
RUN apt-get update && apt-get install -y --no-install-recommends wget && \
    wget ${FFMPEG_URL} -O ffmpeg.tar.xz && \
    tar -xvf ffmpeg.tar.xz && \
    mv ffmpeg-*-amd64-static/ffmpeg /usr/local/bin/ffmpeg && \
    mv ffmpeg-*-amd64-static/ffprobe /usr/local/bin/ffprobe && \
    rm -rf /tmp/* && \
    apt-get purge -y --auto-remove wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN useradd --system --create-home appuser
WORKDIR /home/appuser/app

COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim

WORKDIR /app
RUN useradd --system --create-home appuser
WORKDIR /home/appuser/app

COPY --from=builder --chown=appuser:appuser /usr/local /usr/local

# Copy the application code
COPY --chown=appuser:appuser . .

RUN mkdir -p downloads persistent_data  && \
    chown -R appuser:appuser downloads persistent_data 

# Switch to the non-root user
USER appuser

# Define the command to run
CMD ["python", "-u", "main.py"]