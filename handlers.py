# handlers.py
import logging
import os
import traceback
import html
import json
import asyncio
import jdatetime
import pytz
import math

from functools import wraps
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

import config
from prompts import (
    TRANSCRIBER_PROMPT, 
    ACTIONS_PROMPT_MAPPING, 
    ACTIONS_MAX_TOKENS_MAPPING,
    TRANSCRIBER_SRT_PROMPT
)


ytt_api = YouTubeTranscriptApi()

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Import from our modules
import config
from ai_services import (
    count_text_tokens,
    process_text_with_gemini,
    transcribe_audio_google_sync,
    generate_speech_gemini
)
from database import SessionLocal, User, ActivityLog
from texts import Texts
from utils import (
    convert_md_to_html, deliver_transcription_result, 
    log_activity, check_user_status,
    get_action_keyboard, ensure_telethon_client,
    create_word_document, extract_text_from_docx,
    preprocess_audio_sync, deliver_srt_file,
    correct_srt_format
)

admin_user_id = config.ADMIN_USER_ID

async def privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /privacy command."""
    user = update.effective_user
    await update.message.reply_text(
        text=Texts.User.PRIVACY.format(first_name=user.first_name),
        parse_mode=ParseMode.MARKDOWN, 
        disable_web_page_preview=True
    )    

@check_user_status
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command for approved users."""
    user = update.effective_user
    await update.message.reply_text(
        Texts.User.START_APPROVED.format(first_name=user.first_name)
    )
    
@check_user_status
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles direct text messages from approved users."""
    if update.message.text:  #
        text = update.message.text
    elif update.message.document:  
        text = await extract_text_from_docx(update, context)
        if text is None:
            return  #
    else:
        await update.message.reply_text("Unsupported message type.")
        return
        
    logging.info(f"Received text input from user {update.effective_user.id}. Length: {len(text)} chars.")
    context.user_data['last_text'] = text

    loop = asyncio.get_event_loop()
    input_text_tokens = await loop.run_in_executor(
        config.TOKEN_COUNTING_EXECUTOR,
        count_text_tokens,
        text,
        "gemini-2.0-flash-lite"
    )    
    action1_estimated_minutes = (input_text_tokens + 500) / config.TEXT_TOKENS_TO_MINUTES_COEFF
    action2_estimated_minutes = (input_text_tokens + 2000) / config.TEXT_TOKENS_TO_MINUTES_COEFF
    action3_estimated_minutes = (input_text_tokens + 1000) / config.TEXT_TOKENS_TO_MINUTES_COEFF
    TTS_estimated_minutes = (input_text_tokens * 8 / config.TEXT_TOKENS_TO_MINUTES_COEFF) * 4

    await update.message.reply_text(
        Texts.User.TEXT_RECEIVED,        
        reply_markup=get_action_keyboard(
            action1_estimated_minutes,
            action2_estimated_minutes,
            action3_estimated_minutes,
            TTS_estimated_minutes
            
        )        
    )


@check_user_status
async def handle_text_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text file uploads from approved users."""
    document = update.message.document
    if not document.mime_type.startswith('text/'):
        await update.message.reply_text(Texts.Errors.INVALID_TEXT_FILE)
        return

    status_message = await update.message.reply_text(Texts.User.MEDIA_DOWNLOAD_START)
    try:
        file = await context.bot.get_file(document.file_id)
        file_path = f"downloads/text_{document.file_unique_id}.txt"
        os.makedirs("downloads", exist_ok=True)
        await file.download_to_drive(file_path)

        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()

        os.remove(file_path)
        context.user_data['last_text'] = text

        loop = asyncio.get_event_loop()
        input_text_tokens = await loop.run_in_executor(
            config.TOKEN_COUNTING_EXECUTOR,
            count_text_tokens,
            text,
            "gemini-2.0-flash-lite"
        )    
        action1_estimated_minutes = (input_text_tokens + 500) / config.TEXT_TOKENS_TO_MINUTES_COEFF
        action2_estimated_minutes = (input_text_tokens + 2000) / config.TEXT_TOKENS_TO_MINUTES_COEFF
        action3_estimated_minutes = (input_text_tokens + 1000) / config.TEXT_TOKENS_TO_MINUTES_COEFF
        TTS_estimated_minutes = (input_text_tokens * 8 / config.TEXT_TOKENS_TO_MINUTES_COEFF) * 4

        await status_message.edit_text(
            Texts.User.TEXT_FILE_PROMPT,
            reply_markup=get_action_keyboard(
                action1_estimated_minutes,
                action2_estimated_minutes,
                action3_estimated_minutes,
                TTS_estimated_minutes
            )              
        )
    except Exception as e:
        logging.error(f"Failed to process text file: {e}", exc_info=True)
        await status_message.edit_text(Texts.Errors.TEXT_FILE_PROCESS_FAILED.format(error=e))


