# SedaNevis Telegram Bot

Transcribes audio files and deliver transcription also options for some text processing actions.

## Features
- Audio Transcription
- Text Processing

## Requirements
- Python 3.x
- Docker
- API Kyes (for Telegram and Gemini)

## Installation
rename `.env.example` to `.env` then add your API keys, do the same for `prompts.example.py`, edit `prompts.py` to add needed prompts for transcription and other actions, Then

```bash
docker compose build
```

## Usage
```bash
docker compose up -d && docker compose logs -f
```
