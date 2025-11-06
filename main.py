"""
AntiHentai Bot
This bot serves two primary functions:
1.  Admin-only: Allows admins to post content from local directories to a
    specific Telegram channel, either as a one-off or on a recurring schedule.
2.  Public: Allows non-admin users to submit content, which is then sent to
    admins for moderation (approve/reject) before being posted to the channel.
"""

import os
import random
import asyncio
import json
import logging
import re
import aiofiles
import io
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Third-party libraries
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import CallbackQuery
from PIL import Image, ImageFile

# Local (developer-created)
# Ensure you have a 'token_api.py' file with TOKEN_API = "your_bot_token"
from token_api import TOKEN_API

# Allow PIL to load truncated/corrupted images
ImageFile.LOAD_TRUNCATED_IMAGES = True

# === 1. Constants & Configuration ===

# Get the directory where this script is running
script_dir = Path(__file__).resolve().parent

# --- Channel & Admin Configuration ---
CHANNEL_ID = -1003211451604
CHANNEL_LINK = "https://t.me/+swZx0VHxpgFlZDQ0"
ADMIN_IDS = [327220107]  # List of admin user IDs for moderation

# --- Bot & Dispatcher Setup ---
bot = Bot(token=TOKEN_API)
dp = Dispatcher()

# --- Logging Configuration ---
# FIX: Use explicit UTF-8 encoding for file and stream to prevent
# UnicodeEncodeError on Windows when logging non-Latin filenames.
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# File Handler (for bot.log)
file_handler = logging.FileHandler("bot.log", encoding='utf-8')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Console/Stream Handler
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
# Try to set stream encoding to utf-8 if possible
try:
    # This works in environments like VSCode debug console
    stream_handler.stream.reconfigure(encoding='utf-8')
except AttributeError:
    # Fallback for standard Windows CMD/PowerShell
    pass
logger.addHandler(stream_handler)


current_directory = os.getcwd()
logger.info(f"PostBot started in: {current_directory}")

# --- Message Formatting ---
BOLD_START = "<b>"
BOLD_END = "</b>"
caption = f"<a href='{CHANNEL_LINK}'>⛔️ AntiHentai 🚫</a>"
big_file_caption = f"<a href='{CHANNEL_LINK}'>HI-RES ⛔️ AntiHentai 🚫</a>"

# --- File System Paths ---
# Define base paths for different content types
base_drive_path = script_dir.parent.parent
paths = {
    "art": base_drive_path / "Images",
    "gif": base_drive_path / "Gifs",
    "video": base_drive_path / "Video",
    "real": base_drive_path / "Real",
    "p": base_drive_path / "sheesh" / "Unpacked" / "photo",
    "v": base_drive_path / "sheesh" / "Unpacked" / "video"
}

# Ensure all content directories exist
for path in paths.values():
    os.makedirs(path, exist_ok=True)

# Paths to JSON files that store already-sent files
sent_files_paths = {
    "gif": "sent_gifs.json",
    "video": "sent_videos.json",
    "art": "sent_arts.json",
    "real": "sent_real.json",
    "p": "sent_P.json",
    "v": "sent_V.json"
}

# Allowed file extensions for each content type
ALLOWED_EXTENSIONS = {
    "art": {".jpg", ".jpeg", ".png", ".webp"},
    "gif": {".gif"},
    "video": {".mp4", ".mov", ".avi", ".mkv", ".webm"},
    "real": {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".avi", ".mkv"},
    "p": {".jpg", ".jpeg", ".png", ".webp"},
    "v": {".mp4", ".mov", ".avi", ".mkv"}
}

# --- Bot State ---
# In-memory dictionary to store content pending moderation
pending_photos = {}


# === 2. Async File & Auth Helpers ===

