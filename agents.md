# 🚀 Ishda - Face ID Attendance System

Ushbu loyiha xodimlarning davomatini Face ID va Geofencing (geolokatsiya) yordamida nazorat qilish uchun mo'ljallangan.

## 🛠 Texnologik stek
- **Backend:** FastAPI (Python 3.10+)
- **Database:** PostgreSQL (Railway'da doimiy saqlanadi)
- **Frontend:** HTML5, Vanilla JS, CSS3 (Telegram WebApp)
- **Face ID:** `face-api.js` (Client-side detection & recognition)
- **Bot:** Telegram Bot API (httpx orqali)

## 🏗 Arxitektura
1. **Telegram WebApp:** Xodimlar yuzini skanerlaydi, geolokatsiyasini oladi va o'xshashlik foizini hisoblab serverga yuboradi.
2. **FastAPI Server:** Ma'lumotlarni qabul qiladi, masofani tekshiradi, rasmni saqlaydi va adminga xabar yuboradi.
3. **Admin Panel:** Kunlik davomatni (Keldi/Ketdi birlashtirilgan holda), xodimlar ro'yxatini va rasmlarni ko'rish imkonini beradi.

## 🔑 Muhim o'zgaruvchilar (Environment Variables)
- `BOT_TOKEN`: Telegram bot tokeni.
- `ADMIN_ID`: Adminning Telegram chat ID raqami.
- `PUBLIC_URL`: Loyihaning Railway'dagi manzili (masalan: `https://ishda-production.up.railway.app`).
- `DATABASE_URL`: PostgreSQL ulanish manzili.

## 📍 Muhim koordinatalar
- **Ofis manzili:** `39.633670, 66.919948` (Samarqand).
- **Radius:** 300 metr.

## 🕒 Vaqt zonasi
- Loyihada barcha vaqtlar **Uzbekistan Time (UTC+5)** standartida ishlaydi. 
- Kodda `get_now()` funksiyasi orqali boshqariladi.

## 🧠 Kelajakdagi agentlar uchun eslatmalar
- **Face API:** Modellar `https://justadudewhohacks.github.io/face-api.js/models` manzilidan yuklanadi.
- **Migration:** Ma'lumotlar bazasiga yangi ustun qo'shish `main.py` ichidagi `migrate_db()` funksiyasi orqali amalga oshiriladi.
- **Photos:** Rasmlar `static/uploads/` papkasida saqlanadi. Railway'da Volume ulanmagan bo'lsa, har deployda o'chib ketadi.

---
*Loyiha doimiy rivojlanishda. Oxirgi yangilanish: 2026-04-26*
