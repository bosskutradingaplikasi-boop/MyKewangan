from datetime import datetime, timedelta
import pytz
from collections import defaultdict
import database as db

TIMEZONE = db.TIMEZONE

def generate_report_text(user_id: int, period: str):
    tz = pytz.timezone(TIMEZONE)
    today = datetime.now(tz).date()

    if period == 'harian':
        start_date = today
        title = f"📅 Laporan Harian ({today.strftime('%d %b %Y')})"
    elif period == 'mingguan':
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
        title = f"📅 Laporan Mingguan ({start_date.strftime('%d %b')} – {end_date.strftime('%d %b %Y')})"
    elif period == 'bulanan':
        start_date = today.replace(day=1)
        title = f"📅 Laporan Bulanan ({start_date.strftime('%B %Y')})"
    else:
        return "Tempoh laporan tidak sah. Sila pilih: harian, mingguan, bulanan."

    with next(db.get_db()) as conn:
        transactions = db.get_transactions(conn, user_id, period)
        balance = db.get_balance(conn, user_id)

    if not transactions:
        return f"{title}\n\nTiada transaksi direkodkan dalam tempoh ini."

    total_masuk = 0.0
    total_keluar = 0.0
    kategori_totals = defaultdict(float)

    for t in transactions:
        if t.jenis == 'masuk':
            total_masuk += t.amaun
        elif t.jenis == 'keluar':
            total_keluar += t.amaun
            if t.kategori:
                kategori_totals[t.kategori] += t.amaun

    report_lines = [
        title,
        f"💰 Masuk: RM{total_masuk:.2f}",
        f"💸 Keluar: RM{total_keluar:.2f}",
        f"⚖️ Baki Semasa: RM{balance:.2f}",
    ]

    if kategori_totals:
        report_lines.append("\n📊 Pecahan Kategori Keluar:")
        # Sort categories by amount, descending
        sorted_kategori = sorted(kategori_totals.items(), key=lambda item: item[1], reverse=True)
        for kategori, amaun in sorted_kategori:
            report_lines.append(f"- {kategori.capitalize()}: RM{amaun:.2f}")
            
    return "\n".join(report_lines)