async def scan_and_log_file_stats():
    """
    Scans all content directories on startup and logs a visual summary
    of the file status, including counts for skipped files.
    """
    logger.info("--- Scanning File Statistics ---")
    
    BAR_WIDTH = 30  # Width of the text-based bar chart in characters
    
    # Overall totals
    overall_total = 0
    overall_available = 0
    overall_sent = 0
    overall_skipped = 0

    for file_type, path in paths.items():
        if not os.path.exists(path):
            logger.warning(f"Path does not exist, skipping: {path}")
            continue
            
        try:
            sent_files = await load_sent_files_async(sent_files_paths[file_type])
            allowed_exts = ALLOWED_EXTENSIONS.get(file_type, set())
            
            # Counters for summary
            valid_files = []
            skipped_empty = 0
            skipped_large = 0
            skipped_extension = 0
            
            all_files_in_dir = os.listdir(path)
            total_files_in_dir = len(all_files_in_dir)
            
            for f in all_files_in_dir:
                file_path = os.path.join(path, f)
                
                if not os.path.isfile(file_path):
                    continue  # Skip directories
                    
                if not has_valid_extension(f, allowed_exts):
                    skipped_extension += 1
                    continue
                
                try:
                    file_size = os.path.getsize(file_path)
                except OSError:
                    skipped_empty += 1 # Treat inaccessible files as "empty"
                    continue 

                if file_size == 0:
                    skipped_empty += 1
                    continue
                
                # Check 50MB limit ONLY for non-image types
                if file_type in ['video', 'gif'] and file_size > 50 * 1024 * 1024:
                    skipped_large += 1
                    continue
                    
                # If it passes all checks, it's a valid file
                valid_files.append(f)

            available_files_count = len([f for f in valid_files if f not in sent_files])
            sent_files_count = len(sent_files.intersection(valid_files)) # Count only sent files that are still valid
            skipped_files_count = skipped_empty + skipped_large + skipped_extension
            total_valid_plus_skipped = len(valid_files) + skipped_files_count
            
            # Update overall totals
            overall_total += total_valid_plus_skipped
            overall_available += available_files_count
            overall_sent += sent_files_count
            overall_skipped += skipped_files_count

            logger.info(f"[{file_type.upper():<5}]: {total_valid_plus_skipped} files total")

            if total_valid_plus_skipped > 0:
                # Calculate percentages
                available_perc = available_files_count / total_valid_plus_skipped
                sent_perc = sent_files_count / total_valid_plus_skipped
                skipped_perc = skipped_files_count / total_valid_plus_skipped

                # Build the bar chart
                available_bar = "🟩" * int(available_perc * BAR_WIDTH)
                sent_bar = "🟦" * int(sent_perc * BAR_WIDTH)
                skipped_bar = "🟥" * int(skipped_perc * BAR_WIDTH)
                
                # Adjust for rounding errors to ensure full bar
                while len(available_bar) + len(sent_bar) + len(skipped_bar) < BAR_WIDTH and \
                      (available_files_count + sent_files_count + skipped_files_count) > 0:
                    
                    if available_perc > 0 and len(available_bar) / BAR_WIDTH < available_perc:
                        available_bar += "🟩"
                    elif sent_perc > 0 and len(sent_bar) / BAR_WIDTH < sent_perc:
                        sent_bar += "🟦"
                    elif skipped_perc > 0 and len(skipped_bar) / BAR_WIDTH < skipped_perc:
                         skipped_bar += "🟥"
                    else: # Failsafe
                        available_bar += "🟩"


                logger.info(f"   {available_bar}{sent_bar}{skipped_bar}")
                logger.info(f"   🟩 Available: {available_files_count:<7} ({available_perc:.0%})")
                logger.info(f"   🟦 Sent:      {sent_files_count:<7} ({sent_perc:.0%})")
                logger.info(f"   🟥 Skipped:   {skipped_files_count:<7} ({skipped_perc:.0%})")
                
                if skipped_files_count > 0:
                    logger.info(f"     └ Skipped details: (Empty: {skipped_empty}, Large: {skipped_large}, Extension: {skipped_extension})")
            
        except Exception as e:
            logger.error(f"Failed to scan directory {path}: {e}")

    # --- Log Overall Statistics ---
    logger.info("---")
    logger.info(f"[OVERALL]: {overall_total} files total")
    if overall_total > 0:
        available_perc = overall_available / overall_total
        sent_perc = overall_sent / overall_total
        skipped_perc = overall_skipped / overall_total

        available_bar = "🟩" * int(available_perc * BAR_WIDTH)
        sent_bar = "🟦" * int(sent_perc * BAR_WIDTH)
        skipped_bar = "🟥" * int(skipped_perc * BAR_WIDTH)

        while len(available_bar) + len(sent_bar) + len(skipped_bar) < BAR_WIDTH:
            available_bar += "🟩"
            
        logger.info(f"   {available_bar}{sent_bar}{skipped_bar}")
        logger.info(f"   🟩 Total Available: {overall_available:<7} ({available_perc:.0%})")
        logger.info(f"   🟦 Total Sent:      {overall_sent:<7} ({sent_perc:.0%})")
        logger.info(f"   🟥 Total Skipped:   {overall_skipped:<7} ({skipped_perc:.0%})")
    
    logger.info("--- File Statistics Scan Complete ---")


