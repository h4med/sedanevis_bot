# config.py
import logging
import os
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
import asyncio

from telethon import TelegramClient
from google import genai
from google.genai import types

load_dotenv()

# --- Telegram Configuration ---
ADMIN_USER_ID = int(os.environ['ADMIN_USER_ID'])
TG_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TG_API_ID = os.environ['TELEGRAM_API_ID']
TG_API_HASH = os.environ['TELEGRAM_API_HASH']
TELEGRAM_MAX_BOT_API_FILE_SIZE = 20971520 # 20MB
TG_BOT_NAME=os.environ['TELEGRAM_BOT_NAME']
# --- AI Services Configuration ---
GOOGLE_GEMINI_API_KEY = os.environ['GOOGLE_GEMINI_API_KEY']

DEFAULT_CREDIT_MINUTES = 60.0  # 60 free minutes for all services
TEXT_TOKENS_TO_MINUTES_COEFF = float(os.environ.get('TEXT_TOKENS_TO_MINUTES_COEFF', 1920.0))

# --- Logging Configuration ---
def configure_logging():
    """Sets up the global logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]'
    )
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)

# Google Gemini Client
google_client = genai.Client(api_key=GOOGLE_GEMINI_API_KEY)

# Telethon Client (will be connected on-demand)
telethon_client: TelegramClient | None = None
telethon_lock = asyncio.Lock()

MAX_AUDIO_DURATION_SECONDS = int(os.getenv('MAX_AUDIO_DURATION_SECONDS', 10800)) 
TTS_FARSI_TOKEN_PER_MINUTE_EST = int(os.getenv('TTS_FARSI_TOKEN_PER_MINUTE_EST', 200)) 
TTS_MAX_DURATION_MINUTE = int(os.getenv('TTS_MAX_DURATION_MINUTE', 10))  

TRANSCRIPTION_EXECUTOR = ThreadPoolExecutor(max_workers=2000, thread_name_prefix="transcription_worker")
TOKEN_COUNTING_EXECUTOR = ThreadPoolExecutor(max_workers=100, thread_name_prefix="token_counter")
TEXT_PROCESS_EXECUTOR = ThreadPoolExecutor(max_workers=500, thread_name_prefix="text_processor")
AUDIO_PROCESS_EXECUTOR = ThreadPoolExecutor(max_workers=10, thread_name_prefix="audio_processor")

MAX_CHUNK_LEN = 19
CHUNK_SIZE = 10