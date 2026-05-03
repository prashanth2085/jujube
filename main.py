import sqlite3
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

app = FastAPI()

# --- DATABASE SETUP ---
conn = sqlite3.connect('chat_history.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        sender TEXT,
        avatar TEXT,
        ciphertext TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.commit()

def clean_old_messages():
    cursor.execute("DELETE FROM messages WHERE created_at <= datetime('now', '-48 hours')")
    conn.commit()

# --- WEBSOCKET MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Remove dead connections
                self.disconnect(connection)

manager = ConnectionManager()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/history")
async def get_history():
    clean_old_messages()
    cursor.execute("SELECT id, sender, avatar, ciphertext FROM messages ORDER BY created_at ASC")
    rows = cursor.fetchall()
    return [{"id": r[0], "sender": r[1], "avatar": r[2], "ciphertext": r[3], "type": "message"} for r in rows]

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            
            # 1. Immediate Broadcast
            await manager.broadcast(data)
            
            # 2. Database Handling
            try:
                payload = json.loads(data)
                if payload.get("type") == "message":
                    cursor.execute(
                        "INSERT OR IGNORE INTO messages (id, sender, avatar, ciphertext) VALUES (?, ?, ?, ?)",
                        (payload.get("id"), payload.get("sender"), payload.get("avatar"), payload.get("ciphertext"))
                    )
                    conn.commit()
            except:
                pass # Ignore pings or malformed data
    except WebSocketDisconnect:
        manager.disconnect(websocket)
