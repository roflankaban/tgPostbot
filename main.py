import os
import random
import asyncio
import json
import logging
import re
import aiofiles
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from PIL import Image
from token_api import TOKEN_API
from pathlib import Path
from aiogram.types import CallbackQuery
import io
import uuid

script_dir = Path(__file__).resolve().parent

# === Constants ===
CHANNEL_ID = -1003211451604 
CHANNEL_LINK = "https://t.me/+swZx0VHxpgFlZDQ0"
ADMIN_IDS = [327220107] # <-- ДОДАЙТЕ ЦЕЙ РЯДОК (з вашими ID)

BOLD_START = "<b>"
BOLD_END = "</b>"

# Initialize bot and dispatcher
bot = Bot(token=TOKEN_API)
dp = Dispatcher()

# Configure logging to file and console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    logging.FileHandler("bot.log"),
    logging.StreamHandler()
])
logger = logging.getLogger(__name__)

current_directory = os.getcwd()
logger.info(f"PostBot started: {current_directory} you can send all types of content")

caption = f"<a href='{CHANNEL_LINK}'>⛔️ AntiHentai 🚫</a>"
big_file_caption = f"<a href='{CHANNEL_LINK}'>HI-RES ⛔️ AntiHentai 🚫</a>"

# Define base paths for different file types
base_drive_path = script_dir.parent.parent
script_dir = Path(__file__).resolve().parent
paths = {
    "art": base_drive_path / "Images",
    "gif": base_drive_path / "Gifs",
    "video": base_drive_path / "Video",
    "real": base_drive_path / "Real",
    "p": base_drive_path / "sheesh" / "Unpacked" / "photo",
    "v": base_drive_path / "sheesh" / "Unpacked" / "video"
}

# Ensure all paths exist
for path in paths.values():
    os.makedirs(path, exist_ok=True)

# Paths to JSON files that store already sent files
sent_files_paths = {
    "gif": "sent_gifs.json",
    "video": "sent_videos.json",
    "art": "sent_arts.json",
    "real": "sent_real.json",
    "p": "sent_P.json",
    "v": "sent_V.json"
}

# Allowed extensions for each file type
ALLOWED_EXTENSIONS = {
    "art": {".jpg", ".jpeg", ".png", ".webp"},
    "gif": {".gif"},
    "video": {".mp4", ".mov", ".avi", ".mkv"},
    "real": {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".avi", ".mkv"},
    "p": {".jpg", ".jpeg", ".png", ".webp"},
    "v": {".mp4", ".mov", ".avi", ".mkv"}
}

# Async utility functions for loading and saving sent files
async def load_sent_files_async(file_path):
    if os.path.exists(file_path):
        try:
            async with aiofiles.open(file_path, "r") as file:
                content = await file.read()
                return set(json.loads(content))
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return set()
    return set()

async def save_sent_files_async(file_path, sent_files):
    try:
        async with aiofiles.open(file_path, "w") as file:
            await file.write(json.dumps(list(sent_files)))
    except Exception as e:
        logger.error(f"Error saving {file_path}: {e}")

# Check if a user is subscribed to a channel with a specific status
async def check_subscription(user_id: int, channel_id: int, status) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in status
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return False

# Build admin keyboard with available functions
def get_admin_keyboard():
    keyboard_builder = ReplyKeyboardBuilder()
    keyboard_builder.button(text='Art')
    keyboard_builder.button(text='Gif')
    keyboard_builder.button(text='Video')
    keyboard_builder.button(text='Real')
    keyboard_builder.button(text='P')
    keyboard_builder.button(text='V')
    keyboard_builder.adjust(3, 4) 
    return keyboard_builder.as_markup(resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="Choose a function")

# Build member keyboard (currently with a placeholder button)
def get_member_keyboard():
    keyboard_builder = ReplyKeyboardBuilder()
    keyboard_builder.button(text='This button is not doing anything yet')
    keyboard_builder.adjust(1)
    return keyboard_builder.as_markup(resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="Choose a function")

