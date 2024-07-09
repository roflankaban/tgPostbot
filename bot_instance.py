from aiogram import Bot

from token_api import TOKEN_API


bot = Bot(
    token=TOKEN_API,
    parse_mode='HTML'
)