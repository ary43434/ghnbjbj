import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext, MessageHandler, filters, CallbackQueryHandler
from pymongo import MongoClient
from datetime import datetime, timedelta

# MongoDB Setup
client = 'mongodb+srv://VAISHNAV:VAISHNAV@cluster0.sn8ij4b.mongodb.net/?retryWrites=true&w=majority'
db = client['video_bot']
videos_db = db['videos']
users_db = db['users']
redeem_db = db['redeem_codes']

# Bot Token & Admin Info
BOT_TOKEN = '5583773090:AAFTZEaM7ZDQiFpLbE7TFne-s-ulZnm76fk'  # Replace with your bot token
VIDEO_LIMIT = 10  # Maximum videos to watch without a redeem code
ADMINS = [5079629749, 7013316052]  # Replace with your admin Telegram IDs

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# /start command
async def start(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user

    if not users_db.find_one({"user_id": user.id}):
        users_db.insert_one({"user_id": user.id, "videos_watched": 0, "redeemed": False,
                             "video_index": 1, "next_command_count": 0, "last_reset": datetime.now()})

    keyboard = [[InlineKeyboardButton("🎥 Get Videos", callback_data='get_videos')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"👋 Welcome, <b>{user.first_name}</b>!\n"
        f"Click the button below to get videos.\n"
        f"🌟 Note: You can watch up to {VIDEO_LIMIT} videos before needing a redeem code.",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# /get_reed command to generate redeem codes
async def generate_redeem_code(update: Update, context: CallbackContext) -> None:
    if update.message.from_user.id in ADMINS:
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
            await update.message.reply_text(f"✅ Redeem Code Generated: <b>{code}</b> (Expires on {expiry_time})", parse_mode='HTML')
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
            await update.message.reply_text("✅ Redeem code successful! You can now watch more videos.")
        else:
            await update.message.reply_text("❌ This redeem code has expired.")
    else:
        await update.message.reply_text("❌ Invalid or already used redeem code.")

# /add command to upload and add a video to the database
async def add_video(update: Update, context: CallbackContext) -> None:
    if update.message.from_user.id in ADMINS:
        await update.message.reply_text("📥 Please send the video you want to add.")
        context.user_data['adding_video'] = True  # Flag to indicate we're expecting a video
    else:
        await update.message.reply_text("❌ You are not authorized to perform this action.")

# Handle incoming videos
async def handle_video(update: Update, context: CallbackContext) -> None:
    if context.user_data.get('adding_video', False):
        video_file_id = update.message.video.file_id
        video_index = videos_db.count_documents({}) + 1
        videos_db.insert_one({"index": video_index, "video_file_id": video_file_id})
        logger.info(f"Added video {video_index} with file_id: {video_file_id}")
        await update.message.reply_text(f"✅ Video {video_index} added successfully.")
        context.user_data['adding_video'] = False  # Reset the flag

        # Schedule video deletion after 5 minutes
        await asyncio.sleep(300)  # 5 minutes
        videos_db.delete_one({"index": video_index})
        logger.info(f"Deleted video {video_index} after 5 minutes.")
    else:
        await update.message.reply_text("❌ Please use the /add command to upload a video.")

# /cmd command to display available commands
async def cmd_handler(update: Update, context: CallbackContext) -> None:
    commands = """
    🛠️ <b>Available Commands:</b>
    /start - Start the bot
    /cmd - Show this help message
    /get_reed <time_period> - Admin: Generate redeem code (e.g., 1d, 2h, 30m)
    /redeem <code> - Redeem a code
    /add - Admin: Upload a video to add to the database
    """
    await update.message.reply_text(commands, parse_mode='HTML')

# Get videos for the user
async def get_videos(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    user_data = users_db.find_one({"user_id": user_id})

    if user_data['videos_watched'] >= VIDEO_LIMIT and not user_data['redeemed']:
        await query.message.reply_text("🚫 You've reached your limit! Contact admin for a redeem code.")
        return

    # Reset the user limit if 24 hours have passed
    if datetime.now() - user_data['last_reset'] > timedelta(hours=24):
        users_db.update_one({"user_id": user_id}, {"$set": {"videos_watched": 0, "next_command_count": 0, "last_reset": datetime.now()}})
        await query.message.reply_text("✅ Your video limit has been reset! You can now watch up to 10 videos again.")

    video_index = user_data.get('video_index', 1)
    video_data = videos_db.find_one({'index': video_index})

    if video_data:
        video_file_id = video_data['video_file_id']
        next_button = InlineKeyboardButton("➡️ Next", callback_data='next_video')

        keyboard = [[next_button]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_video(video=video_file_id, reply_markup=reply_markup)
        users_db.update_one({"user_id": user_id}, {"$inc": {"videos_watched": 1}, "$set": {"video_index": video_index}})
    else:
        await query.message.reply_text("❌ No more videos available.")

# Handle next video navigation
async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    user_data = users_db.find_one({"user_id": user_id})

    if query.data == 'next_video':
        if user_data['redeemed'] or user_data['next_command_count'] < 10:
            user_data['next_command_count'] += 1
            user_data['video_index'] += 1
        else:
            await query.message.reply_text("🚫 You've reached the maximum number of next commands allowed. Contact admin for a redeem code.")
            return

        # Get the next video
        video_index = user_data['video_index']
        video_data = videos_db.find_one({'index': video_index})

        if video_data:
            video_file_id = video_data['video_file_id']
            await query.message.reply_video(video=video_file_id, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Next", callback_data='next_video')]]))
            users_db.update_one({"user_id": user_id}, {"$set": {"video_index": video_index}})
        else:
            await query.message.reply_text("❌ No more videos available.")

# Error handling
async def error_handler(update: Update, context: CallbackContext) -> None:
    logger.warning(f'Update "{update}" caused error "{context.error}"')
    await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ An error occurred.")

def main() -> None:
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("get_reed", generate_redeem_code))
    application.add_handler(CommandHandler("redeem", redeem_code))
    application.add_handler(CommandHandler("add", add_video))
    application.add_handler(CommandHandler("cmd", cmd_handler))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_handler(CallbackQueryHandler(get_videos, pattern='get_videos'))
    application.add_handler(CallbackQueryHandler(button_handler, pattern='next_video'))
    application.add_error_handler(error_handler)

    application.run_polling()

if __name__ == '__main__':
    main()
