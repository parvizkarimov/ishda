import logging
import os
import json
import httpx
from datetime import datetime, timedelta, timezone

def get_now():
    return datetime.now(timezone(timedelta(hours=5))).replace(tzinfo=None)
from typing import Optional, List
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine
import uvicorn
import math

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- SOZLAMALAR ---
# Railway Environment Variables dan olish
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_ID")

# Ofis kordinatalari (Samarqand)
OFFICE_LAT = 39.633670
OFFICE_LON = 66.919948
MAX_DISTANCE_METERS = 300 # 300 metr radiusda ruxsat beriladi

# Ma'lumotlar bazasi sozlamalari
# Railway'da PostgreSQL bo'lsa uni oladi, bo'lmasa SQLite ishlatadi
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./ishda.db"

# Ma'lumotlar bazasi ulanishini tekshirish
db_type = "PostgreSQL" if DATABASE_URL.startswith("postgresql") else "SQLite"
logger.info(f"--- FOYDALANILAYOTGAN BAZA: {db_type} ---")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODELLAR ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    username = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    face_descriptor = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_now)

class Attendance(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action_type = Column(String)
    timestamp = Column(DateTime, default=get_now)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    distance = Column(Float, nullable=True)
    face_match = Column(Float, nullable=True)
    photo_path = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

# --- MIGRATION (Ustunlar yo'q bo'lsa qo'shish) ---
def migrate_db():
    with engine.connect() as conn:
        # Attendance table
        for column in ["lat", "lon", "distance", "photo_path", "face_match"]:
            try:
                if column == "photo_path":
                    conn.execute(f"ALTER TABLE attendance ADD COLUMN {column} TEXT")
                else:
                    conn.execute(f"ALTER TABLE attendance ADD COLUMN {column} FLOAT")
                logger.info(f"Column {column} added to attendance table")
            except: pass
        
        # Users table
        for column in ["username", "phone_number"]:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT")
                logger.info(f"Column {column} added to users table")
            except: pass

migrate_db()

# static_path ni yuqoriroqda e'lon qilamiz
static_path = os.path.join(os.path.dirname(__file__), "static")

# Rasmlar uchun papka
UPLOAD_DIR = os.path.join(static_path, "uploads")
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func

# --- FUNKSIYALAR ---
async def send_daily_report():
    db = SessionLocal()
    try:
        now = get_now()
        today = now.date()
        # Bugungi barcha davomatlarni olish
        attendances = db.query(Attendance, User).join(User, Attendance.user_id == User.id)\
            .filter(func.date(Attendance.timestamp) == today)\
            .order_by(Attendance.timestamp.asc()).all()

        if not attendances:
            await send_telegram_notification(f"📅 <b>{today}</b> uchun davomat ma'lumotlari mavjud emas.")
            return

        # Ma'lumotlarni foydalanuvchilar bo'yicha guruhlash
        report_data = {}
        for a, u in attendances:
            if u.id not in report_data:
                report_data[u.id] = {"name": u.full_name, "in": "---", "out": "---"}
            
            time_str = a.timestamp.strftime("%H:%M")
            if a.action_type == "in" and report_data[u.id]["in"] == "---":
                report_data[u.id]["in"] = time_str
            elif a.action_type == "out":
                report_data[u.id]["out"] = time_str

        # Xabarni shakllantirish
        msg = f"📅 <b>Kunlik hisobot ({today}):</b>\n\n"
        for i, (uid, data) in enumerate(report_data.items(), 1):
            msg += f"{i}. <b>{data['name']}</b>\n   📥 {data['in']} | 📤 {data['out']}\n"
        
        await send_telegram_notification(msg)
    finally:
        db.close()

async def send_telegram_notification(message: str):
    if not BOT_TOKEN or "YOUR_BOT_TOKEN" in BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "HTML"})
        except Exception as e:
            logger.error(f"Telegram error: {e}")