async def load_sent_files_async(file_path: str) -> set:
    """Loads a set of filenames from a JSON file."""
    if os.path.exists(file_path):
        try:
            async with aiofiles.open(file_path, "r", encoding='utf-8') as file:
                content = await file.read()
                return set(json.loads(content))
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return set()
    return set()


async def save_sent_files_async(file_path: str, sent_files: set):
    """Saves a set of filenames to a JSON file."""
    try:
        async with aiofiles.open(file_path, "w", encoding='utf-8') as file:
            await file.write(json.dumps(list(sent_files)))
    except Exception as e:
        logger.error(f"Error saving {file_path}: {e}")


async def check_subscription(user_id: int, channel_id: int, status: list) -> bool:
    """Checks if a user has a specific status (e.g., 'administrator') in the channel."""
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in status
    except Exception as e:
        logger.error(f"Error checking subscription for user {user_id}: {e}")
        return False


# === 3. Keyboard Definitions ===

def get_admin_keyboard() -> types.ReplyKeyboardMarkup:
    """Builds the reply keyboard for admins."""
    keyboard_builder = ReplyKeyboardBuilder()
    keyboard_builder.button(text='Art')
    keyboard_builder.button(text='Gif')
    keyboard_builder.button(text='Video')
    keyboard_builder.button(text='Real')
    keyboard_builder.button(text='P')
    keyboard_builder.button(text='V')
    keyboard_builder.adjust(3, 4)
    return keyboard_builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Choose a function"
    )


def get_member_keyboard() -> types.ReplyKeyboardMarkup:
    """Builds the reply keyboard for non-admin members."""
    keyboard_builder = ReplyKeyboardBuilder()
    keyboard_builder.button(text='This button is not doing anything yet')
    keyboard_builder.adjust(1)
    return keyboard_builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Choose a function"
    )


