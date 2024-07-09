import os
import random
import asyncio
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from token_api import TOKEN_API

current_directory = os.getcwd()
print("PostBot запущено, поточна директорія:", current_directory, " можна надсилати боту контент як у форматі телеграму так і посиланням на медіа контент")

# Initialize your bot
bot = Bot(token=TOKEN_API)
dp = Dispatcher()

caption = "<a href='https://t.me/AnitiHentai'>💙AntiHentai💛</a>"
big_file_caption = "<a href='https://t.me/AnitiHentai'>HI-RES 💙AntiHentai💛</a>"

art_path = r"F:\Images"
gif_path = r"F:\Gif"
video_path = r"F:\Video"
real_path = r"F:\OLD SH\Real"
zoo_path = r"F:\OLD SH\zoo"

sent_gifs_file = "sent_gifs.json"
sent_videos_file = "sent_videos.json"
sent_arts_file = "sent_arts.json"
sent_real_file = "sent_real.json"
sent_zoo_file = "sent_zoo.json"

def load_sent_files(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            return set(json.load(file))
    return set()

def save_sent_files(file_path, sent_files):
    with open(file_path, "w") as file:
        json.dump(list(sent_files), file)

sent_gifs = load_sent_files(sent_gifs_file)
sent_arts = load_sent_files(sent_arts_file)
sent_videos = load_sent_files(sent_videos_file)
sent_real = load_sent_files(sent_real_file)
sent_zoo = load_sent_files(sent_zoo_file)

async def check_subscription(user_id: int, channel_id: int, status) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in status
    except Exception as e:
        print(f"Error checking subscription: {e}")
        return False

async def get_start(message: types.Message):
    user_id = message.from_user.id
    if await check_subscription(user_id, -1001169552807, ['administrator', 'creator']):
        reply_text = f'Hi! {message.from_user.first_name}.U are admin so know what ur doing right?'
        await message.answer(reply_text, reply_markup=get_admin_keyboard())
    elif await check_subscription(user_id, -1001169552807, ['member']):
        reply_text = f'Hi! {message.from_user.first_name}. U want to see something special?'
        await message.answer(reply_text, reply_markup=get_member_keyboard())
    else:
        await message.reply("U are not sub! https://t.me/AnitiHentai")

def get_admin_keyboard():
    keyboard_builder = ReplyKeyboardBuilder()
    keyboard_builder.button(text='Art')
    keyboard_builder.button(text='Gif')
    keyboard_builder.button(text='Video')
    keyboard_builder.button(text='Real')
    keyboard_builder.button(text='Zoo')
    keyboard_builder.adjust(3, 2)
    return keyboard_builder.as_markup(resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="Choose a function")

def get_member_keyboard():
    keyboard_builder = ReplyKeyboardBuilder()
    keyboard_builder.button(text='Zoo')
    keyboard_builder.adjust(1)
    return keyboard_builder.as_markup(resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="Choose a function")

async def send_link(message: types.Message) -> None:
    url = message.text
    await bot.send_photo(chat_id=-1001169552807, photo=url, caption=caption, parse_mode=ParseMode.HTML)
    print('File sent from URL')

resend_lock = asyncio.Lock()

async def resend(message: types.Message) -> None:
    async with resend_lock:
        if message.photo:
            await bot.send_photo(chat_id=-1001169552807, photo=message.photo[-1].file_id, caption=caption, parse_mode=ParseMode.HTML)
            print('Photo sent')
            await asyncio.sleep(1 * 60 * 30)

        elif message.video:
            await bot.send_video(chat_id=-1001169552807, video=message.video.file_id, caption=caption, parse_mode=ParseMode.HTML)
            print('Video sent')
            await asyncio.sleep(1 * 60 * 30)

        elif message.animation:
            await bot.send_animation(chat_id=-1001169552807, animation=message.animation.file_id, caption=caption, parse_mode=ParseMode.HTML)
            print('Animation sent')
            await asyncio.sleep(1 * 60 * 30)

        else:
            await message.reply("Unsupported file")

async def send_random_file(message: types.Message, path: str, sent_files: set, send_function, interval: int, sent_files_file: str) -> None:
    user_id = message.from_user.id
    if await check_subscription(user_id, -1001169552807, ['administrator', 'creator']):
        files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
        available_files = [f for f in files if os.path.getsize(os.path.join(path, f)) < 50 * 1024 * 1024]

        if available_files:
            random_file = random.choice(available_files)
            file_path = os.path.join(path, random_file)
            print(file_path)

            file = types.FSInputFile(path=file_path)
            file_size = os.path.getsize(file_path)
            if file_size <= 10*1024*1024:
                if send_function == bot.send_video:
                    await bot.send_video(chat_id=-1001169552807, video=file, caption=caption, parse_mode=ParseMode.HTML)
                    await message.answer_video(video=file, caption=caption, parse_mode=ParseMode.HTML)
                elif send_function == bot.send_photo:
                    await bot.send_photo(chat_id=-1001169552807, photo=file, caption=caption, parse_mode=ParseMode.HTML)
                    await message.answer_photo(photo=file, caption=caption, parse_mode=ParseMode.HTML)
                else:
                    await bot.send_document(chat_id=-1001169552807, document=file, caption=big_file_caption, parse_mode=ParseMode.HTML)
                    await message.answer_document(document=file, caption=big_file_caption, parse_mode=ParseMode.HTML)

            else:
                await bot.send_document(chat_id=-1001169552807, document=file, caption=big_file_caption, parse_mode=ParseMode.HTML)
                await message.answer_document(document=file, caption=big_file_caption, parse_mode=ParseMode.HTML)
        else:
            await message.reply("No files under 50MB available to send.")
    else:
        await message.reply("You are not an admin")

async def send_random_art(message: types.Message) -> None:
    await send_random_file(
        message, art_path, sent_arts,
        lambda file: bot.send_photo(chat_id=-1001169552807, photo=file, caption=caption, parse_mode=ParseMode.HTML),
        4 * 60 * 60, sent_arts_file
    )

async def send_random_gif(message: types.Message) -> None:
    await send_random_file(
        message, gif_path, sent_gifs,
        lambda file: bot.send_animation(chat_id=-1001169552807, animation=file, caption=caption, parse_mode=ParseMode.HTML),
        24 * 60 * 60, sent_gifs_file
    )

async def send_random_video(message: types.Message) -> None:
    await send_random_file(
        message, video_path, sent_videos,
        lambda file: bot.send_video(chat_id=-1001169552807, video=file, caption=caption, parse_mode=ParseMode.HTML),
        24 * 60 * 60, sent_videos_file
    )

async def send_random_real(message: types.Message) -> None:
    user_id = message.from_user.id
    if await check_subscription(user_id, -1001169552807, ['administrator', 'creator']):
        files = [f for f in os.listdir(real_path) if os.path.isfile(os.path.join(real_path, f))]
        available_files = [f for f in files if os.path.getsize(os.path.join(real_path, f)) < 50 * 1024 * 1024]

        if available_files:
            random_file = random.choice(available_files)
            file_path = os.path.join(real_path, random_file)
            print(file_path)

            file = types.FSInputFile(path=file_path)
            file_size = os.path.getsize(file_path)
            if file_size <= 10*1024*1024:
                await message.answer_photo(photo=file, caption=caption, parse_mode=ParseMode.HTML)
            else:
                await message.answer_document(document=file, caption=big_file_caption, parse_mode=ParseMode.HTML)
        else:
            await message.reply("No files under 50MB available to send.")
    else:
        await message.reply("You are not an admin")

async def send_random_zoo(message: types.Message) -> None:
    user_id = message.from_user.id
    if await check_subscription(user_id, -1001169552807, ['administrator', 'creator', 'member']):
        files = [f for f in os.listdir(zoo_path) if os.path.isfile(os.path.join(zoo_path, f))]
        available_files = [f for f in files if os.path.getsize(os.path.join(zoo_path, f)) < 50 * 1024 * 1024]

        if available_files:
            random_file = random.choice(available_files)
            file_path = os.path.join(zoo_path, random_file)
            print(file_path)

            file = types.FSInputFile(path=file_path)
            file_size = os.path.getsize(file_path)
            if file_size <= 10 * 1024 * 1024:
                await message.answer_video(video=file, caption=caption, parse_mode=ParseMode.HTML)
            else:
                await message.answer_document(document=file, caption=big_file_caption, parse_mode=ParseMode.HTML)
        else:
            await message.reply("No files under 50MB available to send.")
    else:
        await message.reply("You are not a member.")

async def main() -> None:
    dp.message.register(get_start, F.text == "/start")
    dp.message.register(send_random_gif, F.text == "Gif")
    dp.message.register(send_random_art, F.text == "Art")
    dp.message.register(send_random_real, F.text == "Real")
    dp.message.register(send_random_video, F.text == "Video")
    dp.message.register(send_random_zoo, F.text == "Zoo")
    dp.message.register(send_link, F.text.contains('https://') | F.text.contains('http://'))
    dp.message.register(resend, F.photo | F.video | F.animation)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
