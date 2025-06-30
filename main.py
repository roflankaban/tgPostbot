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

script_dir = Path(__file__).resolve().parent

# === Constants ===
CHANNEL_ID = -1002416443178  # Main channel ID for posting and checking subscriptions
CHANNEL_LINK = "https://t.me/+7DpKVQBjwCRjNzdk"  # Main channel invite link

BOLD_START = "<b>"
BOLD_END = "</b>"

# List of administrator IDs (fill in your own)
ADMIN_IDS = [327220107]  # <-- Specify your IDs here

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

caption = f"<a href='{CHANNEL_LINK}'>💙AntiHentai💛</a>"
big_file_caption = f"<a href='{CHANNEL_LINK}'>HI-RES 💙AntiHentai💛</a>"

# Define base paths for different file types
base_drive_path = script_dir.parent.parent
script_dir = Path(__file__).resolve().parent
paths = {
    "art": base_drive_path / "Images",
    "gif": base_drive_path / "Gifs",
    "video": base_drive_path / "Video",
    "real": base_drive_path / "Real",
    "P": base_drive_path / "sheesh" / "Unpacked" / "photo",
    "V": base_drive_path / "sheesh" / "Unpacked" / "video"
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
    "P": "sent_P.json",
    "V": "sent_V.json"
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
    keyboard_builder.adjust(4, 3)
    return keyboard_builder.as_markup(resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="Choose a function")

# Build member keyboard (currently with a placeholder button)
def get_member_keyboard():
    keyboard_builder = ReplyKeyboardBuilder()
    keyboard_builder.button(text='This button is not doing anything yet')
    keyboard_builder.adjust(1)
    return keyboard_builder.as_markup(resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="Choose a function")

# Dictionary to store pending photos for moderation
pending_photos = {}

# Build inline keyboard for approving or rejecting a photo
def get_approve_keyboard(message_id, user_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅", callback_data=f"approve:{message_id}:{user_id}")
    builder.button(text="❌", callback_data=f"reject:{message_id}:{user_id}")
    builder.adjust(2)
    return builder.as_markup()

# Handler for /start command
@dp.message(F.text == "/start")
async def get_start(message: types.Message):
    user_id = message.from_user.id
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        reply_text = f'Hi! {message.from_user.first_name}. You are an admin, so you know what you are doing, right?'
        await message.answer(reply_text, reply_markup=get_admin_keyboard())
    elif await check_subscription(user_id, CHANNEL_ID, ['member']):
        reply_text = f'Hi! {message.from_user.first_name}. You can suggest your image by sending it to this bot!'
        await message.answer(reply_text, reply_markup=get_member_keyboard())
    else:
        await message.reply(
            f"❌You are not subscribed to <a href='{CHANNEL_LINK}'>💙AntiHentai💛</a>!❌",
            parse_mode='HTML'
        )

# Handlers for admin keyboard buttons to send random files
@dp.message(F.text == "Gif")
async def send_random_gif(message: types.Message):
    await send_random_file(message, 'gif', interval_range=(4, 24))

@dp.message(F.text == "Art")
async def send_random_art(message: types.Message):
    await send_random_file(message, 'art', interval_range=(1, 3))

@dp.message(F.text == "Real")
async def send_random_real(message: types.Message):
    await send_random_file(message, 'real', interval_range=(4, 24))

@dp.message(F.text == "Video")
async def send_random_video(message: types.Message):
    await send_random_file(message, 'video', interval_range=(4, 24))

@dp.message(F.text == "P")
async def send_random_P(message: types.Message):
    await send_random_file(message, 'P', interval_range=(0, 0))

@dp.message(F.text == "V")
async def send_random_V(message: types.Message):
    await send_random_file(message, 'V', interval_range=(0, 0))

# URL validation function
def is_valid_url(url: str) -> bool:
    # Simple URL validation
    pattern = re.compile(
        r'^(https?://)'
        r'([A-Za-z0-9\.-]+)\.([A-Za-z]{2,6})'
        r'(/[A-Za-z0-9\._~:/?#\[\]@!$&\'()*+,;=%-]*)?$'
    )
    return bool(pattern.match(url))

# Handler for messages containing links, sends the link as a photo to the group
@dp.message(F.text.contains('https://') | F.text.contains('http://'))
async def send_link(message: types.Message) -> None:
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
                    await asyncio.sleep(1 * 60 * 30)
                elif message.video:
                    await bot.send_video(chat_id=CHANNEL_ID, video=message.video.file_id, caption=caption, parse_mode=ParseMode.HTML)
                    logger.info('Video resent')
                    await asyncio.sleep(1 * 60 * 30)
                elif message.animation:
                    await bot.send_animation(chat_id=CHANNEL_ID, animation=message.animation.file_id, caption=caption, parse_mode=ParseMode.HTML)
                    logger.info('Animation resent')
                    await asyncio.sleep(1 * 60 * 30)
                else:
                    await message.reply("Unsupported or missing media file.")
            except Exception as e:
                logger.error(f"Error in resend function: {e}")
                await message.reply("An error occurred while resending the media.")
    else:
        await message.reply("You don't have permission to send media.")

# Handler for photo messages
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"User {user_id} sent a photo at {datetime.now()}")
    if not message.photo or not hasattr(message.photo[-1], 'file_id'):
        await message.reply("No valid photo found in your message.")
        return
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        # Admin — send directly to the group
        await resend(message)
    else:
        # User — send photo for moderation to all admins
        photo_file_id = message.photo[-1].file_id
        for admin_id in ADMIN_IDS:
            sent_msg = await bot.send_photo(
                chat_id=admin_id,
                photo=photo_file_id,
                caption=f"New publication request from {user_id}"
            )
            # Add inline keyboard for approval/rejection after sending the photo
            await sent_msg.edit_reply_markup(
                reply_markup=get_approve_keyboard(sent_msg.message_id, user_id)
            )
            # Store the pending photo with the message ID as key
            pending_photos[sent_msg.message_id] = photo_file_id
        await message.reply("Your photo has been sent for moderation.")

# Handler for approval callback from inline keyboard
@dp.callback_query(F.data.startswith("approve:"))
async def approve_photo(callback: CallbackQuery):
    _, message_id, user_id = callback.data.split(":")
    logger.info(f"Admin {callback.from_user.id} approved photo from user {user_id} at {datetime.now()}")
    photo_file_id = pending_photos.pop(int(message_id), None)
    if photo_file_id:
        await bot.send_photo(chat_id=CHANNEL_ID, photo=photo_file_id, caption=caption, parse_mode=ParseMode.HTML)
        await callback.message.edit_caption("✅ Photo published", reply_markup=None)
        await callback.answer("Photo published")
    else:
        await callback.answer("Photo not found", show_alert=True)

# Handler for rejection callback from inline keyboard
@dp.callback_query(F.data.startswith("reject:"))
async def reject_photo(callback: CallbackQuery):
    _, message_id, user_id = callback.data.split(":")
    logger.info(f"Admin {callback.from_user.id} rejected photo from user {user_id} at {datetime.now()}")
    pending_photos.pop(int(message_id), None)
    await callback.message.delete()
    await callback.answer("Photo rejected and deleted")

# Resize image if it exceeds Telegram's size limits
def resize_image(image_path):
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            # Check if image dimensions exceed Telegram's limits
            max_dimension = 2560
            if max(img.width, img.height) > max_dimension:
                ratio = max_dimension / max(img.width, img.height)
                new_width = int(img.width * ratio)
                new_height = int(img.height * ratio)
                img = img.resize((new_width, new_height), Image.LANCZOS)
            temp_path = os.path.join(os.path.dirname(image_path), "temp.jpg")
            img.save(temp_path, format="JPEG", quality=95)
            logger.warning(f'File {image_path} resized')
            return temp_path
    except Exception as e:
        logger.error(f"Error resizing image: {e}")
        return image_path

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
        files = [f for f in os.listdir(path) if is_valid_file(os.path.join(path, f))]
        available_files = [f for f in files if f not in sent_files]

        while True:
            if available_files:
                random_file = random.choice(available_files)
                file_path = os.path.join(path, random_file)
                file_size = os.path.getsize(file_path)
                file_info = f"{file_path} {BOLD_START}{(file_size / (1024 * 1024)):.2f}MB{BOLD_END}"
                logger.info(file_info)
                await message.answer(file_info, parse_mode=ParseMode.HTML)
                # Send the file according to its type
                if file_type in ['art']:
                    resized_path = resize_image(file_path)
                    await bot.send_photo(chat_id=CHANNEL_ID, photo=types.FSInputFile(resized_path), caption=caption, parse_mode=ParseMode.HTML)
                elif file_type == 'gif':
                    await bot.send_animation(chat_id=CHANNEL_ID, animation=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)
                elif file_type in ['video']:
                    await bot.send_video(chat_id=CHANNEL_ID, video=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)
                elif file_type in ['real', 'P']:
                    if file_size > 10 * 1024 * 1024:
                        file_path = resize_image(file_path)
                    await message.answer_photo(photo=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)
                elif file_type in ['V']:
                    await message.answer_video(video=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)

                sent_files.add(random_file)
                await save_sent_files_async(sent_files_paths[file_type], sent_files)
            else:
                await message.reply("No files under 50MB available to send.")
            # If interval_range is (0, 0), send only once
            if interval_range == (0, 0):
                break
            else:
                interval = random.randrange(*interval_range) * random.randrange(3300, 3900)
                next_post_time = datetime.now() + timedelta(seconds=interval)
                next_post_msg = f"Next {BOLD_START} {file_type} {BOLD_END} post scheduled at: {BOLD_START} {next_post_time.strftime('%d-%m-%Y %H:%M')} {BOLD_END}"
                logger.info(next_post_msg)
                await message.answer(next_post_msg, parse_mode=ParseMode.HTML)
                await asyncio.sleep(interval)
    else:
        await message.reply(
            f"❌You are not subscribed to <a href='{CHANNEL_LINK}'>💙AntiHentai💛</a>!❌",
            parse_mode='HTML'
        )

# Main entry point for the bot
async def main() -> None:
    logger.info("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
