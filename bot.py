import os
import logging
import asyncio
from datetime import datetime, timedelta
from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message

# MongoDB setup
client = MongoClient('mongodb+srv://VAISHNAV:VAISHNAV@cluster0.sn8ij4b.mongodb.net/?retryWrites=true&w=majority')
db = client['video_bot']
videos_db = db['videos']
users_db = db['users']
redeem_db = db['redeem_codes']

# Bot Token & Admin Info
API_ID = '27002519'  # Replace with your API ID
API_HASH = '1033ee721101d78366b4ac46aadf3930'  # Replace with your API Hash
BOT_TOKEN = '5583773090:AAHr7flM2h626zD50naoRMOb3yWkPwrtpP8'  # Replace with your bot token
VIDEO_LIMIT = 10
ADMINS = [5079629749, 7013316052]

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize the bot
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start(client: Client, message: Message):
    user = message.from_user

    if not users_db.find_one({"user_id": user.id}):
        users_db.insert_one({"user_id": user.id, "videos_watched": 0, "redeemed": False,
                             "video_index": 1, "next_command_count": 0, "last_reset": datetime.now()})

    keyboard = [[InlineKeyboardButton("🎥 Get Videos", callback_data='get_videos')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        f"👋 Welcome, <b>{user.first_name}</b>!\n"
        f"Click the button below to get videos.\n"
        f"🌟 Note: You can watch up to {VIDEO_LIMIT} videos before needing a redeem code.",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

@app.on_message(filters.command("get_reed"))
async def generate_redeem_code(client: Client, message: Message):
    if message.from_user.id in ADMINS:
        if len(message.command) == 2:
            duration_str = message.command[1]
            time_unit = duration_str[-1]
            time_value = int(duration_str[:-1])

            if time_unit == 'd':
                expiry_time = datetime.now() + timedelta(days=time_value)
            elif time_unit == 'h':
                expiry_time = datetime.now() + timedelta(hours=time_value)
            elif time_unit == 'm':
                expiry_time = datetime.now() + timedelta(minutes=time_value)
            else:
                await message.reply_text("❌ Invalid format. Use `/get_reed 1d`, `/get_reed 2h`, etc.")
                return

            code = 'REDEEM-' + str(len(list(redeem_db.find())) + 1)
            redeem_db.insert_one({'code': code, 'expiry': expiry_time, 'used': False})
            await message.reply_text(f"✅ Redeem Code Generated: <b>{code}</b> (Expires on {expiry_time})", parse_mode='HTML')
        else:
            await message.reply_text("❌ Usage: `/get_reed 1d` for 1 day, `/get_reed 2h` for 2 hours, etc.")
    else:
        await message.reply_text("❌ You are not authorized.")

@app.on_message(filters.command("redeem"))
async def redeem_code(client: Client, message: Message):
    user_id = message.from_user.id
    user_data = users_db.find_one({"user_id": user_id})

    if user_data and user_data.get('redeemed', False):
        await message.reply_text("✅ You've already redeemed a code.")
        return

    if len(message.command) != 2:
        await message.reply_text("❌ Usage: `/redeem <code>`")
        return

    code = message.command[1]
    redeem_data = redeem_db.find_one({'code': code})

    if redeem_data and not redeem_data['used']:
        if datetime.now() < redeem_data['expiry']:
            users_db.update_one({"user_id": user_id}, {"$set": {"redeemed": True}})
            redeem_db.update_one({'code': code}, {"$set": {'used': True}})
            await message.reply_text("✅ Redeem code successful! You can now watch more videos.")
        else:
            await message.reply_text("❌ This redeem code has expired.")
    else:
        await message.reply_text("❌ Invalid or already used redeem code.")

@app.on_message(filters.command("add"))
async def add_video(client: Client, message: Message):
    if message.from_user.id in ADMINS:
        await message.reply_text("📥 Please send the video you want to add.")
        app.set_user_data(message.from_user.id, adding_video=True)  # Set user data for video addition
    else:
        await message.reply_text("❌ You are not authorized to perform this action.")

@app.on_message(filters.video)
async def handle_video(client: Client, message: Message):
    if app.get_user_data(message.from_user.id).get('adding_video', False):
        video_file_id = message.video.file_id
        video_index = videos_db.count_documents({}) + 1
        videos_db.insert_one({"index": video_index, "video_file_id": video_file_id})
        logger.info(f"Added video {video_index} with file_id: {video_file_id}")
        await message.reply_text(f"✅ Video {video_index} added successfully.")
        app.set_user_data(message.from_user.id, adding_video=False)  # Reset the flag

        # Schedule video deletion after 5 minutes
        await asyncio.sleep(300)  # 5 minutes
        videos_db.delete_one({"index": video_index})
        logger.info(f"Deleted video {video_index} after 5 minutes.")
    else:
        await message.reply_text("❌ Please use the /add command to upload a video.")

@app.on_message(filters.command("cmd"))
async def cmd_handler(client: Client, message: Message):
    commands = """
    🛠️ <b>Available Commands:</b>
    /start - Start the bot
    /cmd - Show this help message
    /get_reed <time_period> - Admin: Generate redeem code (e.g., 1d, 2h, 30m)
    /redeem <code> - Redeem a code
    /add - Admin: Upload a video to add to the database
    """
    await message.reply_text(commands, parse_mode='HTML')

@app.on_callback_query(filters.regex('get_videos'))
async def get_videos(client: Client, query: CallbackQuery):
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

@app.on_callback_query(filters.regex('next_video'))
async def button_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    user_data = users_db.find_one({"user_id": user_id})

    if user_data['redeemed'] or user_data['next_command_count'] < 10:
        users_db.update_one({"user_id": user_id}, {"$inc": {"next_command_count": 1, "video_index": 1}})
    else:
        await query.message.reply_text("🚫 You've reached the maximum number of next commands allowed. Contact admin for a redeem code.")
        return

    # Get the next video
    video_index = user_data['video_index'] + 1
    video_data = videos_db.find_one({'index': video_index})

    if video_data:
        video_file_id = video_data['video_file_id']
        next_button = InlineKeyboardButton("➡️ Next", callback_data='next_video')
        keyboard = [[next_button]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_video(video=video_file_id, reply_markup=reply_markup)
        users_db.update_one({"user_id": user_id}, {"$set": {"video_index": video_index}})
    else:
        await query.message.reply_text("❌ No more videos available.")

if __name__ == "__main__":
    # Run the bot on port 8000, if needed
    app.run(port=8000)
