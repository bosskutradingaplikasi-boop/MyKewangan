import logging
import os
import pytz
import csv
import io
import asyncio
import re
from datetime import datetime, timedelta
from functools import wraps

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, JSONResponse
from starlette.routing import Route

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
PREMIUM_PRICE = 5.00
FREE_TRANSACTION_LIMIT = 100

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Application Initialization (Global Scope) ---
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
            target_message = update.callback_query.message if update.callback_query else update.message
            await target_message.reply_text(
                "🚫 Fungsi ini khas untuk Akaun Premium sahaja.\n\n" \
                f"Naik taraf kepada Premium dengan hanya RM{PREMIUM_PRICE:.2f} sebulan!\n\n" \
                "Taip /upgrade untuk bermula."
            )
    return wrapped

# --- Command & Callback Handlers ---
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
        "<b>Bantuan & Status Akaun</b>\n\n"
        "/status - Semak status akaun anda.\n"
        "/upgrade [email] - Naik taraf ke akaun Premium.\n\n"
        "<b>--- Arahan Asas ---</b>\n"
        "/belanja [jumlah] [nota]\n"
        "/masuk [jumlah] [nota]\n"
        "/laporan [harian|mingguan|bulanan]\n"
        "/baki\n"
        "/padam [ID]\n"
        "/kategori\n"
        "/backup - (Premium) Eksport data ke CSV."
    )
    target_message = update.callback_query.message if update.callback_query else update.message
    await target_message.reply_html(help_text, disable_web_page_preview=True)

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

    chat_id = update.message.chat_id
    try:
        parts = context.args
        if len(parts) < 2:
            await context.bot.send_message(chat_id, f"Format salah. Guna: /{jenis} [jumlah] [nota]")
            return

        amaun = float(parts[0])
        nota = " ".join(parts[1:])
        kategori = nota.split()[0]

        with next(db.get_db()) as conn:
            new_trans = db.add_transaction(conn, user.id, jenis, amaun, kategori, nota)
        
        tz = pytz.timezone(TIMEZONE)
        timestamp = new_trans.tarikh.astimezone(tz).strftime("%d %b %Y, %I:%M %p")
        verb = "Duit Keluar" if jenis == 'keluar' else "Duit Masuk"

        keyboard = [[InlineKeyboardButton("❌ Batalkan", callback_data=f'undo_{new_trans.id}')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id, 
            f"✅ Tambah {verb}:\nRM{amaun:.2f} - {nota}\nDisimpan pada {timestamp}",
            reply_markup=reply_markup
        )
    except (ValueError, IndexError):
        await context.bot.send_message(chat_id, f"Format salah. Pastikan jumlah adalah nombor.\nCth: /{jenis} 12.50 makan")
    except Exception as e:
        logger.error(f"Error in handle_transaction: {e}")
        await context.bot.send_message(chat_id, "Maaf, berlaku ralat semasa menyimpan data.")

async def belanja(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await handle_transaction(update, context, 'keluar')

async def masuk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await handle_transaction(update, context, 'masuk')

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

async def kategori_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    with next(db.get_db()) as conn:
        kategori = db.get_kategori(conn, user_id)
    
    if kategori:
        message = "<b>📊 Senarai Kategori Anda:</b>\n"
        message += "\n".join([f"- {k[0].capitalize()}" for k in kategori])
    else:
        message = "Tiada kategori direkodkan lagi."
        
    await update.message.reply_html(message)

async def padam_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    try:
        transaction_id = int(context.args[0])
        with next(db.get_db()) as conn:
            deleted_trans = db.delete_transaction(conn, user_id, transaction_id)
        
        if deleted_trans:
            await update.message.reply_text(f"🗑️ Transaksi {transaction_id} telah dipadam.")
        else:
            await update.message.reply_text("Transaksi tidak dijumpai atau anda tidak mempunyai kebenaran untuk memadamnya.")
            
    except (IndexError, ValueError):
        await update.message.reply_text("Format salah. Sila guna: /padam [ID Transaksi]")
    except Exception as e:
        logger.error(f"Error in padam_command: {e}")
        await update.message.reply_text("Maaf, berlaku ralat semasa memadam transaksi.")

async def laporan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    period = context.args[0].lower() if context.args else 'harian'
    
    if period not in ['harian', 'mingguan', 'bulanan']:
        await update.message.reply_text("Tempoh tidak sah. Sila guna: harian, mingguan, atau bulanan.")
        return
        
    report_text = laporan.generate_report_text(user_id, period)
    await update.message.reply_html(report_text)

@premium_only
async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text("Memproses data anda, sila tunggu...")
    with next(db.get_db()) as conn:
        transactions = db.get_all_transactions_by_user(conn, user_id)
    if not transactions:
        await update.message.reply_text("Tiada data transaksi untuk dieksport.")
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Jenis', 'Amaun', 'Kategori', 'Nota', 'Tarikh'])
    for t in transactions:
        writer.writerow([t.id, t.jenis, t.amaun, t.kategori, t.nota, t.tarikh.strftime("%Y-%m-%d %H:%M:%S")])
    output.seek(0)
    file_bytes = io.BytesIO(output.getvalue().encode('utf-8'))
    file_bytes.name = f"mykewangan_backup_{datetime.now().strftime('%Y%m%d')}.csv"
    await update.message.reply_document(document=file_bytes)

async def baki(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    with next(db.get_db()) as conn:
        balance = db.get_balance(conn, user_id)
    
    target_message = update.callback_query.message if update.callback_query else update.message
    await target_message.reply_html(f"<b>Baki Semasa Anda:</b> RM{balance:.2f}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data.startswith('undo_'):
        transaction_id = int(query.data.split('_')[1])
        user_id = update.effective_user.id
        with next(db.get_db()) as conn:
            deleted_trans = db.delete_transaction(conn, user_id, transaction_id)
        if deleted_trans:
            await query.edit_message_text(f"✅ Transaksi {transaction_id} telah dibatalkan.")
        else:
            await query.edit_message_text("Gagal membatalkan transaksi. Mungkin ia telah pun dipadamkan.")
    elif query.data == 'rekod_belanja_menu':
        await query.message.reply_html("Format: <code>/belanja [jumlah] [nota]</code>")
    elif query.data == 'rekod_masuk_menu':
        await query.message.reply_html("Format: <code>/masuk [jumlah] [nota]</code>")
    elif query.data == 'laporan_menu':
        await query.message.reply_text("Sila pilih: /laporan harian, /laporan mingguan, atau /laporan bulanan.")
    elif query.data == 'baki_menu':
        await baki(update, context)
    elif query.data == 'help_menu':
        await help_command(update, context)

# --- Webhook and Cron Job Handlers ---
async def toyyibpay_callback(request: Request) -> PlainTextResponse:
    logger.info("Received Toyyibpay callback")
    try:
        form_data = await request.form()
        refno = form_data.get('refno')
        payment_status = form_data.get('status')
        user_telegram_id = int(refno.split('-')[1])
        if payment_status == '1':
            with next(db.get_db()) as conn:
                user = conn.query(db.User).filter(db.User.telegram_id == user_telegram_id).first()
                if user:
                    user.status = 'premium'
                    user.subscription_start = datetime.now(pytz.utc)
                    user.subscription_end = datetime.now(pytz.utc) + timedelta(days=30)
                    conn.commit()
                    expiry_date = user.subscription_end.astimezone(pytz.timezone(TIMEZONE)).strftime("%d %B %Y")
                    await application.bot.send_message(chat_id=user_telegram_id, text=f"🎉Akaun Premium anda telah diaktifkan!\nSah sehingga: {expiry_date}")
        return PlainTextResponse("OK")
    except Exception as e:
        logger.error(f"Error processing Toyyibpay callback: {e}")
        return PlainTextResponse("Error", status_code=500)

async def downgrade_users_cron(request: Request) -> JSONResponse:
    logger.info("Running daily downgrade cron job")
    processed_count = 0
    try:
        with next(db.get_db()) as conn:
            expired_users = conn.query(db.User).filter(db.User.status == 'premium', db.User.subscription_end < datetime.now(pytz.utc)).all()
            for user in expired_users:
                user.status = 'free'
                await application.bot.send_message(chat_id=user.telegram_id, text="⚠️ Langganan Premium anda telah tamat tempoh. Akaun anda telah ditukar kepada Percuma. Taip /upgrade untuk melanggan semula.")
                processed_count += 1
            conn.commit()
        return JSONResponse({"status": "success", "processed_users": processed_count})
    except Exception as e:
        logger.error(f"Error in downgrade cron job: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

# --- Starlette App Configuration ---
async def startup():
    db.init_db()
    await application.initialize()
    # (Register all handlers)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("upgrade", upgrade_command))
    application.add_handler(CommandHandler("belanja", belanja))
    application.add_handler(CommandHandler("masuk", masuk))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("laporan", laporan_command))
    application.add_handler(CommandHandler("padam", padam_command))
    application.add_handler(CommandHandler("kategori", kategori_command))
    application.add_handler(CommandHandler("baki", baki))
    
    application.add_handler(CallbackQueryHandler(button_handler))

    webhook_url = f"https://{VERCEL_URL}/telegram"
    await application.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)
    logger.info(f"Webhook set to {webhook_url}")

async def shutdown():
    await application.shutdown()

async def telegram_webhook(request: Request) -> PlainTextResponse:
    await application.update_queue.put(Update.de_json(await request.json(), application.bot))
    return PlainTextResponse("OK")

app = Starlette(
    routes=[
        Route("/telegram", endpoint=telegram_webhook, methods=["POST"]),
        Route("/webhook/toyyibpay", endpoint=toyyibpay_callback, methods=["POST"]),
        Route("/api/cron/downgrade_users", endpoint=downgrade_users_cron, methods=["GET"]),
    ],
    on_startup=[startup],
    on_shutdown=[shutdown],
)