async def send_telegram_photo(photo_path: str, caption: str):
    if not BOT_TOKEN or not ADMIN_CHAT_ID: return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    async with httpx.AsyncClient() as client:
        try:
            with open(photo_path, "rb") as photo:
                files = {"photo": photo}
                data = {"chat_id": ADMIN_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
                await client.post(url, data=data, files=files)
        except Exception as e:
            logger.error(f"Telegram photo error: {e}")

# --- SCHEDULER ---
scheduler = AsyncIOScheduler()
scheduler.add_job(send_daily_report, 'cron', hour=19, minute=0)

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000 # Yer radiusi metrda
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# --- APP SOZLAMALARI ---
app = FastAPI(title="Ishda API")
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.on_event("startup")
async def startup_event():
    # Schedulerni ishga tushirish
    scheduler.start()
    
    # Webhookni avtomat sozlash (agar PUBLIC_URL bo'lsa)
    public_url = os.environ.get("PUBLIC_URL")
    if public_url and BOT_TOKEN:
        webhook_url = f"{public_url.rstrip('/')}/webhook"
        set_webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
        async with httpx.AsyncClient() as client:
            try:
                res = await client.get(set_webhook_url)
                logger.info(f"Webhook setup status: {res.json()}")
            except Exception as e:
                logger.error(f"Webhook setup error: {e}")

    # Deploy bo'lganda adminga xabar yuborish
    msg = "🚀 <b>Tizim xabari:</b>\nLoyiha muvaffaqiyatli yangilandi va ishga tushdi!\n\n<i>Kunlik hisobot har kuni 19:00 da yuboriladi.</i>"
    await send_telegram_notification(msg)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- SCHEMAS ---
class AttendanceAction(BaseModel):
    user_id: int
    user_name: str
    action_type: str # 'in' or 'out'
    lat: Optional[float] = None
    lon: Optional[float] = None
    image: Optional[str] = None
    face_match: Optional[float] = None # Base64 image

class RegisterFace(BaseModel):
    user_id: int
    user_name: str
    face_descriptor: List[float]

# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def read_index():
    return FileResponse(os.path.join(static_path, "index.html"))

@app.get("/admin", response_class=HTMLResponse)
async def read_admin():
    return FileResponse(os.path.join(static_path, "admin.html"))

@app.post("/api/register")
async def register_user(data: RegisterFace, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        user = User(id=data.user_id, full_name=data.user_name)
        db.add(user)
    user.face_descriptor = json.dumps(data.face_descriptor)
    db.commit()
    return {"ok": True, "message": "Ro'yxatdan o'tdingiz"}

@app.post("/api/attendance")
async def record_attendance(data: AttendanceAction, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user: return {"ok": False, "message": "Avval ro'yxatdan o'ting"}

    # Rasmni saqlash
    photo_filename = None
    if data.image:
        import base64
        import uuid
        try:
            header, encoded = data.image.split(",", 1)
            data_bytes = base64.b64decode(encoded)
            photo_filename = f"{uuid.uuid4()}.jpg"
            with open(os.path.join(UPLOAD_DIR, photo_filename), "wb") as f:
                f.write(data_bytes)
        except Exception as e:
            logger.error(f"Image save error: {e}")

    dist = None
    if data.lat and data.lon:
        dist = calculate_distance(data.lat, data.lon, OFFICE_LAT, OFFICE_LON)
        if dist > MAX_DISTANCE_METERS:
            return {"ok": False, "message": f"Siz ofisdan juda uzoqdasiz ({int(dist)}m)"}

    new_record = Attendance(
        user_id=data.user_id, 
        action_type=data.action_type, 
        lat=data.lat, 
        lon=data.lon, 
        distance=dist,
        face_match=data.face_match,
        photo_path=photo_filename
    )
    db.add(new_record)
    db.commit()

    action_str = "Keldi" if data.action_type == "in" else "Ketdi"
    now_str = get_now().strftime('%H:%M:%S')
    match_str = f"{int(data.face_match)}%" if data.face_match else "?"
    msg = f"🔔 <b>Davomat:</b>\n👤 Xodim: {data.user_name}\n🚀 Holat: {action_str}\n📍 Masofa: {int(dist) if dist else '?'}m\n🧬 O'xshashlik: {match_str}\n⏰ Vaqt: {now_str}"
    
    if photo_filename:
        full_photo_path = os.path.join(UPLOAD_DIR, photo_filename)
        await send_telegram_photo(full_photo_path, msg)
    else:
        await send_telegram_notification(msg)

    return {"ok": True, "message": f"{action_str} qayd etildi", "time": now_str}

@app.get("/api/history/{user_id}")
async def get_user_history(user_id: int, db: Session = Depends(get_db)):
    today = get_now().date()
    records = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        func.date(Attendance.timestamp) == today
    ).order_by(Attendance.timestamp.asc()).all()
    
    first_in = None
    last_action = None
    total_seconds = 0
    temp_in_time = None
    
    log = []
    for r in records:
        log.append({
            "type": r.action_type,
            "time": r.timestamp.strftime("%H:%M:%S")
        })
        if r.action_type == "in":
            if not first_in: first_in = r.timestamp.strftime("%H:%M:%S")
            temp_in_time = r.timestamp
            last_action = "in"
        else:
            if temp_in_time:
                diff = r.timestamp - temp_in_time
                total_seconds += diff.total_seconds()
                temp_in_time = None
            last_action = "out"

    if last_action == "in" and temp_in_time:
        diff = get_now() - temp_in_time
        total_seconds += diff.total_seconds()

    return {
        "ok": True,
        "first_in": first_in,
        "last_action": last_action,
        "total_seconds": int(total_seconds),
        "log": log
    }

@app.get("/api/admin/all")
async def get_all_attendance(filter: Optional[str] = "today", db: Session = Depends(get_db)):
    # Admin panel uchun ma'lumotlarni filterlash
    query = db.query(Attendance, User).join(User, Attendance.user_id == User.id)
    
    today = datetime.now().date()
    if filter == "today":
        query = query.filter(func.date(Attendance.timestamp) == today)
    elif filter == "yesterday":
        from datetime import timedelta
        yesterday = today - timedelta(days=1)
        query = query.filter(func.date(Attendance.timestamp) == yesterday)
    # "all" bo'lsa hamma ma'lumotlarni qaytaradi

    results = query.order_by(Attendance.timestamp.asc()).all()
    
    # Guruhlash logikasi (Sana + UserID bo'yicha)
    grouped = {}
    for a, u in results:
        date_str = a.timestamp.strftime("%Y-%m-%d")
        key = f"{date_str}_{u.id}"
        
        if key not in grouped:
            grouped[key] = {
                "name": u.full_name,
                "date": date_str,
                "in_time": "-",
                "out_time": "-",
                "in_photo": None,
                "out_photo": None,
                "distance": a.distance,
                "face_match": a.face_match
            }
        
        time_str = a.timestamp.strftime("%H:%M:%S")
        if a.action_type == "in":
            grouped[key]["in_time"] = time_str
            grouped[key]["in_photo"] = f"/static/uploads/{a.photo_path}" if a.photo_path else None
            grouped[key]["face_match"] = a.face_match # Kelgan vaqtdagi o'xshashlikni ko'rsatamiz
        else:
            grouped[key]["out_time"] = time_str
            grouped[key]["out_photo"] = f"/static/uploads/{a.photo_path}" if a.photo_path else None

    # Ro'yxatni teskari tartibda qaytarish
    final_list = list(grouped.values())
    final_list.reverse()
    return final_list

@app.get("/api/admin/users")
async def get_all_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{
        "id": u.id,
        "name": u.full_name,
        "username": u.username,
        "phone": u.phone_number,
        "created_at": u.created_at.strftime("%Y-%m-%d")
    } for u in users]

@app.get("/api/user/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"ok": False, "message": "Foydalanuvchi topilmadi"}
    return {
        "ok": True,
        "full_name": user.full_name,
        "face_descriptor": json.loads(user.face_descriptor) if user.face_descriptor else None
    }

@app.post("/api/fraud_alert")
async def fraud_alert(data: AttendanceAction):
    now_str = get_now().strftime('%H:%M:%S')
    msg = f"⚠️ <b>SHUBHALI FAOLLIK!</b>\n👤 Xodim: {data.user_name}\n🚫 Holat: Begona inson xodim o'rniga kirishga urindi!\n⏰ Vaqt: {now_str}"
    await send_telegram_notification(msg)
    return {"ok": True}

@app.post("/webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        
        if text == "/start":
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": "Xush kelibsiz! Davomat tizimidan foydalanish uchun telefon raqamingizni yuboring:",
                "reply_markup": {
                    "keyboard": [[{"text": "📱 Kontaktni ulash", "request_contact": True}]],
                    "one_time_keyboard": True,
                    "resize_keyboard": True
                }
            }
            async with httpx.AsyncClient() as client:
                await client.post(url, json=payload)
        
        elif "contact" in msg:
            contact = msg["contact"]
            user_id = msg["from"]["id"] # Doim xavfsiz id
            phone = contact["phone_number"]
            username = msg["from"].get("username", "")
            first_name = msg["from"].get("first_name", "")
            last_name = msg["from"].get("last_name", "")
            full_name = f"{first_name} {last_name}".strip()
            
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                user = User(id=user_id, full_name=full_name)
                db.add(user)
            
            user.phone_number = phone
            user.username = username
            db.commit()
            
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": "✅ Rahmat! Ma'lumotlaringiz saqlandi. Endi ilovadan bemalol foydalanishingiz mumkin.",
                "reply_markup": {"remove_keyboard": True}
            }
            async with httpx.AsyncClient() as client:
                await client.post(url, json=payload)
                
    return {"ok": True}

@app.get("/api/history/{user_id}")
async def get_history(user_id: int, db: Session = Depends(get_db)):
    history = db.query(Attendance).filter(Attendance.user_id == user_id).order_by(Attendance.timestamp.desc()).limit(10).all()
    return {"ok": True, "history": [{"type": h.action_type, "time": h.timestamp.strftime("%H:%M:%S")} for h in history]}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
