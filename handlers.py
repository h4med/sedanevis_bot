# handlers.py
import logging
import os
import traceback
import html
import json
import asyncio
import jdatetime
import pytz

from functools import wraps
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

import config
from prompts import TRANSCRIBER_PROMPT, ACTIONS_PROMPT_MAPPING


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
    transcribe_audio_google_sync
)
from database import SessionLocal, User, ActivityLog
from texts import Texts
from utils import (
    convert_md_to_html, deliver_transcription_result, 
    log_activity, check_user_status,
    get_action_keyboard, ensure_telethon_client,
    create_word_document, extract_text_from_docx
)

admin_user_id = config.ADMIN_USER_ID

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
    if update.message.text:  # Regular text message
        text = update.message.text
    elif update.message.document:  # DOCX file
        text = await extract_text_from_docx(update, context)
        if text is None:
            return  # Error occurred, message already sent to user
    else:
        await update.message.reply_text("Unsupported message type.")
        return
        
    # text = update.message.text
    logging.info(f"Received text input from user {update.effective_user.id}. Length: {len(text)} chars.")
    context.user_data['last_text'] = text

    loop = asyncio.get_event_loop()
    transcription_tokens = await loop.run_in_executor(
        config.TOKEN_COUNTING_EXECUTOR,
        count_text_tokens,
        text,
        "gemini-2.0-flash-lite"
    )    
    action1_estimated_minutes = (transcription_tokens + 500) / config.TEXT_TOKENS_TO_MINUTES_COEFF
    action2_estimated_minutes = (transcription_tokens + 2000) / config.TEXT_TOKENS_TO_MINUTES_COEFF
    action3_estimated_minutes = (transcription_tokens + 1000) / config.TEXT_TOKENS_TO_MINUTES_COEFF

    await update.message.reply_text(
        Texts.User.TEXT_RECEIVED,        
        reply_markup=get_action_keyboard(
            action1_estimated_minutes,
            action2_estimated_minutes,
            action3_estimated_minutes
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
        transcription_tokens = await loop.run_in_executor(
            config.TOKEN_COUNTING_EXECUTOR,
            count_text_tokens,
            text,
            "gemini-2.0-flash-lite"
        )    
        action1_estimated_minutes = (transcription_tokens + 500) / config.TEXT_TOKENS_TO_MINUTES_COEFF
        action2_estimated_minutes = (transcription_tokens + 2000) / config.TEXT_TOKENS_TO_MINUTES_COEFF
        action3_estimated_minutes = (transcription_tokens + 1000) / config.TEXT_TOKENS_TO_MINUTES_COEFF

        await status_message.edit_text(
            Texts.User.TEXT_FILE_PROMPT,
            # reply_markup=get_action_keyboard()
            reply_markup=get_action_keyboard(
                action1_estimated_minutes,
                action2_estimated_minutes,
                action3_estimated_minutes
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

    if cost_minutes > db_user.credit_minutes:
        await message.reply_text(
            Texts.User.CREDIT_INSUFFICIENT.format(
                current_credit=db_user.credit_minutes,
                cost=cost_minutes
            )
        )
        return

    status_message = await message.reply_text(Texts.User.MEDIA_DOWNLOAD_START)
    downloads_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    original_extension = os.path.splitext(original_filename)[1] or '.tmp'
    local_file_path = os.path.join(downloads_dir, f"downloaded_{file_object.file_unique_id}{original_extension}")    
    ready_for_transcription_path = None
    
    try:
        logging.info(f"Downloading file. Size: {file_object.file_size} bytes.")
        if file_object.file_size > config.TELEGRAM_MAX_BOT_API_FILE_SIZE:
            logging.info("File is larger than 20MB, using Telethon for download.")
            client = await ensure_telethon_client()
            # Telethon can get the message by its ID and download the media within it
            telethon_message = await client.get_messages(entity=message.chat_id, ids=message.message_id)
            if not telethon_message or not (telethon_message.audio or telethon_message.voice or telethon_message.video or telethon_message.document):
                raise ValueError("Could not find media in message via Telethon.")
            await client.download_media(telethon_message, file=local_file_path)
        else:
            logging.info("File is smaller than 20MB, using Bot API for download.")
            bot_file = await context.bot.get_file(file_object.file_id)
            await bot_file.download_to_drive(local_file_path)

        audio = AudioSegment.from_file(local_file_path)
        processed_audio = audio.set_frame_rate(32000).set_channels(1)
        ready_for_transcription_path = f"downloads/converted_{file_object.file_unique_id}.mp3"
        processed_audio.export(ready_for_transcription_path, format="mp3", bitrate="32k")
        duration_str = f"{len(audio) // 60000:02d}:{ (len(audio) // 1000) % 60:02d}"

        await status_message.edit_text(
            Texts.User.MEDIA_PROCESSING_DONE.format(duration=duration_str)
        )
            
        loop = asyncio.get_event_loop()
        transcription_result_dict = await loop.run_in_executor(
            config.TRANSCRIPTION_EXECUTOR,
            transcribe_audio_google_sync,
            ready_for_transcription_path,
            duration_seconds,
            "gemini-2.5-flash",
            TRANSCRIBER_PROMPT,            
        )
        

        if transcription_result_dict.get("error"):
            await status_message.edit_text(Texts.Errors.AUDIO_TRANSCRIPTION_FAILED.format(error=transcription_result_dict['error']))
            return

        raw_transcript = transcription_result_dict.get("transcription", "")
        language = db_user.preferred_language

        logging.info(f"Transcription successful. Length: {len(raw_transcript)} chars")

        await status_message.edit_text(Texts.User.TRANSCRIPTION_SUCCESS)

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
        # Clean up all generated files
        if os.path.exists(local_file_path):
            os.remove(local_file_path)
        if ready_for_transcription_path and os.path.exists(ready_for_transcription_path):
            os.remove(ready_for_transcription_path)


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
        # prompt_template = Texts.Prompts.GEMINI_PROMPT_MAPPING.get(action)
        prompt_template = ACTIONS_PROMPT_MAPPING.get(action)
        if not prompt_template:
            await processing_message.edit_text(text=Texts.Errors.ACTION_UNDEFINED.format(action=action))
            return
        
        full_prompt = prompt_template.format(text=text_to_process)
        # estimated_tokens = await count_text_tokens(full_prompt)

        loop = asyncio.get_event_loop()
        estimated_tokens = await loop.run_in_executor(
            config.TOKEN_COUNTING_EXECUTOR,
            count_text_tokens,
            full_prompt,
            "gemini-2.0-flash-lite"
        )   

        cost_minutes = estimated_tokens / config.TEXT_TOKENS_TO_MINUTES_COEFF
        
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
            "gemini-2.5-flash-lite"  # or your preferred model
        )

        
        if result_dict.get("error"):
            await processing_message.edit_text(Texts.Errors.TEXT_PROCESS_FAILED.format(error=result_dict['error']))
            return

        total_tokens_consumed = result_dict.get("total_token_count", 0)
        input_tc = result_dict.get("prompt_token_count", 0)
        output_tc = result_dict.get("candidates_token_count", 0)
        logging.info(f"Action-{button_text} done, for {db_user.user_id},Tokens Input: {input_tc}, Output: {output_tc}, Total: {total_tokens_consumed}")
                    
        # prompt_tokens_used = result_dict.get("prompt_token_count", 0)
        # output_tokens_generated = result_dict.get("candidates_token_count", 0)
        # total_tokens_consumed = result_dict.get("total_token_count", 0)
        # total_tokens_consumed = prompt_tokens_used + output_tokens_generated
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
                # document_buffer = create_word_document(result_text_md, user_lang )
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



# Handler for Admin Approval Callbacks 
async def approval_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'approve' and 'reject' callbacks from the admin."""
    query = update.callback_query
    await query.answer()

    admin_user = update.effective_user
    if admin_user.id != config.ADMIN_USER_ID:
        # It's better practice to just return if a non-admin somehow triggers this
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
            # await query.edit_message_text(f"Error: User with ID {target_user_id} not found in database.")
            await query.edit_message_text(Texts.Errors.USER_NOT_FOUND_IN_DB_ADMIN.format(user_id=target_user_id))            
            return

        # --- Use html.escape on any user-provided text ---
        safe_first_name = html.escape(target_user.first_name)

        if action == 'approve':
            target_user.status = 'approved'
            # target_user.audio_minutes_credit = config.DEFAULT_AUDIO_MINUTES_CREDIT
            # target_user.text_tokens_credit = config.DEFAULT_TEXT_TOKENS_CREDIT
            target_user.credit_minutes = config.DEFAULT_CREDIT_MINUTES # <-- UPDATED            
            db.commit()
            # Log the initial credit grant
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
                    # audio_credit=config.DEFAULT_AUDIO_MINUTES_CREDIT,
                    # text_credit=config.DEFAULT_TEXT_TOKENS_CREDIT
                    credit=config.DEFAULT_CREDIT_MINUTES # <-- UPDATED                    
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
            # Try to inform the admin that something went wrong
            # await query.edit_message_text(f"An error occurred while processing the request: {e}")
            await query.edit_message_text(Texts.Errors.GENERIC_UNEXPECTED_ADMIN.format(error=e))            
        except:
            pass # If editing the message fails, just log it.
    finally:
        db.close()


@check_user_status
async def credit_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /credit command, showing the user their remaining credits.
    """
    # The decorator ensures the user is approved and loads them into context.
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
        # Handle long lists by splitting the message
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
        info_body = Texts.Admin.USER_INFO_BODY.format( # Uses updated text
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

        confirmation_text = Texts.Admin.ADD_CREDIT_SUCCESS.format( # Uses updated text
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
    elif "/live/" in url: # <-- ADDED THIS FOR LIVE VIDEOS
        return url.split("/live/")[1].split("?")[0]
    elif "/shorts/" in url: # <-- ADDED THIS FOR SHORTS (recommended)
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
        return # Should not happen with the filter, but good practice

    url = message.text[url_entities[0].offset : url_entities[0].offset + url_entities[0].length]

    # Check if it's a youtube link
    video_id = get_yt_video_id(url)
    if not video_id:
        # It was a URL, but not one we recognize as YouTube. Silently ignore.
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
            await status_message.edit_text(Texts.Errors.YOUTUBE_NO_TRANSCRIPTS)
            return
            
        reply_text = Texts.User.YOUTUBE_CHOOSE_TRANSCRIPT.format(
            title=f"Video ID: {video_id}", 
            duration="N/A" # Placeholder
        )
        
        await status_message.edit_text(
            reply_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.HTML
        )

    except TranscriptsDisabled:
        await status_message.edit_text(Texts.Errors.YOUTUBE_TRANSCRIPTS_DISABLED)
    except NoTranscriptFound:
        await status_message.edit_text(Texts.Errors.YOUTUBE_NO_TRANSCRIPTS)
    except Exception as e:
        logging.error(f"Error fetching YouTube info for {video_id}: {e}", exc_info=True)
        await status_message.edit_text(Texts.Errors.YOUTUBE_FETCH_ERROR.format(error=e))


async def youtube_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the button press after a user chooses a transcript language.
    """
    query = update.callback_query
    await query.answer("در حال دریافت رونوشت...")

    try:
        # Callback data format: "yt:VIDEO_ID:LANG_CODE"
        _, video_id, lang_code = query.data.split(':')
    except (ValueError, IndexError):
        await query.edit_message_text(Texts.Errors.INVALID_CALLBACK_DATA)
        return

    try:
        # Fetch the selected transcript
        transcript = ytt_api.get_transcript(video_id, languages=[lang_code])
        
        # Concatenate the text from each segment
        transcript_text = " ".join([segment['text'] for segment in transcript])
        
        source_info = {
            'type': 'youtube',
            'cost': 0.0, # Fetching is free
            'id': video_id,
            'lang_code': lang_code
        }
        # Note: we pass query here so the helper can use `query.message.reply...`
        await deliver_transcription_result(update, context, transcript_text, source_info)

        # Edit the original message to show the action was successful
        await query.edit_message_text(f"✅ رونوشت زبان '{lang_code}' با موفقیت پردازش و ارسال شد.")

    except Exception as e:
        logging.error(f"Error processing YouTube callback for {video_id}: {e}", exc_info=True)
        await query.edit_message_text(Texts.Errors.YOUTUBE_FETCH_ERROR.format(error=e))        