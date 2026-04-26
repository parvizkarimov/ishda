import logging
import os
import json
import httpx
from datetime import datetime
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
# Telegram Bot sozlamalari (Bularni o'zingizniki bilan almashtirishingiz mumkin)
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_CHAT_ID = "YOUR_ADMIN_CHAT_ID_HERE"

# Ofis kordinatalari (Masalan: Toshkent, Amity University hududi)
OFFICE_LAT = 41.3387
OFFICE_LON = 69.3348
MAX_DISTANCE_METERS = 200 # 200 metr radiusda ruxsat beriladi

# Ma'lumotlar bazasi sozlamalari
DATABASE_URL = "sqlite:///./ishda.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODELLAR ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    face_descriptor = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class Attendance(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action_type = Column(String)
    timestamp = Column(DateTime, default=datetime.now)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    distance = Column(Float, nullable=True)

Base.metadata.create_all(bind=engine)

# --- FUNKSIYALAR ---
async def send_telegram_notification(message: str):
    if "YOUR_BOT_TOKEN" in BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "HTML"})
        except Exception as e:
            logger.error(f"Telegram error: {e}")

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000 # Yer radiusi metrda
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# --- APP SOZLAMALARI ---
app = FastAPI(title="Ishda API")
static_path = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- SCHEMAS ---
class AttendanceAction(BaseModel):
    user_id: int
    user_name: str
    action_type: str
    lat: Optional[float] = None
    lon: Optional[float] = None

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

    dist = None
    if data.lat and data.lon:
        dist = calculate_distance(data.lat, data.lon, OFFICE_LAT, OFFICE_LON)
        if dist > MAX_DISTANCE_METERS:
            return {"ok": False, "message": f"Siz ofisdan juda uzoqdasiz ({int(dist)}m)"}

    new_record = Attendance(user_id=data.user_id, action_type=data.action_type, lat=data.lat, lon=data.lon, distance=dist)
    db.add(new_record)
    db.commit()

    action_str = "Keldi" if data.action_type == "in" else "Ketdi"
    msg = f"🔔 <b>Davomat:</b>\n👤 Xodim: {data.user_name}\n🚀 Holat: {action_str}\n📍 Masofa: {int(dist) if dist else '?'}m\n⏰ Vaqt: {datetime.now().strftime('%H:%M:%S')}"
    await send_telegram_notification(msg)

    return {"ok": True, "message": f"{action_str} qayd etildi", "time": datetime.now().strftime("%H:%M:%S")}

@app.get("/api/admin/all")
async def get_all_attendance(db: Session = Depends(get_db)):
    # Admin panel uchun barcha ma'lumotlar
    results = db.query(Attendance, User).join(User, Attendance.user_id == User.id).order_by(Attendance.timestamp.desc()).all()
    return [{
        "id": a.id,
        "name": u.full_name,
        "type": a.action_type,
        "time": a.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "distance": a.distance
    } for a, u in results]

@app.get("/api/history/{user_id}")
async def get_history(user_id: int, db: Session = Depends(get_db)):
    history = db.query(Attendance).filter(Attendance.user_id == user_id).order_by(Attendance.timestamp.desc()).limit(10).all()
    return {"ok": True, "history": [{"type": h.action_type, "time": h.timestamp.strftime("%H:%M:%S")} for h in history]}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