@check_user_status
async def handle_media_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles audio, checks credit, processes, and correctly deducts credit.
    """

    db_user: User = context.user_data['db_user']
    message = update.message
    file_object, original_filename = None, None
    
    if message.voice:
        file_object, original_filename = message.voice, f"{message.voice.file_unique_id}.oga"
    elif message.audio:
        file_object, original_filename = message.audio, message.audio.file_name or f"{message.audio.file_unique_id}.mp3"
    elif message.video:
        file_object, original_filename = message.video, message.video.file_name or f"{message.video.file_unique_id}.mp4"
    else:
        return
    
    if file_object.duration > config.MAX_AUDIO_DURATION_SECONDS:
        await message.reply_text(Texts.Errors.VIDEO_TOO_LONG)
        return
        
    duration_seconds = file_object.duration
    cost_minutes = duration_seconds / 60.0
    duration_minutes = duration_seconds / 60.0 

    if cost_minutes > db_user.credit_minutes:
        await message.reply_text(
            Texts.User.CREDIT_INSUFFICIENT.format(
                current_credit=db_user.credit_minutes,
                cost=cost_minutes
            )
        )
        return

    duration_str = f"{duration_seconds // 60:02d}:{ duration_seconds % 60:02d}"
    status_message = await message.reply_text(
        Texts.User.MEDIA_PROCESSING_MSG.format(
            duration = duration_str,
            download = "آغاز شد...",
            process = "...",
            transcription = "..."
        )
    )

    downloads_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    original_extension = os.path.splitext(original_filename)[1] or '.tmp'
    local_file_path = os.path.join(downloads_dir, f"downloaded_{file_object.file_unique_id}{original_extension}")    
    processed_audio_path = f"downloads/converted_{file_object.file_unique_id}.mp3"

    try:
        logging.info(f"Downloading Audio file. Size: {file_object.file_size} bytes.")

        if file_object.file_size > config.TELEGRAM_MAX_BOT_API_FILE_SIZE:
            logging.info("File is larger than 20MB, using Telethon for download.")
            client = await ensure_telethon_client()
            logging.info(f"Starting download using file_id: {file_object.file_id}")

            telethon_message = await client.get_messages(entity=message.chat_id, ids=message.message_id)
            if not telethon_message or not (telethon_message.audio or telethon_message.voice or telethon_message.video or telethon_message.document):
                raise ValueError("Could not find media in message via Telethon.")
            await client.download_media(telethon_message, file=local_file_path)
        else:
            logging.info("File is smaller than 20MB, using Bot API for download.")
            bot_file = await context.bot.get_file(file_object.file_id)
            await bot_file.download_to_drive(local_file_path)

        await status_message.edit_text(Texts.User.MEDIA_PROCESSING_MSG.format(
                duration = duration_str,
                download = "✅",
                process = "آغاز شد...",
                transcription = "..."
            ))                        

        loop = asyncio.get_event_loop()
        success, error_msg, original_length_ms = await loop.run_in_executor(
            config.AUDIO_PROCESS_EXECUTOR,
            preprocess_audio_sync,
            local_file_path,
            processed_audio_path
        )
        if not success:
            await status_message.edit_text(Texts.User.MEDIA_PROCESSING_MSG.format(
                    duration = duration_str,
                    download = "✅",
                    process = f"خطا در آماده‌سازی فایل: {error_msg}",
                    transcription = "..."
                ))              
            if os.path.exists(local_file_path):
                os.remove(local_file_path)
            if os.path.exists(processed_audio_path):
                os.remove(processed_audio_path)
            return

        if original_length_ms:
            refined_duration_seconds = original_length_ms / 1000
            duration_str = f"{original_length_ms // 60000:02d}:{(original_length_ms // 1000) % 60:02d}"
            cost_minutes = refined_duration_seconds / 60.0  

        await status_message.edit_text(Texts.User.MEDIA_PROCESSING_MSG.format(
                duration = duration_str,
                download = "✅",
                process = "✅",
                transcription = "آغاز شد..."
            ))  
        full_transcript = ""
        loop = asyncio.get_event_loop()

        if duration_minutes > config.MAX_CHUNK_LEN:
            # Chunking mode
            processed_audio = await loop.run_in_executor(
                config.AUDIO_PROCESS_EXECUTOR,
                AudioSegment.from_file,
                processed_audio_path
            )

            chunk_length_ms = config.CHUNK_SIZE * 60 * 1000
            total_length_ms = len(processed_audio)
            num_chunks = math.ceil(total_length_ms / chunk_length_ms)
            logging.info(f"duration_minutes: {duration_minutes} (MAX_CHUNK_LEN: {config.MAX_CHUNK_LEN}), We need to chunk file, num_chunks: {num_chunks}")
            
            for i in range(num_chunks):
                progress = int(100 * (i+1) / num_chunks)
                logging.info(f"Prcessing chunk: {i+1} from {num_chunks}, progress: {progress}")

                await status_message.edit_text(Texts.User.MEDIA_PROCESSING_MSG.format(
                        duration = duration_str,
                        download = "✅",
                        process = "✅",
                        transcription = str(progress) + " %"
                    ))
                
                start_ms = i * chunk_length_ms
                end_ms = min(start_ms + chunk_length_ms, total_length_ms)
                chunk = processed_audio[start_ms:end_ms] 
                chunk_path = os.path.join(downloads_dir, f"temp_chunk_{file_object.file_unique_id}_{i+1}.mp3")
                chunk.export(chunk_path, format="mp3", bitrate="32k")
                
                chunk_duration = int(duration_seconds / num_chunks)
                transcription_result_dict = await loop.run_in_executor(
                    config.TRANSCRIPTION_EXECUTOR,
                    transcribe_audio_google_sync,
                    chunk_path,
                    chunk_duration,
                    "gemini-2.5-flash",
                    TRANSCRIBER_PROMPT,
                )
                
                if transcription_result_dict.get("error"):
                    await status_message.edit_text(Texts.User.MEDIA_PROCESSING_MSG.format(
                            duration = duration_str,
                            download = "✅",
                            process = "✅",
                            transcription = Texts.Errors.AUDIO_TRANSCRIPTION_FAILED.format(error=transcription_result_dict['error'])
                        ))                    
                    return

                chunk_transcript = transcription_result_dict.get("transcription", "")
                full_transcript += chunk_transcript + " "
                os.remove(chunk_path)

            os.remove(processed_audio_path)
        else:
            # No chunking: Transcribe the single file
            logging.info(f"duration_minutes: {duration_minutes} (MAX_CHUNK_LEN: {config.MAX_CHUNK_LEN}), No chunking is needed.")
            await status_message.edit_text(Texts.User.MEDIA_PROCESSING_MSG.format(
                    duration = duration_str,
                    download = "✅",
                    process = "✅",
                    transcription="در حال شروع..."
                ))              
            transcription_result_dict = await loop.run_in_executor(
                config.TRANSCRIPTION_EXECUTOR,
                transcribe_audio_google_sync,
                processed_audio_path,
                duration_seconds,
                "gemini-2.5-flash",
                TRANSCRIBER_PROMPT,
            )
            
            if transcription_result_dict.get("error"):
                await status_message.edit_text(Texts.User.MEDIA_PROCESSING_MSG.format(
                        duration = duration_str,
                        download = "✅",
                        process = "✅",
                        transcription = Texts.Errors.AUDIO_TRANSCRIPTION_FAILED.format(error=transcription_result_dict['error'])
                    ))                  
                return
            
            full_transcript = transcription_result_dict.get("transcription", "")
            
            # Cleanup
            os.remove(processed_audio_path)
        
        raw_transcript = full_transcript.strip()
        language = db_user.preferred_language
        logging.info(f"Transcription successful. Length: {len(raw_transcript)} chars")

        await status_message.edit_text(Texts.User.MEDIA_PROCESSING_MSG.format(
                duration = duration_str,
                download = "✅",
                process = "✅",
                transcription = "✅"
            ))   
        
        # Credit Deduction & Logging
        db = SessionLocal()
        try:
            user_to_update = db.query(User).filter(User.user_id == db_user.user_id).first()
            if user_to_update:
                user_to_update.credit_minutes -= cost_minutes
                db.commit()
                log_activity(
                    db=db,
                    user_id=user_to_update.user_id,
                    action='transcription',
                    credit_change=-cost_minutes,
                    details=f"Media duration: {duration_seconds:.2f}s, File: {original_filename}"
                )
                db.refresh(user_to_update)
                logging.info(f"Deducted {cost_minutes:.2f} minutes from user {db_user.user_id}. New balance: {user_to_update.credit_minutes:.2f}")
                context.user_data['db_user'] = user_to_update
            else:
                logging.error(f"Could not find user {db_user.user_id} to deduct credit.")
        finally:
            db.close()

        source_info = {
            'type': 'media',
            'cost': cost_minutes,
            'language':language
        }
        await deliver_transcription_result(update, context, raw_transcript, source_info)
        
    except CouldntDecodeError:
        logging.error(f"Pydub/FFmpeg could not decode the file: {local_file_path}", exc_info=True)
        await status_message.edit_text("خطا: فایل ارسال شده فرمت ناشناخته یا خرابی دارد و قابل پردازش نیست.")
    except Exception as e:
        logging.error(f"An error occurred in handle_media_file: {e}", exc_info=True)
        error_msg = str(e)
        if "Message is too long" in error_msg:
            error_msg = Texts.Errors.OUTPUT_TOO_LONG
        await status_message.edit_text(Texts.Errors.GENERIC_UNEXPECTED.format(error=error_msg))        
    finally:
        for file_path in [local_file_path, processed_audio_path]:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logging.info(f"Cleaned up: {file_path}")
                except Exception as cleanup_error:
                    logging.warning(f"Failed to delete {file_path}: {cleanup_error}")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Parses the CallbackQuery, executes the action, and sends the result
    as a direct message if short, or as a file if long.
    """
    query = update.callback_query
    await query.answer()

    button_text = ""
    if query.message.reply_markup:
        for row in query.message.reply_markup.inline_keyboard:
            for button in row:
                if button.callback_data == query.data:
                    button_text = button.text
                    break
    
    processing_message = await query.message.reply_text(
        Texts.User.PROCESSING_ACTION.format(action_text=button_text)
    )

    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.user_id == query.from_user.id).first()
        if not db_user or db_user.status != 'approved':
            await processing_message.edit_text("Error: You are not authorized for this action.")
            return

        text_to_process = context.user_data.get('last_text')
        if not text_to_process:
            await processing_message.edit_text(text=Texts.Errors.TEXT_NOT_FOUND)
            return

        action = query.data
        logging.info(f"User {db_user.user_id} selected action: {action} ({button_text}), Text length: {len(text_to_process)} chars")

        # --- TTS LOGIC ---
        if action == 'text_to_speech':
            # 1. Calculate cost based on the input text
            loop = asyncio.get_event_loop()
            input_tokens = await loop.run_in_executor(
                config.TOKEN_COUNTING_EXECUTOR,
                count_text_tokens,
                text_to_process,
                "gemini-2.0-flash-lite"
            )
            # Cost is based on action3's formula, multiplied by 4
            cost_minutes_est = (input_tokens * 8 / config.TEXT_TOKENS_TO_MINUTES_COEFF) * 4
            
            logging.info(f"TTS Action: Input tokens: {input_tokens}, Estimated cost: {cost_minutes_est:.2f} minutes")

            if cost_minutes_est > db_user.credit_minutes:
                await processing_message.edit_text(
                    Texts.User.CREDIT_INSUFFICIENT.format(current_credit=db_user.credit_minutes, cost=cost_minutes_est)
                )
                return

            result_dict = await loop.run_in_executor(
                config.TEXT_PROCESS_EXECUTOR,
                generate_speech_gemini,
                text_to_process
            )

            if result_dict.get("error"):
                await processing_message.edit_text(f"خطا در تبدیل متن به صوت: {result_dict['error']}")
                return

            total_tokens_consumed = result_dict.get("total_token_count", 0)
            final_cost_minutes = 4 * total_tokens_consumed / config.TEXT_TOKENS_TO_MINUTES_COEFF

            # 4. Deduct credit and log
            db_user.credit_minutes -= final_cost_minutes
            db.commit()
            log_activity(db=db, user_id=db_user.user_id, action=action, credit_change=-final_cost_minutes, details=f"TTS for {len(text_to_process)} chars")
            logging.info(f"TTS complete. Deducted {final_cost_minutes:.2f} minutes. New balance: {db_user.credit_minutes:.2f}")

            # 5. Send the audio file to the user
            audio_data = result_dict.get("audio_data")
            caption_text = (
                f"🔊 فایل صوتی شما آماده است.\n\n"
                f"هزینه عملیات: {final_cost_minutes:.1f} دقیقه\n"
                f"<b>اعتبار باقی‌مانده: {db_user.credit_minutes:.1f} دقیقه</b>\n"
                "@SedaNevis_bot"
            )
            
            await query.message.reply_voice(
                voice=audio_data,
                caption=caption_text,
                parse_mode=ParseMode.HTML
            )
            
            await processing_message.delete()
            return
        

        prompt_template = ACTIONS_PROMPT_MAPPING.get(action)
        if not prompt_template:
            await processing_message.edit_text(text=Texts.Errors.ACTION_UNDEFINED.format(action=action))
            return
        
        full_prompt = prompt_template.format(text=text_to_process)
        max_tokens = ACTIONS_MAX_TOKENS_MAPPING.get(action)

        loop = asyncio.get_event_loop()
        estimated_input_tokens = await loop.run_in_executor(
            config.TOKEN_COUNTING_EXECUTOR,
            count_text_tokens,
            full_prompt,
            "gemini-2.0-flash-lite"
        )   

        estimated_tokens = estimated_input_tokens + max_tokens
        cost_minutes =  estimated_tokens / config.TEXT_TOKENS_TO_MINUTES_COEFF
        
        logging.info(f"for Action-{action}, with max_tokens = {max_tokens}, estimated_tokens = {estimated_tokens}, cost_minutes = {cost_minutes} min")

        if cost_minutes > db_user.credit_minutes:
            await processing_message.edit_text(
                Texts.User.CREDIT_INSUFFICIENT.format(current_credit=db_user.credit_minutes, cost=cost_minutes)
            )
            return

        loop = asyncio.get_event_loop()
        result_dict = await loop.run_in_executor(
            config.TEXT_PROCESS_EXECUTOR,
            process_text_with_gemini,
            full_prompt,
            "gemini-2.5-flash-lite",
            max_tokens
        )
        
        if result_dict.get("error"):
            await processing_message.edit_text(Texts.Errors.TEXT_PROCESS_FAILED.format(error=result_dict['error']))
            return

        total_tokens_consumed = result_dict.get("total_token_count", 0)
        input_tc = result_dict.get("prompt_token_count", 0)
        output_tc = result_dict.get("candidates_token_count", 0)
        logging.info(f"Action-{action} done, for {db_user.user_id},Tokens Input: {input_tc}, Output: {output_tc}, Total: {total_tokens_consumed}")
                    
        final_cost_minutes = total_tokens_consumed / config.TEXT_TOKENS_TO_MINUTES_COEFF
        db_user.credit_minutes -= final_cost_minutes
        db.commit()
        log_activity(db=db, user_id=db_user.user_id, action=action, credit_change=-final_cost_minutes, details=f"Tokens consumed: {total_tokens_consumed}")
        user_lang = db_user.preferred_language
        logging.info(f"user_lang: {user_lang}, Total tokens consumed for text process: {total_tokens_consumed}, Deducted {final_cost_minutes:.4f} minutes from user {db_user.user_id}. New balance: {db_user.credit_minutes:.2f}")

        result_text_md = result_dict.get("text", Texts.User.NO_RESPONSE_FROM_AI)
        formatted_result_html = convert_md_to_html(result_text_md, user_lang)
        header = Texts.User.ACTION_RESULT_HEADER.format(action_text=button_text)
        footer = Texts.User.ACTION_RESULT_FOOTER.format(
            cost=final_cost_minutes,
            remaining_credit=db_user.credit_minutes
        )

        
        full_message = f"{header}\n\n{formatted_result_html}{footer}"

        await processing_message.delete() 

        if len(full_message) <= 4096:
            await query.message.reply_text(full_message, parse_mode=ParseMode.HTML)
        else:

            try:
                document_buffer = create_word_document(formatted_result_html, user_lang )
                file_caption = f"{header}\n\n{Texts.User.ACTION_RESULT_LONG_FILE_CAPTION}{footer}"
                tehran_tz = pytz.timezone('Asia/Tehran')
                current_report_time = jdatetime.datetime.now(tehran_tz).strftime("%Y%m%d-%H%M%S")
                report_filename = f"Report_{action}_{current_report_time}.docx"

                await query.message.reply_document(
                    document=document_buffer,
                    filename=report_filename,
                    caption=file_caption,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logging.error(f"Failed to create or send Word file: {e}", exc_info=True)
                await query.message.reply_text(Texts.Errors.GENERIC_UNEXPECTED_ADMIN.format(error=e))

    except Exception as e:
        if 'processing_message' in locals() and processing_message:
            await processing_message.delete()
        logging.error(f"Error in button_callback_handler: {e}", exc_info=True)
        await query.message.reply_text(Texts.Errors.GENERIC_UNEXPECTED_ADMIN.format(error=e))
    finally:
        db.close()

@check_user_status
async def handle_video_file(update, context):
    message = update.message

    db_user: User = context.user_data['db_user']
    message = update.message
    file_object, user_file_name = None, None
    

    if message.video:
        file_object, user_file_name = message.video, message.video.file_name or f"{message.video.file_unique_id}.mp4"
    else:
        return
    
    if file_object.duration > config.MAX_AUDIO_DURATION_SECONDS:
        await message.reply_text(Texts.Errors.VIDEO_TOO_LONG)
        return
    
    # file_object = message.video
    # user_file_name = file_object.file_name or f"video_{file_object.file_unique_id}.mp4"
    duration_seconds = file_object.duration
    cost_minutes = duration_seconds / 60.0
    if cost_minutes > context.user_data['db_user'].credit_minutes:
        await message.reply_text(Texts.User.CREDIT_INSUFFICIENT.format(
            current_credit=context.user_data['db_user'].credit_minutes,
            cost=cost_minutes
        ))
        return

    unique_key = file_object.file_unique_id
    context.user_data[unique_key] = {
        'file_id': file_object.file_id,
        'file_size': file_object.file_size,
        'user_file_name': user_file_name,
        'duration_seconds': duration_seconds,
        'original_message_id': message.message_id 
    }

    keyboard = [
        [InlineKeyboardButton("دریافت رونویسی خام", callback_data=f"video_raw:{unique_key}")],
        [InlineKeyboardButton("دریافت زیرنویس (srt)", callback_data=f"video_srt:{unique_key}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("نوع خروجی را انتخاب کنید:", reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def handle_video_callback(update, context):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(":")
    action = data[0]
    unique_key = data[1]
    file_data = context.user_data.get(unique_key)
    if not file_data:
        await query.edit_message_text("درخواست منقضی شده است.")
        return

    file_id = file_data['file_id']
    file_size = file_data['file_size']
    user_file_name = file_data['user_file_name']
    duration_seconds = file_data['duration_seconds']
    original_message_id = file_data['original_message_id'] 

    cost_minutes = int(duration_seconds / 60.0 )
    db_user = context.user_data['db_user']
   
    duration_str = f"{duration_seconds // 60:02d}:{ duration_seconds % 60:02d}"

    status_message = await query.edit_message_text(
        Texts.User.MEDIA_PROCESSING_MSG.format(
            duration = duration_str,
            download = "شروع شد...",
            process = "...",
            transcription = "..."
        )
    )

    downloads_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(downloads_dir, exist_ok=True)
    
    local_file_path = os.path.join(downloads_dir, f"video_{file_id}.mp4")
    processed_audio_path = os.path.join(downloads_dir, f"processed_{file_id}.mp3")
    
    try:       
        logging.info(f"Downloading Video file. Size: {file_size} bytes.")

        if file_size > config.TELEGRAM_MAX_BOT_API_FILE_SIZE:
            logging.info("Video file is larger than 20MB, using Telethon for download.")
            client = await ensure_telethon_client()
            logging.info(f"Starting download using file_id: {file_id}")
            
            # telethon_message = await client.get_messages(entity=update.effective_chat.id, ids=query.message.message_id)
            telethon_message = await client.get_messages(entity=query.message.chat_id, ids=original_message_id)
            
            if not telethon_message or not (telethon_message.audio or telethon_message.voice or telethon_message.video or telethon_message.document):
                logging.error(f"Telethon could not find media: chat={query.message.chat_id}, msg_id={original_message_id}")
                raise ValueError("Could not find media in message via Telethon.")
            await client.download_media(telethon_message, file=local_file_path)
        else:
            logging.info("Video file is smaller than 20MB, using Bot API for download.")
            bot_file = await context.bot.get_file(file_id)
            await bot_file.download_to_drive(local_file_path) 

        await status_message.edit_text(
            Texts.User.MEDIA_PROCESSING_MSG.format(
                duration = duration_str,
                download = "✅",
                process = "شروع شد...",
                transcription = "..."
            )
        )
        loop = asyncio.get_event_loop()
        success, error_msg, original_length_ms = await loop.run_in_executor(
            config.AUDIO_PROCESS_EXECUTOR, 
            preprocess_audio_sync, 
            local_file_path, 
            processed_audio_path
        )

        if not success:
            # await status_message.edit_text(f"خطا در پردازش ویدیو: {error_msg}")
            await status_message.edit_text(
                Texts.User.MEDIA_PROCESSING_MSG.format(
                    duration = duration_str,
                    download = "✅",
                    process = f"خطا در آماده‌سازی فایل: {error_msg}",
                    transcription = "..."
                )
            )            
            if os.path.exists(local_file_path):
                os.remove(local_file_path)
            if os.path.exists(processed_audio_path):
                os.remove(processed_audio_path)            
            return
        
        if original_length_ms:
            refined_duration_seconds = original_length_ms / 1000
            duration_str = f"{original_length_ms // 60000:02d}:{(original_length_ms // 1000) % 60:02d}"
            cost_minutes = refined_duration_seconds / 60.0  # Update cost for precision

        # await status_message.edit_text(f"ویدیو پردازش شد (طول: {duration_str}). در حال رونویسی...")
        await status_message.edit_text(
            Texts.User.MEDIA_PROCESSING_MSG.format(
                duration = duration_str,
                download = "✅",
                process = "✅",
                transcription = "شروع شد...",
            )
        )  

        full_transcript = ""
        duration_minutes = duration_seconds / 60.0
        
        if duration_minutes > config.MAX_CHUNK_LEN:
            processed_audio = AudioSegment.from_file(processed_audio_path)
            chunk_length_ms = config.CHUNK_SIZE * 60 * 1000
            total_length_ms = len(processed_audio)
            num_chunks = math.ceil(total_length_ms / chunk_length_ms)
            
            for i in range(num_chunks):
                progress = int(100 * (i+1) / num_chunks)
                logging.info(f"Prcessing chunk: {i+1} from {num_chunks}, progress: {progress}")
                await status_message.edit_text(Texts.User.MEDIA_PROCESSING_MSG.format(
                        duration = duration_str,
                        download = "✅",
                        process = "✅",
                        transcription = str(progress) + " %"
                    ))
                                                
                start_ms = i * chunk_length_ms
                end_ms = min(start_ms + chunk_length_ms, total_length_ms)
                chunk = processed_audio[start_ms:end_ms]
                chunk_path = f"downloads/temp_chunk_{file_id}_{i+1}.mp3"
                chunk.export(chunk_path, format="mp3", bitrate="32k")
                
                prompt = TRANSCRIBER_SRT_PROMPT if action == "video_srt" else TRANSCRIBER_PROMPT
                chunk_duration = int(duration_seconds / num_chunks)
                transcription_result_dict = await loop.run_in_executor(
                    config.TRANSCRIPTION_EXECUTOR, 
                    transcribe_audio_google_sync, 
                    chunk_path, 
                    chunk_duration, 
                    "gemini-2.5-flash", 
                    prompt
                )
                
                if transcription_result_dict.get("error"):
                    # await status_message.edit_text(f"خطا در رونویسی: {transcription_result_dict['error']}")
                    await status_message.edit_text(Texts.User.MEDIA_PROCESSING_MSG.format(
                            duration = duration_str,
                            download = "✅",
                            process = "✅",
                            transcription = Texts.Errors.AUDIO_TRANSCRIPTION_FAILED.format(error=transcription_result_dict['error'])
                        ))                      
                    return
                
                full_transcript += transcription_result_dict.get("transcription", "") + " "
                os.remove(chunk_path)
            
            os.remove(processed_audio_path)
        else:
            prompt = TRANSCRIBER_SRT_PROMPT if action == "video_srt" else TRANSCRIBER_PROMPT
            await status_message.edit_text(Texts.User.MEDIA_PROCESSING_MSG.format(
                    duration = duration_str,
                    download = "✅",
                    process = "✅",
                    transcription="در حال شروع..."
                ))  
            transcription_result_dict = await loop.run_in_executor(
                config.TRANSCRIPTION_EXECUTOR, 
                transcribe_audio_google_sync, 
                processed_audio_path, 
                duration_seconds, 
                "gemini-2.5-flash", 
                prompt
            )
            
            if transcription_result_dict.get("error"):
                # await status_message.edit_text(f"خطا در رونویسی: {transcription_result_dict['error']}")
                # return
                await status_message.edit_text(Texts.User.MEDIA_PROCESSING_MSG.format(
                        duration = duration_str,
                        download = "✅",
                        process = "✅",
                        transcription = Texts.Errors.AUDIO_TRANSCRIPTION_FAILED.format(error=transcription_result_dict['error'])
                    ))                  
                return
                        
            full_transcript = transcription_result_dict.get("transcription", "")
            os.remove(processed_audio_path)
        
        os.remove(local_file_path)

        await status_message.edit_text(Texts.User.MEDIA_PROCESSING_MSG.format(
                duration = duration_str,
                download = "✅",
                process = "✅",
                transcription = "✅"
            ))   
                
        if action == "video_srt":
            # full_transcript = correct_srt_format(full_transcript)
            await deliver_srt_file(update, context, full_transcript, user_file_name, cost_minutes)
        else:
            source_info = {'type': 'video_raw', 'cost': cost_minutes, 'language': db_user.preferred_language}
            await deliver_transcription_result(update, context, full_transcript, source_info)
        
        db = SessionLocal()
        user_to_update = db.query(User).filter(User.user_id == db_user.user_id).first()
        if user_to_update:
            user_to_update.credit_minutes -= cost_minutes
            db.commit()
        db.close()
        
    except Exception as e:
        await status_message.edit_text(f"خطا: {str(e)}")
    finally:
        for f in [local_file_path, processed_audio_path]:
            if os.path.exists(f):
                os.remove(f)


async def approval_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'approve' and 'reject' callbacks from the admin."""
    query = update.callback_query
    await query.answer()

    admin_user = update.effective_user
    if admin_user.id != config.ADMIN_USER_ID:
        logging.warning(f"Non-admin user {admin_user.id} tried to use an approval callback.")
        return

    try:
        action, target_user_id_str = query.data.split(':')
        target_user_id = int(target_user_id_str)
    except (ValueError, IndexError):
        await query.edit_message_text("Error: Invalid callback data.")
        return

    db = SessionLocal()
    try:
        target_user = db.query(User).filter(User.user_id == target_user_id).first()
        if not target_user:
            await query.edit_message_text(Texts.Errors.USER_NOT_FOUND_IN_DB_ADMIN.format(user_id=target_user_id))            
            return

        safe_first_name = html.escape(target_user.first_name)

        if action == 'approve':
            target_user.status = 'approved'
            target_user.credit_minutes = config.DEFAULT_CREDIT_MINUTES           
            db.commit()

            log_activity(
                db=db,
                user_id=target_user_id,
                action='admin_approval',
                credit_change=config.DEFAULT_CREDIT_MINUTES,
                details=f"Approved by admin {admin_user.id}"
            )            
            await query.edit_message_text(
                Texts.Admin.USER_APPROVED_NOTIFICATION.format(
                    first_name=safe_first_name,
                    user_id=target_user.user_id,
                    credit=config.DEFAULT_CREDIT_MINUTES                  
                ),
                parse_mode=ParseMode.HTML
            )            
            await context.bot.send_message(
                chat_id=target_user_id,
                text=Texts.User.APPROVAL_SUCCESS
            )            
        elif action == 'reject':
            target_user.status = 'rejected'
            db.commit()
            log_activity(
                db=db, user_id=target_user_id, action='admin_rejection',
                credit_change=0, details=f"Rejected by admin {admin_user.id}"
            )            
            await query.edit_message_text(
                Texts.Admin.USER_REJECTED_NOTIFICATION.format(
                    first_name=safe_first_name, 
                    user_id=target_user.user_id
                ),
                parse_mode=ParseMode.HTML
            )
            await context.bot.send_message(
                chat_id=target_user_id,
                text=Texts.User.APPROVAL_REJECTED
            )            
    except Exception as e:
        logging.error(f"Error in approval_callback_handler: {e}", exc_info=True)
        try:
            await query.edit_message_text(Texts.Errors.GENERIC_UNEXPECTED_ADMIN.format(error=e))            
        except:
            pass 
    finally:
        db.close()


@check_user_status
async def credit_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /credit command, showing the user their remaining credits.
    """
    db_user: User = context.user_data['db_user']
    
    reply_text = Texts.User.CREDIT_STATUS.format(credit=db_user.credit_minutes)   
    await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)


@check_user_status
async def settings_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /settings command, allowing users to change their language.
    """
    db_user: User = context.user_data['db_user']
    
    current_lang = Texts.User.LANG_FA_NAME if db_user.preferred_language == 'fa' else Texts.User.LANG_EN_NAME
    reply_text = Texts.User.SETTINGS_PROMPT.format(current_lang=current_lang)
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            ("✅ " if db_user.preferred_language == 'fa' else "") + Texts.Keyboard.LANG_FA,
            callback_data='set_lang:fa'
        ),
        InlineKeyboardButton(
            ("✅ " if db_user.preferred_language == 'en' else "") + Texts.Keyboard.LANG_EN,
            callback_data='set_lang:en'
        )
    ]])
    
    await update.message.reply_text(reply_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def set_language_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the callback from the /settings language buttons.
    """
    query = update.callback_query
    await query.answer()
    
    try:
        action, lang_code = query.data.split(':')
    except (ValueError, IndexError):
        await query.edit_message_text("Error: Invalid language callback.")
        return

    db = SessionLocal()
    try:
        user_to_update = db.query(User).filter(User.user_id == query.from_user.id).first()
        if not user_to_update:
            await query.edit_message_text(Texts.Errors.USER_PROFILE_NOT_FOUND)
            return

        if user_to_update.preferred_language == lang_code:
            # The language is already set, just give a confirmation
            await query.edit_message_text(query.message.text, reply_markup=query.message.reply_markup)
            return
            
        user_to_update.preferred_language = lang_code
        db.commit()
        db.refresh(user_to_update)
        
        logging.info(f"User {user_to_update.user_id} changed language to '{lang_code}'.")

        # Re-create the message and keyboard with updated info
        current_lang = Texts.User.LANG_FA_NAME if user_to_update.preferred_language == 'fa' else Texts.User.LANG_EN_NAME
        reply_text = Texts.User.LANG_UPDATED_SUCCESS.format(new_lang=current_lang)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                ("✅ " if user_to_update.preferred_language == 'fa' else "") + Texts.Keyboard.LANG_FA,
                callback_data='set_lang:fa'
            ),
            InlineKeyboardButton(
                ("✅ " if user_to_update.preferred_language == 'en' else "") + Texts.Keyboard.LANG_EN,
                callback_data='set_lang:en'
            )
        ]])
        
        await query.edit_message_text(reply_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    finally:
        db.close()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:

    logging.error("Exception while handling an update:", exc_info=context.error)

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"{Texts.Errors.EXCEPTION_REPORT_HEADER}\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )
    limit = 4096
    chunks = [message[i:i + limit] for i in range(0, len(message), limit)]

    for chunk in chunks:
        await context.bot.send_message(
            chat_id=admin_user_id, text=chunk, parse_mode=ParseMode.HTML
        )

def admin_only(func):
    """
    A decorator to restrict access to a handler to the admin only.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or user.id != config.ADMIN_USER_ID:
            logging.warning(f"Unauthorized access attempt to an admin command by user {user.id if user else 'Unknown'}.")
            if update.message:
                await update.message.reply_text(Texts.Admin.ONLY_ADMIN_COMMAND)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@admin_only
async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays all available admin commands."""
    await update.message.reply_text(Texts.Admin.HELP_TEXT, parse_mode=ParseMode.HTML)


@admin_only
async def list_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all users in the database."""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        if not users:
            await update.message.reply_text("No users found in the database.")
            return
            
        message_parts = ["<b>👥 User List</b>\n\n"]
        for user in users:
            user_line = Texts.Admin.LIST_USERS_ITEM.format(
                first_name=html.escape(user.first_name),
                user_id=user.user_id,
                status=user.status,
                credit=user.credit_minutes
            )            
            message_parts.append(user_line)
            
        full_message = "".join(message_parts)

        limit = 4096
        for i in range(0, len(full_message), limit):
            chunk = full_message[i:i + limit]
            await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
            
    finally:
        db.close()

@admin_only
async def user_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gets detailed information for a specific user."""
    args = context.args
    if len(args) != 1:
        await update.message.reply_text(Texts.Errors.USAGE_USER_INFO, parse_mode=ParseMode.HTML)        
        return

    try:
        target_user_id = int(args[0])
    except ValueError:
        await update.message.reply_text(Texts.Errors.INVALID_USER_ID)        
        return
        
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == target_user_id).first()
        if not user:
            await update.message.reply_text(f"No user found with ID <code>{target_user_id}</code>.", parse_mode=ParseMode.HTML)
            return
            
        info_header = Texts.Admin.USER_INFO_HEADER.format(first_name=html.escape(user.first_name))
        info_body = Texts.Admin.USER_INFO_BODY.format( 
            user_id=user.user_id,
            username=user.username or 'N/A',
            status=user.status,
            credit=user.credit_minutes,
            lang=user.preferred_language,
            joined_date=user.created_at.strftime('%Y-%m-%d %H:%M')
        )
        await update.message.reply_text(info_header + info_body, parse_mode=ParseMode.HTML)
        
    finally:
        db.close()


