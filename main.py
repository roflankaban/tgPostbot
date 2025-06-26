import os
import random
import asyncio
import json
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from PIL import Image
from token_api import TOKEN_API
from pathlib import Path

script_dir = Path(__file__).resolve().parent

BOLD_START = "<b>"
BOLD_END = "</b>"

# Initialize bot and dispatcher
bot = Bot(token=TOKEN_API)
dp = Dispatcher()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    logging.FileHandler("bot.log"),
    logging.StreamHandler()
])
logger = logging.getLogger(__name__)

# Constants
current_directory = os.getcwd()
logger.info(f"PostBot started: {current_directory} you can send all types of content")

caption = "<a href='https://t.me/+FuSlw2SpmwBmNmI0'>💙AntiHentai💛</a>"
big_file_caption = "<a href='https://t.me/+FuSlw2SpmwBmNmI0'>HI-RES 💙AntiHentai💛</a>"

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

sent_files_paths = {
    "gif": "sent_gifs.json",
    "video": "sent_videos.json",
    "art": "sent_arts.json",
    "real": "sent_real.json",
    "P": "sent_P.json",
    "V": "sent_V.json"
}

# Utility functions
def load_sent_files(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            return set(json.load(file))
    return set()

def save_sent_files(file_path, sent_files):
    with open(file_path, "w") as file:
        json.dump(list(sent_files), file)

# Load sent files sets or initialize empty sets if files don't exist
sent_gifs = load_sent_files(sent_files_paths["gif"])
sent_arts = load_sent_files(sent_files_paths["art"])
sent_videos = load_sent_files(sent_files_paths["video"])
sent_real = load_sent_files(sent_files_paths["real"])
sent_P = load_sent_files(sent_files_paths["P"])
sent_V = load_sent_files(sent_files_paths["V"])

async def check_subscription(user_id: int, channel_id: int, status) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in status
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return False

async def get_start(message: types.Message):
    user_id = message.from_user.id
    if await check_subscription(user_id, -1002416443178, ['administrator', 'creator']):
        reply_text = f'Hi! {message.from_user.first_name}. You are an admin, so you know what you are doing, right?'
        await message.answer(reply_text, reply_markup=get_admin_keyboard())
    elif await check_subscription(user_id, -1002416443178, ['member']):
        reply_text = f'Hi! {message.from_user.first_name}. Do you want to see something special?'
        await message.answer(reply_text, reply_markup=get_member_keyboard())
    else:
        await message.reply(
    "❌You are not subscribed to <a href='https://t.me/+FuSlw2SpmwBmNmI0'>💙AntiHentai💛</a>!❌",
    parse_mode='HTML'
)

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


async def send_link(message: types.Message) -> None:
    url = message.text
    await bot.send_photo(chat_id=-1002416443178, photo=url, caption=caption, parse_mode=ParseMode.HTML)
    logger.info('File sent from URL')

resend_lock = asyncio.Lock()

async def resend(message: types.Message) -> None:
    user_id = message.from_user.id
    if await check_subscription(user_id, -1002416443178, ['administrator', 'creator']):
        async with resend_lock:
            try:
                if message.photo:
                    await bot.send_photo(chat_id=-1002416443178, photo=message.photo[-1].file_id, caption=caption, parse_mode=ParseMode.HTML)
                    logger.info('Photo resent')
                    await asyncio.sleep(1 * 60 * 30)

                elif message.video:
                    await bot.send_video(chat_id=-1002416443178, video=message.video.file_id, caption=caption, parse_mode=ParseMode.HTML)
                    logger.info('Video resent')
                    await asyncio.sleep(1 * 60 * 30)

                elif message.animation:
                    await bot.send_animation(chat_id=-1002416443178, animation=message.animation.file_id, caption=caption, parse_mode=ParseMode.HTML)
                    logger.info('Animation resent')
                    await asyncio.sleep(1 * 60 * 30)
                else:
                    await message.reply("Unsupported file")
            except Exception as e:
                logger.error(f"Error in resend function: {e}")
    else:
        await message.reply("You don't have permission to send media.")

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

async def send_random_file(message: types.Message, file_type: str, interval_range=(12, 24)) -> None:
    user_id = message.from_user.id
    if await check_subscription(user_id, -1002416443178, ['administrator', 'creator']):
        path = paths[file_type]
        sent_files = load_sent_files(sent_files_paths[file_type])
        files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
        available_files = [f for f in files if f not in sent_files and os.path.getsize(os.path.join(path, f)) < 50 * 1024 * 1024]

        while True:
            if available_files:
                random_file = random.choice(available_files)
                file_path = os.path.join(path, random_file)
                file_size = os.path.getsize(file_path)
                file_info = f"{file_path} {BOLD_START}{(file_size / (1024 * 1024)):.2f}MB{BOLD_END}"
                logger.info(file_info)
                await message.answer(file_info, parse_mode=ParseMode.HTML)
                if file_type in ['art']:
                  
                    resized_path = resize_image(file_path)
                    await bot.send_photo(chat_id=-1002416443178, photo=types.FSInputFile(resized_path), caption=caption, parse_mode=ParseMode.HTML)

                elif file_type == 'gif':
                    await bot.send_animation(chat_id=-1002416443178, animation=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)
                elif file_type in ['video']:
                    await bot.send_video(chat_id=-1002416443178, video=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)
                elif file_type in ['real','P']:
                    if file_size > 10 * 1024 * 1024:
                        file_path = resize_image(file_path)
                    await message.answer_photo(photo=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)
                elif file_type in ['V']:
                    await message.answer_video(video=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)

                sent_files.add(random_file)
                save_sent_files(sent_files_paths[file_type], sent_files)
            else:
                await message.reply("No files under 50MB available to send.")
                
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
    "❌You are not subscribed to <a href='https://t.me/+FuSlw2SpmwBmNmI0'>💙AntiHentai💛</a>!❌",
    parse_mode='HTML'
)

# Handlers for different types of files
async def send_random_art(message: types.Message) -> None:
    await send_random_file(message, 'art', interval_range=(1, 3))

async def send_random_gif(message: types.Message) -> None:
    await send_random_file(message, 'gif', interval_range=(4, 24))

async def send_random_video(message: types.Message) -> None:
    await send_random_file(message, 'video', interval_range=(4, 24))

async def send_random_real(message: types.Message) -> None:
    await send_random_file(message, 'real', interval_range=(4, 24))

async def send_random_P(message: types.Message) -> None:
    await send_random_file(message, 'P', interval_range=(0, 0))
    
async def send_random_V(message: types.Message) -> None:
    await send_random_file(message, 'V', interval_range=(0, 0))

# Main function to register handlers and start polling
async def main() -> None:
    dp.message.register(get_start, F.text == "/start")
    dp.message.register(send_random_gif, F.text == "Gif")
    dp.message.register(send_random_art, F.text == "Art")
    dp.message.register(send_random_real, F.text == "Real")
    dp.message.register(send_random_video, F.text == "Video")
    dp.message.register(send_random_P, F.text == "P")
    dp.message.register(send_random_V, F.text == "V")
    dp.message.register(send_link, F.text.contains('https://') | F.text.contains('http://'))
    dp.message.register(resend, F.photo | F.video | F.animation)
    logger.info("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