# Inline keyboard for moderation
def get_approve_keyboard(pending_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅", callback_data=f"approve:{pending_id}")
    builder.button(text="❌", callback_data=f"reject:{pending_id}")
    builder.adjust(2)
    return builder.as_markup()

# Dictionary to store pending photos for moderation
pending_photos = {}

# Handler for /start command
@dp.message(F.text == "/start")
async def get_start(message: types.Message):
    user_id = message.from_user.id
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        reply_text = f'Hi! {message.from_user.first_name}. You are an admin, so you know what you are doing, right?'
        await message.answer(reply_text, reply_markup=get_admin_keyboard())
    else:
        await message.reply(
            "❌ Only administrators can use this bot ❌",
            parse_mode='HTML'
        )

# Handlers for admin keyboard buttons to send random files
@dp.message(F.text.in_(["Gif", "Art", "Real", "Video", "P", "V"]))
async def admin_only_send(message: types.Message):
    user_id = message.from_user.id
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        file_type = message.text.lower()
        await send_random_file(message, file_type)
    else:
        await message.reply("❌ Only administrators can use this bot. ❌", parse_mode='HTML')

# URL validation function
def is_valid_url(url: str) -> bool:
    # Simple URL validation
    pattern = re.compile(
        r'^(https?://)'
        r'([A-Za-z0-9\.-]+)\.([A-Za-z]{2,6})'
        r'(/[A-Za-z0-9\._~:/?#\[\]@!$&\'()*+,;=%-]*)?$'
    )
    return bool(pattern.match(url))

# Handler for messages containing links
@dp.message(F.text.contains('https://') | F.text.contains('http://'))
async def send_link(message: types.Message) -> None:
    user_id = message.from_user.id
    if not await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        await message.reply("❌ Only administrators can use this bot. ❌", parse_mode='HTML')
        return
    url = message.text.strip()
    if not is_valid_url(url):
        await message.reply("Invalid URL format.")
        return
    try:
        await bot.send_photo(chat_id=CHANNEL_ID, photo=url, caption=caption, parse_mode=ParseMode.HTML)
        logger.info('File sent from URL')
    except Exception as e:
        logger.error(f"Failed to send photo from URL: {e}")
        await message.reply("Failed to send image from the provided link. Make sure it's a direct link to an image.")

# Lock to prevent concurrent resend operations
resend_lock = asyncio.Lock()

# Handler for resending media (video or animation) to the group
@dp.message(F.video | F.animation)
async def resend(message: types.Message):
    user_id = message.from_user.id
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        async with resend_lock:
            try:
                if message.photo:
                    await bot.send_photo(chat_id=CHANNEL_ID, photo=message.photo[-1].file_id, caption=caption, parse_mode=ParseMode.HTML)
                    logger.info('Photo resent')
                elif message.video:
                    await bot.send_video(chat_id=CHANNEL_ID, video=message.video.file_id, caption=caption, parse_mode=ParseMode.HTML)
                    logger.info('Video resent')
                elif message.animation:
                    await bot.send_animation(chat_id=CHANNEL_ID, animation=message.animation.file_id, caption=caption, parse_mode=ParseMode.HTML)
                    logger.info('Animation resent')
                else:
                    await message.reply("Unsupported or missing media file.")
            except Exception as e:
                logger.error(f"Error in resend function: {e}")
                await message.reply("An error occurred while resending the media.")
    else:
        await message.reply("❌ Only administrators can use this bot. ❌", parse_mode='HTML')

# When a non-admin sends a photo:
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        # Admin: post directly
        await resend(message)
    else:
        # Non-admin: send for moderation
        photo_file_id = message.photo[-1].file_id
        short_id = uuid.uuid4().hex[:16]
        pending_photos[short_id] = {
            "user_id": user_id,
            "file_id": photo_file_id,
            "timestamp": datetime.now().isoformat(),
            "type": "photo"
        }
        for admin_id in ADMIN_IDS:
            await bot.send_photo(
                chat_id=admin_id,
                photo=photo_file_id,
                caption=f"Moderation request (photo) from {user_id}",
                reply_markup=get_approve_keyboard(short_id)
            )
        await message.reply("Your photo has been sent for moderation.")

# When a non-admin sends a video:
@dp.message(F.video)
async def handle_video(message: types.Message):
    user_id = message.from_user.id
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        await resend(message)
    else:
        video_file_id = message.video.file_id
        short_id = uuid.uuid4().hex[:16]
        pending_photos[short_id] = {
            "user_id": user_id,
            "file_id": video_file_id,
            "timestamp": datetime.now().isoformat(),
            "type": "video"
        }
        for admin_id in ADMIN_IDS:
            await bot.send_video(
                chat_id=admin_id,
                video=video_file_id,
                caption=f"Moderation request (video) from {user_id}",
                reply_markup=get_approve_keyboard(short_id)
            )
        await message.reply("Your video has been sent for moderation.")

# When a non-admin sends a link:
@dp.message(F.text.contains('https://') | F.text.contains('http://'))
async def handle_link(message: types.Message):
    user_id = message.from_user.id
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        await send_link(message)
    else:
        url = message.text.strip()
        if not is_valid_url(url):
            await message.reply("Invalid URL format.")
            return
        short_id = uuid.uuid4().hex[:16]
        pending_photos[short_id] = {
            "user_id": user_id,
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "type": "link"
        }
        for admin_id in ADMIN_IDS:
            await bot.send_message(
                chat_id=admin_id,
                text=f"Moderation request (link) from {user_id}: {url}",
                reply_markup=get_approve_keyboard(short_id)
            )
        await message.reply("Your link has been sent for moderation.")

# When a non-admin sends a text message (not a link)
@dp.message(F.text & ~F.text.contains('https://') & ~F.text.contains('http://'))
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        # Admin: send directly to channel
        await bot.send_message(chat_id=CHANNEL_ID, text=message.text)
        logger.info(f"Text message from admin {user_id} sent to channel.")
    else:
        # Non-admin: send for moderation
        short_id = uuid.uuid4().hex[:16]
        pending_photos[short_id] = {
            "user_id": user_id,
            "text": message.text,
            "timestamp": datetime.now().isoformat(),
            "type": "text"
        }
        for admin_id in ADMIN_IDS:
            await bot.send_message(
                chat_id=admin_id,
                text=f"Moderation request (text) from {user_id}: {message.text}",
                reply_markup=get_approve_keyboard(short_id)
            )
        await message.reply("Your message has been sent for moderation.")

# Approve handler (universal for photo, video, link)
@dp.callback_query(F.data.startswith("approve:"))
async def approve_photo(callback: CallbackQuery):
    _, pending_id = callback.data.split(":")
    info = pending_photos.pop(pending_id, None)
    if info:
        if info.get("type") == "photo":
            await bot.send_photo(chat_id=CHANNEL_ID, photo=info["file_id"], caption=caption, parse_mode=ParseMode.HTML)
        elif info.get("type") == "video":
            await bot.send_video(chat_id=CHANNEL_ID, video=info["file_id"], caption=caption, parse_mode=ParseMode.HTML)
        elif info.get("type") == "link":
            await bot.send_photo(chat_id=CHANNEL_ID, photo=info["url"], caption=caption, parse_mode=ParseMode.HTML)
        elif info.get("type") == "text":
            await bot.send_message(chat_id=CHANNEL_ID, text=info["text"])
        await callback.message.edit_caption("✅ Published", reply_markup=None)
        await callback.answer("Published")
        await bot.send_message(info["user_id"], "Your content was approved and published.")
        logger.info(f"Content {info.get('file_id', info.get('url', info.get('text')))} from user {info['user_id']} approved by admin {callback.from_user.id}")
    else:
        await callback.answer("Content not found", show_alert=True)

# Reject handler
@dp.callback_query(F.data.startswith("reject:"))
async def reject_photo(callback: CallbackQuery):
    _, pending_id = callback.data.split(":")
    info = pending_photos.pop(pending_id, None)
    await callback.message.delete()
    await callback.answer("Photo rejected and deleted")
    if info:
        await bot.send_message(info["user_id"], "Your photo was rejected.")
        logger.info(f"Photo {info['file_id']} from user {info['user_id']} rejected by admin {callback.from_user.id}")

# Resize image and return BytesIO object
def resize_image(image_path):
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            max_dimension = 2560
            if max(img.width, img.height) > max_dimension:
                ratio = max_dimension / max(img.width, img.height)
                new_width = int(img.width * ratio)
                new_height = int(img.height * ratio)
                img = img.resize((new_width, new_height), Image.LANCZOS)
            img_bytes = io.BytesIO()
            img.save(img_bytes, format="JPEG", quality=95)
            img_bytes.seek(0)
            logger.warning(f'File {image_path} resized in memory')
            return img_bytes
    except Exception as e:
        logger.error(f"Error resizing image: {e}")
        return None

# Validate file based on size and existence
def is_valid_file(file_path: str, max_size_mb: int = 50) -> bool:
    if not os.path.isfile(file_path):
        return False
    if os.path.getsize(file_path) == 0:
        return False
    if os.path.getsize(file_path) > max_size_mb * 1024 * 1024:
        return False
    return True

# Check if a file has a valid extension
def has_valid_extension(filename: str, allowed_exts: set) -> bool:
    return any(filename.lower().endswith(ext) for ext in allowed_exts)

# Send a random file of the specified type to the group, with optional interval scheduling
async def send_random_file(message: types.Message, file_type: str, interval_range=(12, 24)) -> None:
    user_id = message.from_user.id
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        path = paths[file_type]
        sent_files = await load_sent_files_async(sent_files_paths[file_type])
        allowed_exts = ALLOWED_EXTENSIONS.get(file_type, set())
        files = [
            f for f in os.listdir(path)
            if is_valid_file(os.path.join(path, f)) and has_valid_extension(f, allowed_exts)
        ]
        available_files = [f for f in files if f not in sent_files]

        if available_files:
            random_file = random.choice(available_files)
            file_path = os.path.join(path, random_file)
            file_size = os.path.getsize(file_path)
            file_info = f"{file_path} {BOLD_START}{(file_size / (1024 * 1024)):.2f}MB{BOLD_END}"
            logger.info(file_info)
            await message.answer(file_info, parse_mode=ParseMode.HTML)
            # Send the file according to its type
            if file_type == 'art':
                img_bytes = resize_image(file_path)
                if img_bytes:
                    input_file = types.BufferedInputFile(img_bytes.getvalue(), filename="image.jpg")
                    await bot.send_photo(chat_id=CHANNEL_ID, photo=input_file, caption=caption, parse_mode=ParseMode.HTML)
                else:
                    await message.reply("Error resizing image.")
            elif file_type == 'gif':
                await bot.send_animation(chat_id=CHANNEL_ID, animation=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)
            elif file_type == 'video':
                await bot.send_video(chat_id=CHANNEL_ID, video=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)
            elif file_type in ['real', 'p']:
                if file_size > 10 * 1024 * 1024:
                    img_bytes = resize_image(file_path)
                    if img_bytes:
                        await message.answer_photo(photo=img_bytes, caption=caption, parse_mode=ParseMode.HTML)
                    else:
                        await message.reply("Error resizing image.")
                else:
                    await message.answer_photo(photo=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)
            elif file_type == 'v':
                await message.answer_video(video=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)

            sent_files.add(random_file)
            await save_sent_files_async(sent_files_paths[file_type], sent_files)
        else:
            await message.reply("No files under 50MB available to send.")

        # Do not schedule periodic posts for 'real', 'p', or 'v'
        if interval_range != (0, 0) and file_type not in ['real', 'p', 'v']:
            interval = random.randrange(*interval_range) * random.randrange(3300, 3900)
            next_post_time = datetime.now() + timedelta(seconds=interval)
            next_post_msg = f"Next {BOLD_START} {file_type} {BOLD_END} post scheduled at: {BOLD_START} {next_post_time.strftime('%d-%m-%Y %H:%M')} {BOLD_END}"
            logger.info(next_post_msg)
            await message.answer(next_post_msg, parse_mode=ParseMode.HTML)
            asyncio.create_task(scheduled_post(file_type, interval, message))
    else:
        await message.reply(
            f"❌ Only administrators can use this bot ❌",
            parse_mode='HTML'
        )

# For scheduled posting, use a background task
async def scheduled_post(file_type, interval, message):
    await asyncio.sleep(interval)
    await send_random_file(message, file_type, interval_range=(0, 0))

# Main entry point for the bot
async def main() -> None:
    logger.info("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