@admin_only
async def add_credit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds credit to a user's account."""
    args = context.args
    if len(args) != 2:
        await update.message.reply_text(Texts.Errors.USAGE_ADD_CREDIT, parse_mode=ParseMode.HTML)
        return

    try:
        target_user_id = int(args[0])
        minutes_to_add = float(args[1])
    except ValueError:
        await update.message.reply_text("Invalid arguments. User ID, minutes, and tokens must be numbers.")
        return
        
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == target_user_id).first()
        if not user:
            await update.message.reply_text(f"No user found with ID <code>{target_user_id}</code>.", parse_mode=ParseMode.HTML)
            return
            
        user.credit_minutes += minutes_to_add 
        db.commit()

        log_activity(
            db=db,
            user_id=target_user_id,
            action='admin_add_credit',
            credit_change=minutes_to_add,
            details=f"Added by admin {update.effective_user.id}"
        )

        confirmation_text = Texts.Admin.ADD_CREDIT_SUCCESS.format( 
            first_name=html.escape(user.first_name),
            minutes_added=minutes_to_add,
            new_credit=user.credit_minutes
        )
        await update.message.reply_text(confirmation_text, parse_mode=ParseMode.HTML)
        
    finally:
        db.close()

@admin_only
async def set_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Changes a user's status."""
    args = context.args
    valid_statuses = ['approved', 'pending', 'rejected', 'banned']
    
    if len(args) != 2 or args[1] not in valid_statuses:
        await update.message.reply_text(
            "Usage: <code>/set_status <user_id> <status></code>\n"
            f"Valid statuses are: {', '.join(valid_statuses)}",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        target_user_id = int(args[0])
        new_status = args[1]
    except ValueError:
        await update.message.reply_text("Invalid User ID. It must be a number.")
        return
        
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == target_user_id).first()
        if not user:
            await update.message.reply_text(f"No user found with ID <code>{target_user_id}</code>.", parse_mode=ParseMode.HTML)
            return
            
        user.status = new_status
        db.commit()

        log_activity(
            db=db, user_id=target_user_id, action=f'admin_set_status_{new_status}',
            credit_change=0, details=f"Set by admin {update.effective_user.id}"
        )

        await update.message.reply_text(
            Texts.Admin.SET_STATUS_SUCCESS.format( # Uses updated text
                first_name=html.escape(user.first_name),
                user_id=user.user_id,
                new_status=new_status
            ),
            parse_mode=ParseMode.HTML
        )
        
    finally:
        db.close()

