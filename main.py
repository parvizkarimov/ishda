import logging
import os
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Ishda API")

# Static fayllarni ulash (index.html va h.k.)
static_path = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")

class AttendanceAction(BaseModel):
    user_id: int
    user_name: str
    action_type: str # "in" yoki "out"
    face_data: Optional[str] = None # Yuz skaneri natijasi (base64 yoki embedding)

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(os.path.join(static_path, "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/attendance")
async def record_attendance(data: AttendanceAction):
    now = datetime.now()
    action_str = "Keldi" if data.action_type == "in" else "Ketdi"
    
    logger.info(f"Attendance: {data.user_name} ({data.user_id}) - {action_str} at {now}")
    
    # Kelajakda bu yerda ma'lumotlar bazasiga yoziladi
    return {
        "ok": True,
        "message": f"{action_str} muvaffaqiyatli qayd etildi",
        "time": now.strftime("%H:%M:%S")
    }

@app.get("/api/history/{user_id}")
async def get_history(user_id: int):
    # Placeholder tarix
    return {
        "ok": True,
        "history": [
            {"date": "2026-04-25", "in": "09:00", "out": "18:05"},
            {"date": "2026-04-24", "in": "08:55", "out": "18:10"}
        ]
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
