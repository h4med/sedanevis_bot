# ai_services.py
import logging
import time
from google.genai import types

import io  
import wave 
from pydub import AudioSegment 

# Import the initialized client from our config file
from config import google_client
from texts import Texts


def count_text_tokens(text: str, model: str = "gemini-2.0-flash-lite") -> int:
    """
    Counts the number of tokens in a given text using the specified Gemini model.
    Returns the token count or 0 if an error occurs.
    """
    try:
        response = google_client.models.count_tokens(model=model, contents=text)
        return response.total_tokens
    except Exception as e:
        logging.error(f"Error during token counting: {e}", exc_info=True)
        return 0

def transcribe_audio_google_sync(file_path: str, duration_seconds: int, model: str , prompt: str) -> dict:
    """
    Synchronous transcription function - to be run in thread pool.
    Returns a dictionary with transcription and usage data or an error.
    """
    try:
        logging.info(f"Uploading audio {file_path} to Google for transcription.")
        start_time = time.time()
        uploaded_file = google_client.files.upload(file=file_path)
        logging.info(f"Uploaded audio {file_path} to Google: {uploaded_file.uri}")
        max_tokens = duration_seconds * 15
        # max_tokens = 65536
        
        transcription_response = google_client.models.generate_content(
            model=model,
            contents=[prompt, uploaded_file],
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                temperature=1,
                topP=0.95,
                max_output_tokens=max_tokens,
            ),
        )
        
        duration = time.time() - start_time
        logging.info(f"Successfully received  the response from Gemini. duration: {duration:.2f}s")

        if transcription_response is None:
            return {"error": "Google API returned empty response"}
        
        transcription_text = ""
        if hasattr(transcription_response, 'text') and transcription_response.text is not None:
            transcription_text = transcription_response.text.strip()
        else:
            logging.warning(f"Transcription response text is None for file: {file_path}")
            transcription_text = ""

        usage = transcription_response.usage_metadata if hasattr(transcription_response, 'usage_metadata') else None
        prompt_token_count = 0
        candidates_token_count = 0
        total_token_count = 0

        if usage is not None:
            prompt_token_count = getattr(usage, 'prompt_token_count', 0) or 0
            candidates_token_count = getattr(usage, 'candidates_token_count', 0) or 0
            total_token_count = getattr(usage, 'total_token_count', 0) or 0
        
        return {
            "transcription": transcription_text,
            "prompt_token_count": prompt_token_count,
            "candidates_token_count": candidates_token_count,
            "total_token_count": total_token_count,
        }
    except Exception as e:
        logging.error(f"Error during Google transcription: {e}", exc_info=True)
        return {"error": f"An error occurred during Google transcription: {e}"}
    
def process_text_with_gemini(prompt_text: str, model: str = "gemini-2.5-flash-lite-preview-09-2025", max_tokens:int = 1024) -> dict:
    """
    Sends a text prompt to a GEMINI model and returns the response.
    Returns a dictionary with the generated text and usage data or an error.
    model1: gemini-2.5-flash-lite
    model2: gemini-2.5-flash
    """
    try:
        logging.info(f"Processing text with Gemini model: {model}")
        response = google_client.models.generate_content(
            model=model,
            contents=prompt_text,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0), 
                temperature=0.9,
                topP=0.95,
                max_output_tokens=max_tokens
            ),
        )

        usage = response.usage_metadata
        return {
            "text": response.text.strip(),
            "prompt_token_count": usage.prompt_token_count,
            "candidates_token_count": usage.candidates_token_count,
            "total_token_count": usage.total_token_count,
        }
    except Exception as e:
        logging.error(f"Error during Gemini text processing: {e}", exc_info=True)
        return {"error": f"An error occurred during Gemini text processing: {e}"}

def generate_speech_gemini(text: str) -> dict:
    """
    Converts text to speech using the Gemini TTS model.
    Returns a dictionary with the audio data or an error.
    """
    try:
        logging.info(f"Generating speech for text of length: {len(text)}")
        
        # The 'text-to-speech' model automatically routes to the best available version.
        response = google_client.models.generate_content(
            model="gemini-2.5-flash-preview-tts", 
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            # Using a high-quality voice
                            voice_name='Kore', 
                        )
                    )
                ),
            )
        )

        if not response.candidates or not response.candidates[0].content.parts:
            raise ValueError("API returned no audio data.")

        # audio_data = response.candidates[0].content.parts[0].inline_data.data
        pcm_data = response.candidates[0].content.parts[0].inline_data.data
        # 1. Create a WAV file in memory from the raw PCM data
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(1)       # Mono
            wf.setsampwidth(2)       # 16-bit
            wf.setframerate(24000)   # 24kHz sample rate (Gemini TTS default)
            wf.writeframes(pcm_data)
        wav_buffer.seek(0) # Rewind the buffer to the beginning

        # 2. Load the in-memory WAV file using pydub
        audio_segment = AudioSegment.from_wav(wav_buffer)
        
        # 3. Export it as an MP3 to another in-memory buffer
        mp3_buffer = io.BytesIO()
        audio_segment.export(mp3_buffer, format="mp3")
        mp3_buffer.seek(0) # Rewind the buffer

        # 4. Get the final MP3 data as bytes
        mp3_data = mp3_buffer.getvalue()

        logging.info(f"Successfully converted TTS output to MP3. Size: {len(mp3_data)} bytes.")

        # It's good practice to also get usage metadata if available, though TTS might not provide it
        usage = response.usage_metadata if hasattr(response, 'usage_metadata') else None
        total_token_count = 0
        if usage:
            total_token_count = getattr(usage, 'total_token_count', 0) or 0
            prompt_token_count = getattr(usage, 'prompt_token_count', 0) or 0
            candidates_token_count = getattr(usage, 'candidates_token_count', 0) or 0
            logging.info(f"TTS Usage - Prompt tokens: {prompt_token_count}, Candidate tokens: {candidates_token_count}, Total tokens: {total_token_count}")

        return {
            "audio_data": mp3_data,
            "total_token_count": total_token_count, # For potential future cost calculation
            "error": None
        }
    except Exception as e:
        logging.error(f"Error during Gemini speech generation or conversion: {e}", exc_info=True)
        return {"audio_data": None, "error": str(e)}