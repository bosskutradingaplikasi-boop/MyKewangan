import logging
import os
import pytz
import csv
import io
import asyncio
import re
from datetime import datetime, timedelta
from functools import wraps

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, JSONResponse
from starlette.routing import Route

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)
from dotenv import load_dotenv

import database as db
import laporan
import toyyibpay

# Load environment variables
load_dotenv()

# --- Constants ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kuala_Lumpur")
VERCEL_URL = os.getenv("VERCEL_URL")
PORT = int(os.getenv("PORT", 8000))
PREMIUM_PRICE = 5.00
FREE_TRANSACTION_LIMIT = 100

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Application Initialization (Global Scope) ---
# This is necessary for webhook handlers to access the bot
application = Application.builder().token(BOT_TOKEN).build()

# --- Decorators for Access Control ---
def premium_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        with next(db.get_db()) as conn:
            user = db.get_or_create_user(conn, user_id, update.effective_user.full_name)

        is_premium = False
        if user.status == 'premium' and user.subscription_end and user.subscription_end > datetime.now(pytz.utc):
            is_premium = True

        if is_premium:
            return await func(update, context, *args, **kwargs)
        else:
            await update.message.reply_text(
                "🚫 Fungsi ini khas untuk Akaun Premium sahaja.\n\n" \
                f"Naik taraf kepada Premium dengan hanya RM{PREMIUM_PRICE:.2f} sebulan!\n\n" \
                "Taip /upgrade untuk bermula."
            )
    return wrapped

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    with next(db.get_db()) as conn:
        db.get_or_create_user(conn, user.id, user.full_name)
    keyboard = [
        [InlineKeyboardButton("➕ Rekod Belanja", callback_data='rekod_belanja_menu'), InlineKeyboardButton("💰 Rekod Masuk", callback_data='rekod_masuk_menu')],
        [InlineKeyboardButton("📊 Buat Laporan", callback_data='laporan_menu'), InlineKeyboardButton("💸 Semak Baki", callback_data='baki_menu')],
        [InlineKeyboardButton("🌟 Akaun & Bantuan", callback_data='help_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(
        f"<b>✨ Selamat Datang ke MyKewanganBot, {user.mention_html()}!</b>\n\n" \
        "Urus kewangan anda dengan mudah. Rekod perbelanjaan, pendapatan, dan dapatkan laporan terus di Telegram.",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "<b>Bantuan & Status Akaun</b>\n\n" \
        "/status - Semak status akaun anda (Percuma/Premium).\n" \
        "/upgrade [email] - Naik taraf ke akaun Premium.\n\n" \
        "<b>--- Arahan Asas ---</b>\n" \
        "/belanja [jumlah] [nota]\n" \
        "/masuk [jumlah] [nota]\n" \
        "/laporan [harian|mingguan|bulanan]\n" \
        "/baki\n" \
        "/padam [ID]\n" \
        "/backup - (Premium Sahaja) Eksport data ke CSV."
    )
    target_message = update.callback_query.message if update.callback_query else update.message
    await target_message.reply_html(help_text)

async def handle_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, jenis: str) -> None:
    user_id = update.effective_user.id
    with next(db.get_db()) as conn:
        user = db.get_or_create_user(conn, user_id, update.effective_user.full_name)
        if user.status == 'free':
            count = db.count_transactions(conn, user.id)
            if count >= FREE_TRANSACTION_LIMIT:
                await update.message.reply_text(
                    f"🚫 Anda telah mencapai had {FREE_TRANSACTION_LIMIT} transaksi untuk akaun percuma.\n\n" \
                    "Sila /upgrade ke akaun Premium untuk transaksi tanpa had."
                )
                return

    # ... (rest of transaction logic) ...
    # (This part is re-integrated from previous versions)
    pass # Placeholder to avoid syntax error, the full logic will be in the final file

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    with next(db.get_db()) as conn:
        user = db.get_or_create_user(conn, user_id, update.effective_user.full_name)

    if user.status == 'premium' and user.subscription_end and user.subscription_end > datetime.now(pytz.utc):
        expiry_date = user.subscription_end.astimezone(pytz.timezone(TIMEZONE)).strftime("%d %B %Y, %I:%M %p")
        message = f"🌟 Status Akaun: <b>Premium</b>\nSah sehingga: <b>{expiry_date}</b>"
    else:
        message = "Status Akaun: <b>Percuma</b>\n\nNaik taraf ke Premium untuk menikmati ciri-ciri tanpa had! Taip /upgrade"
    await update.message.reply_html(message)

async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not re.match(r"[^@]+@[^@]+\.[^@]+", context.args[0]):
        await update.message.reply_html(
            "Sila berikan e-mel anda untuk tujuan resit dan pengesahan.\n" \
            "Format: <code>/upgrade emailanda@contoh.com</code>"
        )
        return

    email = context.args[0]
    user = update.effective_user
    await update.message.reply_text("Sedang menjana pautan bayaran, sila tunggu...")
    result = toyyibpay.create_bill(user.id, user.full_name, email, PREMIUM_PRICE)

    if result.get("success"):
        payment_url = result.get("payment_url")
        keyboard = [[InlineKeyboardButton(f"💳 Bayar RM{PREMIUM_PRICE:.2f} Sekarang", url=payment_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Hebat! Klik butang di bawah untuk melengkapkan pembayaran anda melalui Toyyibpay.",
            reply_markup=reply_markup
        )
    else:
        logger.error(f"Toyyibpay error for user {user.id}: {result.get('error')}")
        await update.message.reply_text("Maaf, kami tidak dapat menjana pautan bayaran pada masa ini.")

@premium_only
async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (Full backup logic) ...
    pass

# --- Webhook and Cron Job Handlers ---
async def toyyibpay_callback(request: Request) -> PlainTextResponse:
    logger.info("Received Toyyibpay callback")
    try:
        form_data = await request.form()
        refno = form_data.get('refno')
        payment_status = form_data.get('status')
        
        if payment_status == '1': # 1 means success
            user_telegram_id = int(refno.split('-')[1])
            with next(db.get_db()) as conn:
                user = conn.query(db.User).filter(db.User.telegram_id == user_telegram_id).first()
                if user:
                    user.status = 'premium'
                    user.subscription_start = datetime.now(pytz.utc)
                    user.subscription_end = datetime.now(pytz.utc) + timedelta(days=30)
                    conn.commit()
                    
                    expiry_date = user.subscription_end.astimezone(pytz.timezone(TIMEZONE)).strftime("%d %B %Y")
                    await application.bot.send_message(
                        chat_id=user_telegram_id,
                        text=f"🎉Akaun Premium anda telah diaktifkan!\nSah sehingga: {expiry_date}\n\nTerima kasih kerana menyokong MyKewanganBot! 💰"
                    )
        return PlainTextResponse("OK")
    except Exception as e:
        logger.error(f"Error processing Toyyibpay callback: {e}")
        return PlainTextResponse("Error", status_code=500)

async def downgrade_users_cron(request: Request) -> JSONResponse:
    logger.info("Running daily downgrade cron job")
    processed_count = 0
    try:
        with next(db.get_db()) as conn:
            expired_users = conn.query(db.User).filter(
                db.User.status == 'premium',
                db.User.subscription_end < datetime.now(pytz.utc)
            ).all()

            for user in expired_users:
                user.status = 'free'
                await application.bot.send_message(
                    chat_id=user.telegram_id,
                    text="⚠️ Langganan Premium anda telah tamat tempoh. Akaun anda telah ditukar kepada Percuma. Taip /upgrade untuk melanggan semula."
                )
                processed_count += 1
            conn.commit()
        return JSONResponse({"status": "success", "processed_users": processed_count})
    except Exception as e:
        logger.error(f"Error in downgrade cron job: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

# --- Main Application Setup ---
async def main() -> None:
    await application.initialize()
    # (Re-integrating all handlers)
    # ...

    # --- Web server setup ---
    async def telegram_webhook(request: Request) -> PlainTextResponse:
        await application.update_queue.put(Update.de_json(await request.json(), application.bot))
        return PlainTextResponse("OK")

    routes = [
        Route("/telegram", endpoint=telegram_webhook, methods=["POST"]),
        Route("/webhook/toyyibpay", endpoint=toyyibpay_callback, methods=["POST"]),
        Route("/api/cron/downgrade_users", endpoint=downgrade_users_cron, methods=["GET"]),
    ]
    web_server = Starlette(routes=routes)
    config = uvicorn.Config(app=web_server, host="0.0.0.0", port=PORT)
    server = uvicorn.Server(config)

    webhook_url = f"https://{VERCEL_URL}/telegram"
    if (await application.bot.get_webhook_info()).url != webhook_url:
        await application.bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook set to {webhook_url}")

    logger.info(f"Starting server on port {PORT}")
    await server.serve()

if __name__ == "__main__":
    # This runs the web server, suitable for Vercel deployment
    # To run locally: uvicorn main:web_server --reload
    # Ensure you have a .env file with all necessary variables
    db.init_db() # Initialize database tables
    # The main function is now the web server runner
    # For simplicity, we are not re-adding all handlers in this placeholder.
    # The final file will have them.
    pass
