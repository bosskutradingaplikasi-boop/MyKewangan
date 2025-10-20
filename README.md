# 💸 MyKewangan Telegram Bot

Sistem pengurusan perbelanjaan harian & laporan automatik — sepenuhnya melalui Telegram.

## 🚀 Ciri Utama
- Tambah duit masuk & keluar dengan mudah
- Kategori & nota perbelanjaan
- Laporan harian, mingguan & bulanan
- Auto laporan ke Telegram
- Tiada web UI, 100% Telegram

## ⚙️ Setup
1. Clone repo:
   ```bash
   git clone https://github.com/username/MyKewangan.git
   cd MyKewangan
   ```

2. Tambah `.env`:
   ```
   BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
   DATABASE_URL=sqlite:///mykewangan.db
   TIMEZONE=Asia/Kuala_Lumpur
   ```

3. Install:
   ```bash
   pip install -r requirements.txt
   ```

4. Jalankan:
   ```bash
   python main.py
   ```

## 🌐 Deploy ke Vercel

1. Push ke GitHub.
2. Deploy melalui Vercel.
3. Tambah `BOT_TOKEN` dan `DATABASE_URL` di Environment Variables.
4. Aktifkan webhook Telegram:
   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://your-vercel-url.vercel.app/`

Siap 🎉

## 📲 Command Telegram
| Command | Fungsi |
|---|---|
| `/belanja` | Tambah perbelanjaan |
| `/masuk` | Tambah pendapatan |
| `/laporan` | Lihat laporan |
| `/baki` | Semak baki |
| `/padam` | Padam transaksi |
| `/help` | Bantuan |

---

🧑‍💻 Dibangunkan oleh Bossku System Dev
📅 Versi 1.0 – MyKewanganBot
