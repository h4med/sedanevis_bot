# main.py
import logging
from telegram import Update, BotCommand, BotCommandScopeChat
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import TG_BOT_TOKEN, configure_logging, ADMIN_USER_ID 
from handlers import (
    start,
    privacy,
    handle_media_file, 
    button_callback_handler,
    handle_text_file,
    handle_text_input,
    error_handler,
    approval_callback_handler,
    credit_command_handler,
    settings_command_handler,
    set_language_callback_handler,
    admin_help_command,        
    list_users_command,        
    user_info_command,         
    add_credit_command,        
    set_status_command,
    user_logs_command,   
    handle_youtube_url,    
    youtube_callback_handler,   
    handle_video_file,
    handle_video_callback,    
    delete_user_command
)
from database import create_db_and_tables
from texts import Texts  

async def post_init(application: Application):
    """
    Sets the bot's commands for regular users and a separate set for the admin.
    """
    # Define commands for regular users using the Texts class
    user_commands = [
        BotCommand("/start", Texts.BotCommands.START),
        BotCommand("/privacy", Texts.BotCommands.PRIVACY),
        BotCommand("/credit", Texts.BotCommands.CREDIT),
        BotCommand("/settings", Texts.BotCommands.SETTINGS),
    ]
    await application.bot.set_my_commands(user_commands)
    logging.info("User commands have been set for the default scope.")

    # Define a more extensive list of commands for the admin
    admin_commands = user_commands + [
        BotCommand("/admin_help", Texts.BotCommands.ADMIN_HELP),
        BotCommand("/list_users", Texts.BotCommands.LIST_USERS),
        BotCommand("/user_info", Texts.BotCommands.USER_INFO),
        BotCommand("/add_credit", Texts.BotCommands.ADD_CREDIT),
        BotCommand("/set_status", Texts.BotCommands.SET_STATUS),
        BotCommand("/user_logs", Texts.BotCommands.USER_LOGS),
        BotCommand("/delete_user", Texts.BotCommands.DEL_USER),
    ]
    # Set the admin commands only for the admin's chat
    await application.bot.set_my_commands(
        admin_commands, 
        scope=BotCommandScopeChat(chat_id=ADMIN_USER_ID)
    )
    logging.info(f"Admin commands have been set for admin user {ADMIN_USER_ID}.")

def main() -> None:
    """Start the bot."""
    configure_logging()
    create_db_and_tables()

    builder = Application.builder().token(TG_BOT_TOKEN)

    # Set connection and read/write timeouts for all requests
    # Increasing the read/write timeouts to 30 seconds as a better default
    builder.connect_timeout(30.0)
    builder.read_timeout(60.0)
    builder.write_timeout(60.0)

    application = (
        builder
        .concurrent_updates(True)
        .post_init(post_init)
        .build()
    )

    # User Command handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('privacy', privacy))
    application.add_handler(CommandHandler('credit', credit_command_handler))
    application.add_handler(CommandHandler('settings', settings_command_handler))
    
    # Admin Command handlers
    application.add_handler(CommandHandler('admin_help', admin_help_command)) 
    application.add_handler(CommandHandler('list_users', list_users_command)) 
    application.add_handler(CommandHandler('user_info', user_info_command))   
    application.add_handler(CommandHandler('add_credit', add_credit_command)) 
    application.add_handler(CommandHandler('set_status', set_status_command)) 
    application.add_handler(CommandHandler('user_logs', user_logs_command)) 
    application.add_handler(CommandHandler("delete_user", delete_user_command))

    application.add_handler(MessageHandler(
        filters.VOICE | filters.AUDIO, 
        handle_media_file
    ))    
    application.add_handler(MessageHandler(filters.VIDEO, handle_video_file))
    application.add_handler(MessageHandler(filters.Document.TEXT, handle_text_file))
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Entity("url") & (~filters.COMMAND), 
        handle_youtube_url
    ))


    application.add_handler(MessageHandler(
        (filters.TEXT | filters.Document.MimeType("application/vnd.openxmlformats-officedocument.wordprocessingml.document")) & 
        (~filters.COMMAND), 
        handle_text_input
    ))    

    application.add_handler(CallbackQueryHandler(approval_callback_handler, pattern=r'^(approve|reject):'))
    application.add_handler(CallbackQueryHandler(set_language_callback_handler, pattern=r'^set_lang:'))
    application.add_handler(CallbackQueryHandler(youtube_callback_handler, pattern=r'^yt:'))
    application.add_handler(CallbackQueryHandler(handle_video_callback, pattern=r'^video_(raw|srt):'))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    application.add_error_handler(error_handler)

    logging.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()