@admin_only
async def user_logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays recent activity logs for a specific user."""
    args = context.args
    if len(args) != 1:
        await update.message.reply_text(Texts.Errors.USAGE_USER_LOGS, parse_mode=ParseMode.HTML)
        return

    try:
        target_user_id = int(args[0])
    except ValueError:
        await update.message.reply_text(Texts.Errors.INVALID_USER_ID)
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == target_user_id).first()
        if not user:
            await update.message.reply_text(f"No user found with ID <code>{target_user_id}</code>.", parse_mode=ParseMode.HTML)
            return

        logs = db.query(ActivityLog).filter(ActivityLog.user_id == target_user_id).order_by(ActivityLog.timestamp.desc()).limit(20).all()

        if not logs:
            await update.message.reply_text(Texts.Admin.NO_LOGS_FOUND.format(user_id=target_user_id), parse_mode=ParseMode.HTML)
            return
        
        message_parts = [
            Texts.Admin.USER_LOGS_HEADER.format(
                first_name=html.escape(user.first_name), 
                user_id=user.user_id
            )
        ]
        for log in logs:
            log_line = Texts.Admin.USER_LOGS_ITEM.format(
                timestamp=log.timestamp.strftime('%Y-%m-%d %H:%M'),
                action=log.action_type,
                change=log.credit_change,
                details=html.escape(log.details or 'N/A')
            )
            message_parts.append(log_line)
            
        full_message = "".join(message_parts)
        await update.message.reply_text(full_message, parse_mode=ParseMode.HTML)
        
    finally:
        db.close()

def get_yt_video_id(url: str) -> str | None:
    """
    Extracts the YouTube video ID from various URL formats.
    Handles standard, short, live, and Shorts video links.
    """
    if "watch?v=" in url:
        return url.split("watch?v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    elif "/live/" in url:
        return url.split("/live/")[1].split("?")[0]
    elif "/shorts/" in url: 
        return url.split("/shorts/")[1].split("?")[0]
    return None

@check_user_status
async def handle_youtube_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles messages containing YouTube URLs.
    """
    message = update.message
    url_entities = [entity for entity in message.entities if entity.type == 'url']
    if not url_entities:
        return 

    url = message.text[url_entities[0].offset : url_entities[0].offset + url_entities[0].length]

    video_id = get_yt_video_id(url)
    if not video_id:
        logging.info(f"Ignoring non-YouTube URL: {url}")
        return

    status_message = await message.reply_text(Texts.User.YOUTUBE_LOOKING_UP)

    try:
        transcript_list = ytt_api.list_transcripts(video_id)
        
        buttons = []
        for transcript in transcript_list:
            lang_name = transcript.language
            lang_code = transcript.language_code
            is_generated = " (auto)" if transcript.is_generated else ""
            
            button_text = f"{lang_name}{is_generated}"
            callback_data = f"yt:{video_id}:{lang_code}"
            
            buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        if not buttons:
            # This case will be caught by NoTranscriptFound, but we keep it for safety
            raise NoTranscriptFound(video_id)
            
        reply_text = Texts.User.YOUTUBE_CHOOSE_TRANSCRIPT.format(
            title=f"Video ID: {video_id}", 
            duration="N/A" 
        )
        
        await status_message.edit_text(
            reply_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML
        )

    except (TranscriptsDisabled, NoTranscriptFound, Exception) as e:
        # It's crucial to still log the *actual* error for debugging purposes
        logging.error(f"Could not retrieve YouTube transcript for {video_id}: {e}", exc_info=True)
        
        # Send the unified workaround message to the user
        await status_message.edit_text(
            text=Texts.Errors.YOUTUBE_TRANSCRIPT_UNAVAILABLE_WORKAROUND,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )


async def youtube_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the button press after a user chooses a transcript language.
    """
    query = update.callback_query
    await query.answer("در حال دریافت رونوشت...")

    try:
        _, video_id, lang_code = query.data.split(':')
    except (ValueError, IndexError):
        await query.edit_message_text(Texts.Errors.INVALID_CALLBACK_DATA)
        return

    try:
        transcript = ytt_api.get_transcript(video_id, languages=[lang_code])

        transcript_text = " ".join([segment['text'] for segment in transcript])
        
        source_info = {
            'type': 'youtube',
            'cost': 0.0,
            'id': video_id,
            'lang_code': lang_code
        }
        await deliver_transcription_result(update, context, transcript_text, source_info)

        await query.edit_message_text(f"✅ رونوشت زبان '{lang_code}' با موفقیت پردازش و ارسال شد.")

    except Exception as e:
        logging.error(f"Error processing YouTube callback for {video_id}: {e}", exc_info=True)
        await query.edit_message_text(Texts.Errors.YOUTUBE_FETCH_ERROR.format(error=e))        

