import logging
import os
import json
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine
import uvicorn

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ma'lumotlar bazasi sozlamalari
DATABASE_URL = "sqlite:///./ishda.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODELLAR ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True) # Telegram User ID
    full_name = Column(String)
    face_descriptor = Column(Text, nullable=True) # Yuz izi (JSON string)
    created_at = Column(DateTime, default=datetime.now)

class Attendance(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action_type = Column(String) # "in" yoki "out"
    timestamp = Column(DateTime, default=datetime.now)

Base.metadata.create_all(bind=engine)

# --- APP SOZLAMALARI ---
app = FastAPI(title="Ishda API")
static_path = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- SCHEMAS ---
class AttendanceAction(BaseModel):
    user_id: int
    user_name: str
    action_type: str
    face_descriptor: Optional[List[float]] = None

class RegisterFace(BaseModel):
    user_id: int
    user_name: str
    face_descriptor: List[float]

# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_file = os.path.join(static_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Index file not found")

@app.post("/api/register")
async def register_user(data: RegisterFace, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        user = User(id=data.user_id, full_name=data.user_name)
        db.add(user)
    
    user.face_descriptor = json.dumps(data.face_descriptor)
    db.commit()
    return {"ok": True, "message": "Yuz muvaffaqiyatli ro'yxatga olindi"}

@app.post("/api/attendance")
async def record_attendance(data: AttendanceAction, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        return {"ok": False, "message": "Avval ro'yxatdan o'ting"}

    # Bu yerda kelajakda backendda ham face verification qilish mumkin
    # Hozircha frontend tasdiqlashiga ishonamiz
    
    new_record = Attendance(user_id=data.user_id, action_type=data.action_type)
    db.add(new_record)
    db.commit()
    
    action_str = "Keldi" if data.action_type == "in" else "Ketdi"
    return {
        "ok": True, 
        "message": f"{action_str} qayd etildi",
        "time": datetime.now().strftime("%H:%M:%S")
    }

@app.get("/api/history/{user_id}")
async def get_history(user_id: int, db: Session = Depends(get_db)):
    history = db.query(Attendance).filter(Attendance.user_id == user_id).order_by(Attendance.timestamp.desc()).limit(10).all()
    return {
        "ok": True,
        "history": [{"type": h.action_type, "time": h.timestamp.strftime("%Y-%m-%d %H:%M:%S")} for h in history]
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
