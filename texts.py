# texts.py

class Texts:
    """
    A central repository for all text strings used in the SedaNevis bot.
    This makes management and future internationalization (i18n) easier.
    """
    class Keyboard:
        """Labels for keyboard buttons."""
        SUMMARY_SHORT = "📄 خلاصه خیلی کوتاه"
        EXTRACT_POINTS = "💡استخراج نکات مهم"
        EXTRACT_MINUTES = "📑 استخراج صورت جلسه"     
        TEXT_TO_SPEECH = "🔊 تبدیل به صوت"

        APPROVE_USER = "✅ Approve"
        REJECT_USER = "❌ Reject"

        LANG_FA = "🇮🇷 فارسی"
        LANG_EN = "🇬🇧 English"

    class User:
        """Messages sent to regular users."""
        NEW_USER_GREETING = (
            "👋 سلام !\n\n"
            "✨ به ربات صدانویس خوش آمدی. ✨\n\n"
            "🎧 ما اینجا از قویترین و به‌روزترین موتورهای هوش‌مصنوعی برای تبدیل صوت به متن، متن به صورت و پردازش محتوای متنی و Youtube استفاده می‌کنیم.\n\n"
            "📝 اینجا می‌تونی هر فایل صوتی، تصویری، Voice یا Youtube را به متن تبدیل کنی.\n\n"
            "درخواست شما برای استفاده از این ربات ثبت شد.\n\n"
            "👈 لطفاً تا زمان تایید توسط ادمین شکیبا باشید.\n\n"
            "@SedaNevis_Bot"
        )        
        PENDING_STATUS = "⏳ درخواست شما هنوز در انتظار تایید توسط ادمین است.\n\n@SedaNevis_bot"
        REJECTED_STATUS = "⛔ شما مجاز به استفاده از این ربات نیستید.\n\n@SedaNevis_bot"

        START_APPROVED = (
            "👋 سلام {first_name} عزیز!\n\n"
            "✨ به ربات صدانویس خوش آمدی. ✨\n\n"
            "🔉 اینجا می‌تونی هر فایل صوتی، تصویری و Voice یا حتی لینک ارسالی از Youtube رو به متن تبدیل کنی.\n\n"
            "📝 بعد از دریافت متن، می‌تونی اون رو خلاصه کنی، نکات اصلیش رو دربیاری یا به صورت‌جلسه تبدیلش کنی.\n\n"
            "💬 ما اینجا متن رو هم پردازش و تبدیل به صوت می‌کنیم. متن رو بفرست یا اینجا فوروارد کن یا حتی فایل docx بفرست و نتیجه رو ببین.\n\n"
            "🎧 بعد از پردازش متن می‌تونی خروجی رو به صوت تبدیل کرده و گوش کنی.\n\n"
            "کافیه فایلت رو بفرستی یا از جای دیگه فوروارد کنی 🙂\n\n"
            "@SedaNevis_Bot"
        )  
        PRIVACY = (
            "سلام {first_name} عزیز!\n\n"
            "*تعهد ما به حفظ حریم خصوصی شما*\n\n" 
            "اطمینان خاطر می‌دهیم که امنیت و حریم خصوصی شما برای ما در بالاترین اولویت قرار دارد. ربات «صدانویس» به شکل زیر عمل می‌کند:\n\n"
            "🛡️ *عدم ذخیره‌سازی فایل‌ها:* هیچ‌کدام از فایل‌های صوتی یا ویدیویی ارسالی شما پس از پردازش، بر روی سرورهای ما *ذخیره نمی‌شوند*.\n\n" # <-- Use single asterisks
            "🛡️ *عدم نگهداری متن:* متون تبدیل‌شده نیز صرفاً برای شما ارسال شده و در هیچ کجا *نگهداری یا آرشیو نمی‌گردند*.\n\n" # <-- Use single asterisks
            "تمامی فرآیندها به صورت لحظه‌ای انجام شده و داده‌های شما بلافاصله پس از اتمام کار به طور کامل حذف می‌شوند.\n\n"
            "*شفافیت کامل با کد منبع باز (Open Source)*\n" 
            "برای اطمینان کامل شما و اثبات این گفته، تمام کدهای این ربات به صورت عمومی در گیت‌هاب منتشر شده است. شما می‌توانید شخصاً کدها را بررسی نمایید:\n"
            "[https://github.com/h4med/sedanevis_bot](https://github.com/h4med/sedanevis_bot)\n\n" 
            "از اعتماد شما سپاسگزاریم."
        )                 
        TEXT_RECEIVED = "متن دریافت شد. چه کاری روی آن انجام دهم؟\n\n@SedaNevis_bot"
        TEXT_FILE_PROMPT = "فایل متنی خوانده شد. چه کاری روی آن انجام دهم؟\n\n@SedaNevis_bot"
        
        CREDIT_INSUFFICIENT = (
            "⛔ اعتبار شما کافی نیست.\n"
            "اعتبار فعلی: {current_credit:.1f} دقیقه\n"
            "هزینه این عملیات: {cost:.1f} دقیقه\n\n"
            "@SedaNevis_bot\n"
        )
        MEDIA_PROCESSING_MSG = (
            "فایل دریافت شد. طول فایل: {duration}\n\n"
            "دانلود: {download}\n"
            "پردازش: {process}\n"
            "رونویسی: {transcription}\n\n"
            "@SedaNevis_bot\n"
        )
        MEDIA_DOWNLOAD_START = "فایل دریافت شد! در حال دانلود و پردازش اولیه هستیم.\n\nاز شکیبایی شما سپاس‌گذاریم 🙏\n\n@SedaNevis_bot\n"
        MEDIA_DOWNLOAD_DONE = "فایل دانلود شد. در حال پردازش و استخراج صدا..."
        MEDIA_PROCESSING_DONE = (
            "پردازش اولیه تمام شد.\n"
            "طول فایل: {duration}\n\n"
            "در حال ارسال به سرویس رونویسی...\n"
            "(با توجه به طول فایل، ممکن است رونویسی تا چند دقیقه طول بکشد.)\n\n"
            "@SedaNevis_bot\n"
        )
        TRANSCRIPTION_IN_PROGRESS = (
            "🎤 پردازش اولیه تمام شد، در حال رونویسی هستیم.\n"
            "با توجه به طول فایل، ممکن است رونویسی تا چند دقیقه طول بکشد...\n\n"
            "از شکیبایی شما همچنان سپاس‌گذاریم 🙏\n\n"
            "⏳ پیشرفت: {progress:.0f}%\n\n"
            "@SedaNevis_bot\n"
        )
        TRANSCRIPTION_SUCCESS = "رونویسی با موفقیت انجام شد! ✅"
        TRANSCRIPTION_CAPTION = ( 
            "**رونوشت کامل فایل:**\n"
            "مدت زمان مصرف شده: {cost:.1f} دقیقه\n"
            "اعتبار باقی‌مانده: {remaining_credit:.1f} دقیقه\n\n"
            "چه کاری روی این متن انجام دهم؟\n@SedaNevis_bot\n"
        )
        
        PROCESSING_ACTION = "در حال اجرای «{action_text}»..."
        NO_RESPONSE_FROM_AI = "پاسخی دریافت نشد."
        
        ACTION_RESULT_HEADER = "<b>نتیجه برای «{action_text}»</b>"

        ACTION_RESULT_FOOTER = (
            "\n\n—————————————\n" #
            "هزینه عملیات: {cost:.1f} دقیقه\n"
            "<b>اعتبار باقی‌مانده: {remaining_credit:.1f} دقیقه</b>\n"
            "@SedaNevis_bot"
        )

        ACTION_RESULT_LONG_FILE_CAPTION = (
            "نتیجه درخواست شما به دلیل طولانی بودن در فایل ضمیمه شده است."
        )

        APPROVAL_SUCCESS = (
            "حساب شما تایید شد! شما اکنون می‌توانید از ربات استفاده کنید. \n"
            "برای شروع، یک فایل صوتی یا متن ارسال کنید.\n\n"
            "یا برای راهنمایی بیشتر دستور /start رو اجرا کن.\n\n"
            "@SedaNevis_bot"
        )
        APPROVAL_REJECTED = "متاسفانه درخواست شما برای استفاده از ربات رد شد."

        CREDIT_STATUS = (
            "📊 <b>وضعیت اعتبار شما</b>\n\n"
            "⏳ <b>اعتبار باقیمانده:</b> {credit:.1f} دقیقه\n\n"
            "<b>راهنمای شارژ اعتبار:</b>\n"
            "۱. به ادمین به شناسه @sedanevis_admin پیام دهید.\n"
            "۲. در پیام خود، <b>شناسه کاربری</b> زیر را ارسال کنید تا حساب شما شناسایی شود:\n"
            "\n<code>{user_id}</code>\n\n"
            "پس از هماهنگی و پرداخت، اعتبار به حساب شما اضافه خواهد شد.\n\n"
        )

        SETTINGS_PROMPT = (
            "⚙️ <b>تنظیمات</b>\n\n"
            "زبان ترجیحی فعلی شما برای پردازش: <b>{current_lang}</b>\n\n"
            "لطفا زبان جدید را انتخاب کنید:"
        )
        
        LANG_UPDATED_SUCCESS = (
            "⚙️ <b>تنظیمات</b>\n\n"
            "✅ زبان با موفقیت به <b>{new_lang}</b> تغییر یافت."
        )
        LANG_FA_NAME = "فارسی (fa)"
        LANG_EN_NAME = "English (en)"

        YOUTUBE_LOOKING_UP = "در حال بررسی لینک یوتیوب..."
        YOUTUBE_TEMP_MSG = "در حال دریافت رونوشت..."
        YOUTUBE_CHOOSE_TRANSCRIPT = (
            "✨ دریافت رونوشت از یوتیوب بدون هزینه است.\n\n"
            "لطفا زبان رونوشت مورد نظر خود را انتخاب کنید:"
        )
        TRANSCRIPTION_LONG_FILE_CAPTION = (
            "<b>رونوشت کامل در فایل ضمیمه شده است.</b>\n"
            "متن به دلیل طولانی بودن در قالب فایل ارسال شد.\n\n"
            "بخشی از متن:\n"
            "<code>{preview_text}...</code>\n\n"
            "{usage_info}"
            "چه کاری روی این متن انجام دهم؟\n@SedaNevis_bot"
        )

    class Admin:
        """Messages sent to the admin or related to admin actions."""
        ONLY_ADMIN_COMMAND = "⛔ This command is for admins only."
        NEW_USER_NOTIFICATION = (
            "👤 **New User Request**\n\n"
            "**Name:** {first_name}\n"
            "**Username:** @{username}\n"
            "**Telegram ID:** `{user_id}`\n"
            "**Language:** {lang_code}"
        )
        USER_APPROVED_NOTIFICATION = ( # Updated
            "✅ User <b>{first_name}</b> (<code>{user_id}</code>) has been <b>approved</b>.\n"
            "They have been granted {credit} minutes of credit."
        )

        USER_REJECTED_NOTIFICATION = "❌ User <b>{first_name}</b> (<code>{user_id}</code>) has been <b>rejected</b>."

        HELP_TEXT = (
            "<b>Admin Commands</b>\n\n"
            "<code>/list_users</code>\nShow a list of all users.\n\n"
            "<code>/user_info &lt;user_id&gt;</code>\nGet detailed info for a single user.\n\n"
            "<code>/add_credit &lt;user_id&gt; &lt;minutes&gt;</code>\nAdd credit to a user.\n\n"
            "<code>/set_status &lt;user_id&gt; &lt;status&gt;</code>\nChange a user's status (e.g., approved, banned).\n\n"
            "<code>/user_logs &lt;user_id&gt;</code>\nShow recent activity for a user."            
        )
        
        LIST_USERS_HEADER = "<b>👥 Users List</b>\n\n"
        LIST_USERS_ITEM = (
            "<b>{first_name}</b> (<code>{user_id}</code>)\n"
            "Profile: <b>{user_name}</b>\n"
            "Status: {status} | Credit: {credit:.1f} \n"
            "--------------------\n"
        )
        
        USER_INFO_HEADER = "<b>👤 User Info: {first_name}</b>\n\n"
        USER_INFO_BODY = ( # Updated
            "<b>Telegram ID:</b> <code>{user_id}</code>\n"
            "<b>Username:</b> @{username}\n"
            "<b>Status:</b> <code>{status}</code>\n"
            "<b>Credit:</b> {credit:.2f} minutes\n"
            "<b>Preferred Lang:</b> {lang}\n"
            "<b>Joined:</b> {joined_date}"
        )

        ADD_CREDIT_SUCCESS = ( # Updated
            "✅ Credit added successfully to <b>{first_name}</b>.\n\n"
            "Added: {minutes_added:.2f} minutes.\n"
            "New Balance: {new_credit:.2f} minutes."
        )

        USER_LOGS_HEADER = "<b>📜 Activity Logs for {first_name} ({user_id})</b>\n(Showing last 20 entries)\n\n"
        USER_LOGS_ITEM = "<code>{timestamp}</code>\n<b>Action:</b> {action}\n<b>Change:</b> {change:.2f} min | <b>Details:</b> {details}\n--------------------\n"
        NO_LOGS_FOUND = "No activity logs found for user <code>{user_id}</code>."

        SET_STATUS_SUCCESS = "✅ Status for <b>{first_name}</b> (<code>{user_id}</code>) has been updated to <code>{new_status}</code>."

    class Errors:
        """Error messages shown to users or admins."""
        GENERIC_UNEXPECTED = "در پردازش درخواست شما خطای غیرمنتظره‌ای رخ داد: {error}"
        GENERIC_UNEXPECTED_ADMIN = "An unexpected error occurred: {error}"
        
        INVALID_CALLBACK_DATA = "Error: Invalid callback data."
        INVALID_LANG_CALLBACK = "Error: Invalid language callback."
        USER_NOT_FOUND_IN_DB_ADMIN = "Error: User with ID {user_id} not found in database."
        USER_PROFILE_NOT_FOUND = "Error: Could not find your user profile."

        INVALID_TEXT_FILE = "لطفا فقط فایل متنی (مانند .txt) ارسال کنید."
        TEXT_FILE_PROCESS_FAILED = "خطا در پردازش فایل: {error}"
        AUDIO_TRANSCRIPTION_FAILED = "رونویسی با خطا مواجه شد: {error}"
        TEXT_PROCESS_FAILED = "پردازش متن با خطا مواجه شد: {error}"
        VIDEO_TOO_LONG = "⛔ فایل ارسال شده طولانی‌تر از حد مجاز (۱۸۰ دقیقه) است."
        TTS_TEXT_TOO_LONG = (
            "⛔ متن ارسالی برای تبدیل به صوت بیش از حد طولانی است.\n\n"
            "طول صوت تخمینی متن دریافتی: {estimated_duration:.1f} دقیقه\n"
            "حداکثر طول قابل قبول: {max_duration} دقیقه\n\n"
            "لطفا متن کوتاه‌تری ارسال کنید."
        )
        
        TEXT_NOT_FOUND = "خطا: متن اصلی یافت نشد. لطفاً دوباره متن یا فایل را ارسال کنید."
        ACTION_UNDEFINED = "خطا: فرمان '{action}' تعریف نشده است."
        OUTPUT_TOO_LONG = "Output too long to send as a single message."
        
        INVALID_USER_ID = "Invalid User ID. It must be a number."
        INVALID_ARGS_ADD_CREDIT = "Invalid arguments. User ID, minutes, and tokens must be numbers."
        
        USAGE_USER_INFO = "⚠️ Usage: <code>/user_info &lt;user_id&gt;</code>"
        USAGE_ADD_CREDIT = "⚠️ Usage: <code>/add_credit &lt;user_id&gt; &lt;minutes&gt;</code>"
        USAGE_USER_LOGS = "⚠️ Usage: <code>/user_logs &lt;user_id&gt;</code>"
        USAGE_SET_STATUS = (
            "⚠️ Usage: <code>/set_status &lt;user_id&gt; &lt;status&gt;</code>\n"
            "Valid statuses are: {valid_statuses}"
        )
        USAGE_DELETE_USER = "⚠️ Usage: <code>/delete_user &lt;user_id&gt;</code>"

        EXCEPTION_REPORT_HEADER = "An exception was raised while handling an update\n"
        YOUTUBE_INVALID_URL = "لینک یوتیوب نامعتبر است. لطفا یک لینک معتبر ارسال کنید."
        YOUTUBE_TRANSCRIPTS_DISABLED = "متاسفانه صاحب این ویدیو امکان دسترسی به رونوشت را غیرفعال کرده است."
        YOUTUBE_NO_TRANSCRIPTS = "متاسفانه هیچ رونوشتی (دستی یا خودکار) برای این ویدیو یافت نشد."
        YOUTUBE_TRANSCRIPTS_ERR_TRYAGAIN = "متاسفانه ارتباط با یوتیوب بیش از حد طول کشید و پاسخی دریافت نشد. لطفاً چند دقیقه دیگر دوباره امتحان کنید."
        YOUTUBE_FETCH_ERROR = "خطایی در دریافت اطلاعات از یوتیوب رخ داد: {error}"
        YOUTUBE_TRANSCRIPT_UNAVAILABLE_WORKAROUND = (
            "متاسفانه امکان دریافت مستقیم رونویس از این ویدیو وجود ندارد.\n"
            "این مشکل معمولاً به دلیل در حال پردازش بودن ویدیو، غیرفعال بودن رونویس، یا عدم وجود آن رخ می‌دهد.\n\n"
            "**راه حل جایگزین:**\n"
            "شما می‌توانید فایل صوتی این ویدیو را از طریق ربات زیر دریافت کرده و سپس آن را برای من ارسال (فوروارد) کنید:\n\n"
            "۱. لینک یوتیوب را برای ربات @Gozilla_bot ارسال کنید.\n"
            "۲. این ربات فایل صوتی ویدیو را برای شما ارسال می‌کند.\n"
            "۳. فایل صوتی دریافت شده را مستقیماً به اینجا فوروارد کنید تا رونویسی شود."
        )
        
    class BotCommands:
        """Descriptions for Bot Commands shown in Telegram."""
        START = "شروع مجدد ربات | Restart the Bot"
        PRIVACY = "حفظ حریم خصوصی کاربر | Privacy"
        CREDIT = "مشاهده اعتبار باقی‌مانده | Check Credit"
        SETTINGS = "تنظیمات زبان | Language Settings"
        ADMIN_HELP = "Show all admin commands"
        LIST_USERS = "List all users"
        USER_INFO = "Get info for a user"
        ADD_CREDIT = "Add credit to a user"
        SET_STATUS = "Set a user's status"
        USER_LOGS = "Get activity logs for a user"
        DEL_USER = "Delete a user from the database"