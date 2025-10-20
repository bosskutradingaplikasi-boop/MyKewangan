# scheduler.py

import logging
from telegram.ext import Application
import database as db
import laporan

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def send_auto_reports(application: Application):
    """
    Fungsi ini akan dipanggil secara berkala (cth: oleh Vercel Cron Job)
    untuk menghantar laporan kepada pengguna yang telah mengaktifkan auto-report.
    """
    bot = application.bot
    logging.info("Running scheduled report job...")
    with next(db.get_db()) as conn:
        users_to_report = conn.query(db.User).filter(db.User.auto_laporan == 'on').all()

    for user in users_to_report:
        try:
            report_text = laporan.generate_report_text(user.id, 'harian')
            await bot.send_message(chat_id=user.telegram_id, text=report_text)
            logging.info(f"Sent daily report to user {user.telegram_id}")
        except Exception as e:
            logging.error(f"Failed to send report to {user.telegram_id}: {e}")

# Nota: Untuk Vercel, kita tidak akan menjalankan scheduler secara langsung.
# Sebaliknya, kita akan setup Cron Job di vercel.json untuk trigger satu endpoint
# yang akan menjalankan fungsi send_auto_reports.