def get_approve_keyboard(message_id: int, user_id: int) -> types.InlineKeyboardMarkup:
    """Builds the inline keyboard (✅/❌) for moderation messages."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅", callback_data=f"approve:{message_id}:{user_id}")
    builder.button(text="❌", callback_data=f"reject:{message_id}:{user_id}")
    builder.adjust(2)
    return builder.as_markup()


# === 4. Core Bot Handlers ===

@dp.message(F.text == "/start")
async def get_start(message: types.Message):
    """Handles the /start command, showing the correct keyboard based on user status."""
    user_id = message.from_user.id
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        reply_text = f'Hi! {message.from_user.first_name}. You are an admin, so you know what you are doing, right?'
        await message.answer(reply_text, reply_markup=get_admin_keyboard())
    elif await check_subscription(user_id, CHANNEL_ID, ['member', 'restricted']):
        reply_text = f'Hi! {message.from_user.first_name}. You can suggest your image by sending it to this bot!'
        await message.answer(reply_text, reply_markup=get_member_keyboard())
    else:
        # Not an admin and not in the channel
        await message.reply(
            f"❌You are not subscribed to <a href='{CHANNEL_LINK}'>⛔️ AntiHentai 🚫</a>!❌",
            parse_mode='HTML'
        )


# --- HANDLERS FOR ADMIN KEYBOARD BUTTONS ---
# (These MUST be registered before the general handle_text handler)

@dp.message(F.text.in_(["Gif", "Art", "Video"]))
async def admin_start_scheduling(message: types.Message):
    """
    Handles admin buttons for starting RECURRING posts to the CHANNEL
    ("Gif", "Art", "Video").
    """
    user_id = message.from_user.id
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        file_type = message.text.lower()
        
        # Define intervals from the old code
        interval_range = (4, 24)
        if file_type == 'art':
            interval_range = (1, 3)
            
        # Notify admin that the process is starting
        status_message = await message.reply(f"Starting scheduled {file_type} posts...")
        
        # Call the scheduling function, passing the message to delete
        await send_scheduled_file(
            file_type,
            interval_range=interval_range,
            message=message,
            status_message_to_delete=status_message
        )
    else:
        await message.reply("❌ Only administrators can use this bot. ❌", parse_mode='HTML')


@dp.message(F.text.in_(["Real", "P", "V"]))
async def admin_send_personal(message: types.Message):
    """
    Handles admin buttons for sending a ONE-OFF file to the ADMIN'S PM
    ("Real", "P", "V").
    """
    user_id = message.from_user.id
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        file_type = message.text.lower()
        # Call the one-off posting function
        await send_random_file(message, file_type)
    else:
        await message.reply("❌ Only administrators can use this bot. ❌", parse_mode='HTML')

# --- (End of button handlers) ---


# === 5. Moderation System & Content Handlers ===

def is_valid_url(url: str) -> bool:
    """Simple regex check to validate a URL format."""
    pattern = re.compile(
        r'^(https?://)'
        r'([A-Za-z0-9\.-]+)\.([A-Za-z]{2,6})'
        r'(/[A-Za-z0-9\._~:/?#\[\]@!$&\'()*+,;=%-]*)?$'
    )
    return bool(pattern.match(url))


@dp.message(F.text.contains('https://') | F.text.contains('http://'))
async def handle_link(message: types.Message) -> None:
    """
    Handles messages with links.
    Admin: posts photo directly to channel.
    User: (In this version, it's admin-only)
    """
    # This handler is ADMIN-ONLY in this code version
    if not await check_subscription(message.from_user.id, CHANNEL_ID, ['administrator', 'creator']):
         await message.reply("❌ Only administrators can use this bot for links. ❌", parse_mode='HTML')
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


@dp.message(F.video | F.animation)
async def resend_media(message: types.Message):
    """
    Handles direct uploads of videos/GIFs.
    Admin: resends to channel (but this version has the blocking sleep).
    User: (Not handled in this version)
    """
    user_id = message.from_user.id
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        # WARNING: This handler contains blocking asyncio.sleep calls
        # which will freeze the bot for 30 minutes.
        try:
            if message.video:
                await bot.send_video(chat_id=CHANNEL_ID, video=message.video.file_id, caption=caption, parse_mode=ParseMode.HTML)
                logger.info('Video resent')
                await asyncio.sleep(1 * 60 * 30) # <-- BLOCKING CALL
            elif message.animation:
                await bot.send_animation(chat_id=CHANNEL_ID, animation=message.animation.file_id, caption=caption, parse_mode=ParseMode.HTML)
                logger.info('Animation resent')
                await asyncio.sleep(1 * 60 * 30) # <-- BLOCKING CALL
            else:
                await message.reply("Unsupported or missing media file.")
        except Exception as e:
            logger.error(f"Error in resend function: {e}")
            await message.reply("An error occurred while resending the media.")
    else:
        await message.reply("You don't have permission to send media.")


@dp.message(F.photo)
async def handle_photo(message: types.Message):
    """
    Handles incoming photos.
    Admin: resends to channel (with blocking sleep).
    User: sends photo to admins for moderation.
    """
    user_id = message.from_user.id
    logger.info(f"User {user_id} sent a photo at {datetime.now()}")
    
    if not message.photo or not hasattr(message.photo[-1], 'file_id'):
        await message.reply("No valid photo found in your message.")
        return
        
    if await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        # Admin — send directly to the group
        # WARNING: This function contains blocking asyncio.sleep calls
        try:
            await bot.send_photo(chat_id=CHANNEL_ID, photo=message.photo[-1].file_id, caption=caption, parse_mode=ParseMode.HTML)
            logger.info('Photo resent')
            await asyncio.sleep(1 * 60 * 30) # <-- BLOCKING CALL
        except Exception as e:
            logger.error(f"Error in admin photo resend: {e}")
            await message.reply("An error occurred while resending the media.")
            
    elif await check_subscription(user_id, CHANNEL_ID, ['member', 'restricted']):
        # User — send photo for moderation to all admins
        photo_file_id = message.photo[-1].file_id
        for admin_id in ADMIN_IDS:
            try:
                sent_msg = await bot.send_photo(
                    chat_id=admin_id,
                    photo=photo_file_id,
                    caption=f"New publication request from {user_id}"
                )
                # Add inline keyboard for approval/rejection after sending
                await sent_msg.edit_reply_markup(
                    reply_markup=get_approve_keyboard(sent_msg.message_id, user_id)
                )
                # Store the pending photo with the message ID as key
                pending_photos[sent_msg.message_id] = photo_file_id
            except Exception as e:
                logger.error(f"Failed to send moderation request to admin {admin_id}: {e}")
                
        await message.reply("Your photo has been sent for moderation.")
    else:
        # User is not subscribed
        await message.reply(
            f"❌You must be subscribed to <a href='{CHANNEL_LINK}'>⛔️ AntiHentai 🚫</a> to submit content!❌",
            parse_mode='HTML'
        )

# Fallback text handler (must be after buttons)
@dp.message(F.text)
async def handle_text(message: types.Message):
    """Handles any text that isn't a command (should be empty)."""
    logger.info(f"Received unhandled text: {message.text} from {message.from_user.id}")
    # You can add logic here if needed, e.g., for non-admin text submissions.


# === 6. Callback Handlers (Moderation Actions) ===

@dp.callback_query(F.data.startswith("approve:"))
async def approve_photo(callback: CallbackQuery):
    """Handles the 'Approve' (✅) button click from an admin."""
    _, message_id, user_id = callback.data.split(":")
    logger.info(f"Admin {callback.from_user.id} approved photo from user {user_id} at {datetime.now()}")
    
    photo_file_id = pending_photos.pop(int(message_id), None)
    
    if photo_file_id:
        try:
            await bot.send_photo(chat_id=CHANNEL_ID, photo=photo_file_id, caption=caption, parse_mode=ParseMode.HTML)
            await callback.message.edit_caption("✅ Photo published", reply_markup=None)
            await callback.answer("Photo published")
        except Exception as e:
            logger.error(f"Failed to publish approved photo: {e}")
            await callback.answer(f"Failed to publish: {e}", show_alert=True)
            # Put the photo back in the queue
            pending_photos[int(message_id)] = photo_file_id
    else:
        await callback.answer("Photo not found (already processed?)", show_alert=True)


@dp.callback_query(F.data.startswith("reject:"))
async def reject_photo(callback: CallbackQuery):
    """Handles the 'Reject' (❌) button click from an admin."""
    _, message_id, user_id = callback.data.split(":")
    logger.info(f"Admin {callback.from_user.id} rejected photo from user {user_id} at {datetime.now()}")
    
    pending_photos.pop(int(message_id), None)
    await callback.message.delete()
    await callback.answer("Photo rejected and deleted")


# === 7. File Processing & Posting Logic ===

def resize_image(image_path: str) -> io.BytesIO | None | str:
    """
    Handles image resizing and compression to fit Telegram's limits.
    - Resizes if dimensions are too large (sum > 10000px or bad ratio).
    - Compresses if file size is > 10MB (Telegram's limit for photos).
    - Converts non-JPEG images (like PNG, WEBP) to JPEG.
    
    Returns:
        - BytesIO: If resize/compression/conversion was needed and successful.
        - None: If file is already a valid JPEG under 10MB with good dimensions.
        - "" (empty string): If PIL fails to open the file (corrupted/invalid).
    """
    try:
        # Get original file size and format info
        file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
        is_jpeg = image_path.lower().endswith((".jpg", ".jpeg"))
        
        # Open the image and ensure it's in RGB format
        img = Image.open(image_path)
        img = img.convert("RGB")
    except Exception as e:
        logger.error(f"PIL failed to open image {image_path}: {e}")
        return ""  # Return empty string to signal a corrupt/invalid file

    width, height = img.width, img.height
    needs_resize = False
    needs_recode = not is_jpeg  # Mark for recoding if it's PNG, WEBP, etc.
    
    # Check 1: Invalid Dimensions (Telegram limit)
    if (width + height) > 10000:
        logger.warning(f"Resizing {image_path}: dimensions {width}x{height} sum > 10000.")
        needs_resize = True
        # Calculate new dimensions preserving aspect ratio
        ratio = 10000 / (width + height)
        width = int(width * ratio)
        height = int(height * ratio)
    
    # Check 2: Extreme Aspect Ratio (Telegram limit)
    if width > 0 and height > 0:
        if width / height > 20 or height / width > 20:
            logger.warning(f"Resizing {image_path}: aspect ratio > 20.")
            needs_resize = True
            # Clamp the aspect ratio (e.g., make it 20:1)
            if width > height:
                height = max(1, int(width / 20)) # Ensure height is at least 1
            else:
                width = max(1, int(height / 20)) # Ensure width is at least 1
                
    if needs_resize:
        try:
            img = img.resize((width, height), Image.LANCZOS)
        except Exception as e:
            logger.error(f"Failed to resize image {image_path}: {e}")
            return "" # Treat as corrupted if resize fails
            
    # Check 3: File Size (Telegram limit is 10MB for photos)
    # OR if it's a non-JPEG (like PNG) that needs conversion
    # OR if it was already resized
    if file_size_mb > 10.0 or needs_recode or needs_resize:
        if file_size_mb > 10.0:
            logger.warning(f"Compressing {image_path}: size {file_size_mb:.2f}MB > 10MB.")
        elif needs_recode:
            logger.info(f"Converting {image_path} from non-JPEG format.")
        elif needs_resize:
            logger.info(f"Saving resized {image_path}...")

        img_bytes = io.BytesIO()
        quality = 90  # Start with high quality for recoding/resizing
        
        # If it's too large, start with lower quality
        if file_size_mb > 10.0:
            quality = 85

        # Iteratively lower quality until it's under 10MB
        while quality > 40:
            img_bytes.seek(0)
            img_bytes.truncate()
            try:
                img.save(img_bytes, format="JPEG", quality=quality)
            except Exception as e:
                 logger.error(f"Failed to save image {image_path} at quality {quality}: {e}")
                 return "" # Corrupted
            
            if img_bytes.tell() <= 10 * 1024 * 1024:
                break # Success!
            quality -= 10
            
        if img_bytes.tell() > 10 * 1024 * 1024:
            logger.error(f"Could not compress {image_path} under 10MB.")
            return "" # Failed to compress, send as document
            
        logger.info(f"Processed {image_path}. New size: {img_bytes.tell() / (1024*1024):.2f}MB at quality {quality}.")
        img_bytes.seek(0)
        return img_bytes

    else:
        # No resize, compression, or conversion needed
        # (It's a JPEG <= 10MB with valid dimensions)
        return None


def is_valid_file(file_path: str, file_type: str) -> bool:
    """
    Checks if a file is valid for sending.
    - Not a directory.
    - Not empty (0 bytes).
    - If it's a non-image (video/gif), checks it's under 50MB.
    This function is now SILENT and only logs at a DEBUG level (if enabled).
    The main counting logic is in `scan_and_log_file_stats`.
    """
    if not os.path.isfile(file_path):
        return False
        
    try:
        file_size = os.path.getsize(file_path)
    except OSError as e:
        logger.debug(f"Could not get size of file {file_path}: {e}")
        return False

    if file_size == 0:
        return False
    
    # For non-image types, check the 50MB Telegram limit
    if file_type in ['video', 'gif']:
        if file_size > 50 * 1024 * 1024:
            return False
            
    return True


def has_valid_extension(filename: str, allowed_exts: set) -> bool:
    """Checks if a filename has one of the allowed extensions."""
    return any(filename.lower().endswith(ext) for ext in allowed_exts)


# --- CORRECTED (NON-BLOCKING) SCHEDULING LOGIC ---

async def send_random_file(message: types.Message, file_type: str) -> None:
    """
    Sends ONE random file of a specific type to the ADMIN'S PM.
    Used for "Real", "P", "V".
    Will attempt to send as document if photo processing fails.
    """
    user_id = message.from_user.id
    if not await check_subscription(user_id, CHANNEL_ID, ['administrator', 'creator']):
        await message.reply(f"❌ Only administrators can use this bot ❌", parse_mode='HTML')
        return

    path = paths[file_type]
    sent_files = await load_sent_files_async(sent_files_paths[file_type])
    allowed_exts = ALLOWED_EXTENSIONS.get(file_type, set())
    
    files = [
        f for f in os.listdir(path)
        if has_valid_extension(f, allowed_exts) and is_valid_file(os.path.join(path, f), file_type)
    ]
    available_files = [f for f in files if f not in sent_files]

    if not available_files:
        await message.reply("No new files available to send.")
        return

    random_file = random.choice(available_files)
    file_path = os.path.join(path, random_file)
    file_size = os.path.getsize(file_path)
    file_info = f"{file_path} {BOLD_START}{(file_size / (1024 * 1024)):.2f}MB{BOLD_END}"
    await message.answer(file_info, parse_mode=ParseMode.HTML)
    
    try:
        # --- For personal admin use (NOT IN CHANNEL) ---
        if file_type in ['real', 'p']:
            processed_image = resize_image(file_path)
            
            if processed_image == "":  # Corrupted file
                raise ValueError("File is corrupted or invalid, sending as document.")
            
            if processed_image is None:  # File is OK, send original
                input_file = types.FSInputFile(file_path)
            else:  # File was resized/compressed
                input_file = types.BufferedInputFile(processed_image.getvalue(), filename="image.jpg")
                
            await message.answer_photo(photo=input_file, caption=caption, parse_mode=ParseMode.HTML)

        elif file_type == 'v':
            await message.answer_video(video=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)

        sent_files.add(random_file)
        await save_sent_files_async(sent_files_paths[file_type], sent_files)

    except Exception as e:
        logger.error(f"Failed to send file {file_path} as photo/video: {e}. Sending as document.")
        try:
            # Fallback: send as document
            await message.answer_document(document=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)
            sent_files.add(random_file) # Mark as sent even if as document
            await save_sent_files_async(sent_files_paths[file_type], sent_files)
        except Exception as e2:
            logger.critical(f"Failed to send {file_path} even as document: {e2}")
            await message.reply(f"Error sending file {random_file}: {e2}")


async def send_scheduled_file(
    file_type: str,
    interval_range: tuple,
    message: types.Message | None = None,
    status_message_to_delete: types.Message | None = None
):
    """
    Sends ONE file to the CHANNEL and schedules the NEXT one.
    - Used for "Art", "Gif", "Video".
    - `message` and `status_message_to_delete` are only provided on the first (manual) run.
    """
    path = paths[file_type]
    sent_files = await load_sent_files_async(sent_files_paths[file_type])
    allowed_exts = ALLOWED_EXTENSIONS.get(file_type, set())
    
    files = [
        f for f in os.listdir(path)
        if has_valid_extension(f, allowed_exts) and is_valid_file(os.path.join(path, f), file_type)
    ]
    available_files = [f for f in files if f not in sent_files]

    # Clean up the "Starting..." message regardless of outcome
    if status_message_to_delete:
        try:
            await status_message_to_delete.delete()
        except Exception as e:
            logger.warning(f"Could not delete status message: {e}")

    if not available_files:
        logger.warning(f"No new scheduled files of type {file_type} to send.")
        if message:
            await message.reply("No new files available to send.")
        return  # Stop execution if no files

    random_file = random.choice(available_files)
    file_path = os.path.join(path, random_file)
    file_size = os.path.getsize(file_path)
    file_info = f"File: {file_path} {BOLD_START}{(file_size / (1024 * 1024)):.2f}MB{BOLD_END}"
    logger.info(f"Attempting scheduled post: {file_info.replace(BOLD_START, '').replace(BOLD_END, '')}")
    
    # If this is the first manual call, send feedback to the admin
    if message:
        await message.answer(file_info, parse_mode=ParseMode.HTML)
    
    try:
        # --- For public channel posting ---
        if file_type == 'art':
            processed_image = resize_image(file_path)
            
            if processed_image == "":  # Corrupted file
                raise ValueError("File is corrupted or invalid, sending as document.")
            
            if processed_image is None:  # File is OK, send original
                input_file = types.FSInputFile(file_path)
            else:  # File was resized/compressed
                input_file = types.BufferedInputFile(processed_image.getvalue(), filename="image.jpg")
                
            await bot.send_photo(chat_id=CHANNEL_ID, photo=input_file, caption=caption, parse_mode=ParseMode.HTML)

        elif file_type == 'gif':
            await bot.send_animation(chat_id=CHANNEL_ID, animation=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)
        elif file_type == 'video':
            await bot.send_video(chat_id=CHANNEL_ID, video=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)
        
        # If sending succeeded, mark as sent
        sent_files.add(random_file)
        await save_sent_files_async(sent_files_paths[file_type], sent_files)

    except Exception as e:
        logger.error(f"Failed to send {file_path} as photo/video: {e}. Sending as document.")
        try:
            # Fallback: send as document
            await bot.send_document(chat_id=CHANNEL_ID, document=types.FSInputFile(file_path), caption=caption, parse_mode=ParseMode.HTML)
            sent_files.add(random_file) # Mark as sent even if as document
            await save_sent_files_async(sent_files_paths[file_type], sent_files)
        except Exception as e2:
            logger.critical(f"Failed to send {file_path} even as document: {e2}")
            if message:
                await message.reply(f"Error sending file {random_file}: {e2}")
            return # Do not schedule next post if critical error
            
    # Schedule the next post
    interval = random.randrange(*interval_range) * random.randrange(3300, 3900)
    next_post_time = datetime.now() + timedelta(seconds=interval)
    
    # Create the message for the next post
    next_post_msg = f"Next {BOLD_START}{file_type}{BOLD_END} post scheduled at: {BOLD_START}{next_post_time.strftime('%d-%m-%Y %H:%M')}{BOLD_END}"
    
    # Log it (without HTML)
    logger.info(next_post_msg.replace(BOLD_START, "").replace(BOLD_END, ""))
    
    # If this was a manual start, notify the admin
    if message:
        await message.answer(next_post_msg, parse_mode=ParseMode.HTML)
    
    # Create the next background task
    asyncio.create_task(scheduled_post_recursive(file_type, interval, interval_range))


async def scheduled_post_recursive(file_type: str, interval: int, interval_range: tuple):
    """
    A helper function called by asyncio.create_task to wait and then post.
    This runs entirely in the background, without a user message.
    """
    await asyncio.sleep(interval)
    await send_scheduled_file(file_type, interval_range)


# === 8. Main Bot Execution ===

async def main() -> None:
    """Main entry point for the bot."""
    # Scan and log file stats on startup
    await scan_and_log_file_stats()
    
    logger.info("Bot is starting polling...")
    # Start polling for updates
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())