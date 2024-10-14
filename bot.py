import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from pymongo import MongoClient
from datetime import datetime, timedelta
from telegram.error import BadRequest

# MongoDB Setup
client = MongoClient('your_mongodb_connection_uri')
db = client['video_bot']
videos_db = db['videos']
users_db = db['users']
redeem_db = db['redeem_codes']

# Bot Token & Channel Info
BOT_TOKEN = 'your_bot_token'
CHANNEL_USERNAME = '@your_channel'
CHANNEL_ID = -100123456789  # Replace with your channel ID
VIDEO_LIMIT = 15  # Limit of videos users can watch before needing a redeem code
your_admin_id = 123456789  # Replace with the admin's Telegram ID

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# /start command with forced subscription check
def start(update: Update, context):
    user = update.message.from_user
    chat_member = context.bot.get_chat_member(CHANNEL_ID, user.id)
    
    if chat_member.status in ['left', 'kicked']:
        keyboard = [[InlineKeyboardButton(f"Join {CHANNEL_USERNAME}", url=f"https://t.me/{CHANNEL_USERNAME}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("⚠️ Please join the channel to use this bot.", reply_markup=reply_markup)
    else:
        if not users_db.find_one({"user_id": user.id}):
            users_db.insert_one({"user_id": user.id, "videos_watched": 0, "redeemed": False, "video_index": 1})
        keyboard = [[InlineKeyboardButton("🎥 Get Videos", callback_data='get_videos')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(f"👋 Welcome, {user.first_name}!\nClick the button below to get videos.", reply_markup=reply_markup)

# /get_reed command to generate redeem codes
def generate_redeem_code(update: Update, context):
    if update.message.from_user.id == your_admin_id:
        if len(context.args) == 1:
            duration_str = context.args[0]
            time_unit = duration_str[-1]  # 'd' for days, 'h' for hours, 'm' for minutes
            time_value = int(duration_str[:-1])

            if time_unit == 'd':
                expiry_time = datetime.now() + timedelta(days=time_value)
            elif time_unit == 'h':
                expiry_time = datetime.now() + timedelta(hours=time_value)
            elif time_unit == 'm':
                expiry_time = datetime.now() + timedelta(minutes=time_value)
            else:
                update.message.reply_text("❌ Invalid format. Use `/get_reed 1d`, `/get_reed 2h`, etc.")
                return

            code = 'REDEEM-' + str(len(list(redeem_db.find())) + 1)
            redeem_db.insert_one({'code': code, 'expiry': expiry_time, 'used': False})
            update.message.reply_text(f"✅ Redeem Code Generated: {code} (Expires on {expiry_time})")
        else:
            update.message.reply_text("❌ Usage: `/get_reed 1d` for 1 day, `/get_reed 2h` for 2 hours, etc.")
    else:
        update.message.reply_text("❌ You are not authorized.")

# /redeem command to redeem a code
def redeem_code(update: Update, context):
    user_id = update.message.from_user.id
    user_data = users_db.find_one({"user_id": user_id})
    
    if user_data['redeemed']:
        update.message.reply_text("✅ You've already redeemed a code.")
        return
    
    code = context.args[0]
    redeem_data = redeem_db.find_one({'code': code})
    
    if redeem_data and not redeem_data['used']:
        if datetime.now() < redeem_data['expiry']:
            users_db.update_one({"user_id": user_id}, {"$set": {"redeemed": True}})
            redeem_db.update_one({'code': code}, {"$set": {'used': True}})
            update.message.reply_text("✅ Redeem code successful!")
        else:
            update.message.reply_text("❌ This redeem code has expired.")
    else:
        update.message.reply_text("❌ Invalid or already used redeem code.")

# /index_videos command to index videos from a private channel
def index_videos(update: Update, context):
    if update.message.from_user.id == your_admin_id:
        try:
            messages = context.bot.get_chat_history(CHANNEL_ID, limit=100)

            video_count = 0
            for message in messages:
                if message.video:
                    video_file_id = message.video.file_id
                    video_index = len(list(videos_db.find())) + 1
                    videos_db.insert_one({"index": video_index, "video_file_id": video_file_id})
                    video_count += 1

            update.message.reply_text(f"✅ {video_count} videos indexed from the channel.")
        except BadRequest as e:
            update.message.reply_text(f"❌ Failed to index videos: {str(e)}")
    else:
        update.message.reply_text("❌ You are not authorized to perform this action.")

# /cmd command to display available commands
def cmd_handler(update: Update, context):
    commands = """
    /start - Start the bot
    /cmd - Show this help message
    /get_reed <time_period> - Admin: Generate redeem code (e.g., 1d, 2h, 30m)
    /redeem <code> - Redeem a code
    /index_videos - Admin: Index videos from channel
    """
    update.message.reply_text(commands)

# Get videos for the user
def get_videos(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id
    user_data = users_db.find_one({"user_id": user_id})

    if user_data['videos_watched'] >= VIDEO_LIMIT and not user_data['redeemed']:
        query.message.reply_text("🚫 You've reached your limit! Contact admin for a redeem code.")
        return

    video_index = user_data.get('video_index', 1)
    video_data = videos_db.find_one({'index': video_index})

    if video_data:
        video_file_id = video_data['video_file_id']
        next_button = InlineKeyboardButton("➡️ Next", callback_data='next_video')
        prev_button = InlineKeyboardButton("⬅️ Previous", callback_data='prev_video')

        keyboard = [[prev_button, next_button]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        query.message.reply_video(video=video_file_id, reply_markup=reply_markup)
        
        users_db.update_one({"user_id": user_id}, {"$inc": {"videos_watched": 1}, "$set": {"video_index": video_index + 1}})
    else:
        query.message.reply_text("🚫 No more videos available.")

# Handlers for Next and Previous buttons
def next_video(update: Update, context):
    get_videos(update, context)

def prev_video(update: Update, context):
    user_id = update.callback_query.from_user.id
    user_data = users_db.find_one({"user_id": user_id})

    if user_data['video_index'] > 1:
        users_db.update_one({"user_id": user_id}, {"$set": {"video_index": user_data['video_index'] - 1}})
    get_videos(update, context)

# Main bot execution
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(get_videos, pattern='get_videos'))
    dp.add_handler(CallbackQueryHandler(next_video, pattern='next_video'))
    dp.add_handler(CallbackQueryHandler(prev_video, pattern='prev_video'))
    dp.add_handler(CommandHandler("get_reed", generate_redeem_code))
    dp.add_handler(CommandHandler("redeem", redeem_code))
    dp.add_handler(CommandHandler("cmd", cmd_handler))
    dp.add_handler(CommandHandler("index_videos", index_videos))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
