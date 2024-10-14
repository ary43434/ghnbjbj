import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext, CallbackQueryHandler
from pymongo import MongoClient
from datetime import datetime, timedelta
from telegram.error import BadRequest

# MongoDB Setup
try:
    client = MongoClient('mongodb+srv://VAISHNAV:VAISHNAV@cluster0.sn8ij4b.mongodb.net/?retryWrites=true&w=majority')
    db = client['video_bot']
    videos_db = db['videos']
    users_db = db['users']
    redeem_db = db['redeem_codes']
    logging.info("Connected to MongoDB successfully.")
except Exception as e:
    logging.error(f"Failed to connect to MongoDB: {str(e)}")

# Bot Token & Channel Info
BOT_TOKEN = '5583773090:AAFu8pMnjiRFzX4A77HTwTqo-NM9MMwXsSM'
CHANNEL_USERNAME = '@ary_botz'
CHANNEL_ID = -1002024225912  # Replace with your channel ID
VIDEO_LIMIT = 15  # Limit of videos users can watch before needing a redeem code
YOUR_ADMIN_IDS = [5079629749, 7013316052]  # Replace with the admin's Telegram IDs

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# /start command
async def start(update: Update, context: CallbackContext) -> None:
    logger.info(f"Start command received from user: {update.message.from_user.id}")
    user = update.message.from_user
    if not users_db.find_one({"user_id": user.id}):
        users_db.insert_one({"user_id": user.id, "videos_watched": 0, "redeemed": False, "video_index": 1})
    keyboard = [[InlineKeyboardButton("🎥 Get Videos", callback_data='get_videos')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"👋 Welcome, {user.first_name}!\nClick the button below to get videos.", reply_markup=reply_markup)

# /add command to upload videos
async def add_video(update: Update, context: CallbackContext) -> None:
    if update.message.from_user.id in YOUR_ADMIN_IDS:  # Check if the user is an admin
        if update.message.video:
            video_file_id = update.message.video.file_id
            video_index = videos_db.count_documents({}) + 1
            try:
                videos_db.insert_one({"index": video_index, "video_file_id": video_file_id})
                await update.message.reply_text(f"✅ Video added successfully with index {video_index}.")
            except Exception as e:
                logger.error(f"Error while adding video: {str(e)}")
                await update.message.reply_text("❌ Failed to add video. Please try again.")
        else:
            await update.message.reply_text("❌ Please upload a video.")
    else:
        await update.message.reply_text("❌ You are not authorized to perform this action.")

# /get_reed command to generate redeem codes
async def generate_redeem_code(update: Update, context: CallbackContext) -> None:
    if update.message.from_user.id in YOUR_ADMIN_IDS:  # Check if the user is an admin
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
                await update.message.reply_text("❌ Invalid format. Use `/get_reed 1d`, `/get_reed 2h`, etc.")
                return

            code = 'REDEEM-' + str(len(list(redeem_db.find())) + 1)
            redeem_db.insert_one({'code': code, 'expiry': expiry_time, 'used': False})
            await update.message.reply_text(f"✅ Redeem Code Generated: {code} (Expires on {expiry_time})")
        else:
            await update.message.reply_text("❌ Usage: `/get_reed 1d` for 1 day, `/get_reed 2h` for 2 hours, etc.")
    else:
        await update.message.reply_text("❌ You are not authorized.")

# /redeem command to redeem a code
async def redeem_code(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    user_data = users_db.find_one({"user_id": user_id})

    if user_data and user_data.get('redeemed', False):
        await update.message.reply_text("✅ You've already redeemed a code.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("❌ Usage: `/redeem <code>`")
        return

    code = context.args[0]
    redeem_data = redeem_db.find_one({'code': code})

    if redeem_data and not redeem_data['used']:
        if datetime.now() < redeem_data['expiry']:
            users_db.update_one({"user_id": user_id}, {"$set": {"redeemed": True}})
            redeem_db.update_one({'code': code}, {"$set": {'used': True}})
            await update.message.reply_text("✅ Redeem code successful!")
        else:
            await update.message.reply_text("❌ This redeem code has expired.")
    else:
        await update.message.reply_text("❌ Invalid or already used redeem code.")

# /index_videos command to index videos from a private channel
async def index_videos(update: Update, context: CallbackContext) -> None:
    if update.message.from_user.id in YOUR_ADMIN_IDS:  # Check if the user is an admin
        try:
            if len(context.args) != 2:
                await update.message.reply_text("❌ Usage: /index_videos <first_video_id> <latest_post_id>")
                return

            first_video_id = int(context.args[0])
            latest_post_id = int(context.args[1])

            # Fetch messages from the channel with specified IDs
            async for message in context.bot.get_chat_history(CHANNEL_ID, limit=100):
                if message.video:
                    # Check if the video falls within the specified range
                    if message.id >= first_video_id and message.id <= latest_post_id:
                        video_file_id = message.video.file_id
                        video_index = videos_db.count_documents({}) + 1
                        videos_db.insert_one({"index": video_index, "video_file_id": video_file_id})
                        logger.info(f"Indexed video {video_index} with file_id: {video_file_id}")

            await update.message.reply_text("✅ Videos indexed successfully.")
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to index videos: {str(e)}")
            logger.error(f"Error indexing videos: {str(e)}")
    else:
        await update.message.reply_text("❌ You are not authorized to perform this action.")

# /cmd command to display available commands
async def cmd_handler(update: Update, context: CallbackContext) -> None:
    commands = """
    /start - Start the bot
    /cmd - Show this help message
    /get_reed <time_period> - Admin: Generate redeem code (e.g., 1d, 2h, 30m)
    /redeem <code> - Redeem a code
    /index_videos - Admin: Index videos from channel
    /add - Admin: Upload a video to add to the database
    """
    await update.message.reply_text(commands)

# Get videos for the user
async def get_videos(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    user_data = users_db.find_one({"user_id": user_id})

    if user_data['videos_watched'] >= VIDEO_LIMIT and not user_data['redeemed']:
        await query.message.reply_text("🚫 You've reached your limit! Contact admin for a redeem code.")
        return

    video_index = user_data.get('video_index', 1)
    video_data = videos_db.find_one({'index': video_index})

    if video_data:
        video_file_id = video_data['video_file_id']
        next_button = InlineKeyboardButton("➡️ Next", callback_data='next_video')
        prev_button = InlineKeyboardButton("⬅️ Previous", callback_data='prev_video')

        keyboard = [[prev_button, next_button]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_video(video=video_file_id, reply_markup=reply_markup)

        users_db.update_one({"user_id": user_id}, {"$inc": {"videos_watched": 1}, "$set": {"video_index": video_index + 1}})
    else:
        await query.message.reply_text("🚫 No more videos available.")

# Handlers for Next and Previous buttons
async def next_video(update: Update, context: CallbackContext) -> None:
    await get_videos(update, context)

async def prev_video(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    user_data = users_db.find_one({"user_id": user_id})

    video_index = user_data.get('video_index', 1) - 1
    if video_index < 1:
        await query.message.reply_text("🚫 No previous video available.")
        return

    video_data = videos_db.find_one({'index': video_index})
    if video_data:
        video_file_id = video_data['video_file_id']
        next_button = InlineKeyboardButton("➡️ Next", callback_data='next_video')
        prev_button = InlineKeyboardButton("⬅️ Previous", callback_data='prev_video')

        keyboard = [[prev_button, next_button]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_video(video=video_file_id, reply_markup=reply_markup)
        users_db.update_one({"user_id": user_id}, {"$set": {"video_index": video_index}})
    else:
        await query.message.reply_text("🚫 No previous video available.")

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cmd", cmd_handler))
    application.add_handler(CommandHandler("add", add_video))
    application.add_handler(CommandHandler("get_reed", generate_redeem_code))
    application.add_handler(CommandHandler("redeem", redeem_code))
    application.add_handler(CommandHandler("index_videos", index_videos))

    # Callback query handlers
    application.add_handler(CallbackQueryHandler(get_videos, pattern='get_videos'))
    application.add_handler(CallbackQueryHandler(next_video, pattern='next_video'))
    application.add_handler(CallbackQueryHandler(prev_video, pattern='prev_video'))

    application.run_polling()

if __name__ == "__main__":
    main()
