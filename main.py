import sqlite3
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

app = FastAPI()

# --- DATABASE SETUP ---
# This creates a file named 'chat_history.db' in your folder
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
    # The magic 48-hour auto-delete logic
    cursor.execute("DELETE FROM messages WHERE created_at <= datetime('now', '-48 hours')")
    conn.commit()

# --- WEBSOCKET SETUP ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

# --- NEW: HISTORY ENDPOINT ---
@app.get("/history")
async def get_history():
    clean_old_messages() # Delete old stuff before showing history
    cursor.execute("SELECT id, sender, avatar, ciphertext FROM messages ORDER BY created_at ASC")
    rows = cursor.fetchall()
    
    history = []
    for row in rows:
        history.append({
            "id": row[0],
            "sender": row[1],
            "avatar": row[2],
            "ciphertext": row[3],
            "type": "message"
        })
    return history

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            # If it's a new message, save the encrypted gibberish to the database
            if payload.get("type") == "message":
                cursor.execute(
                    "INSERT OR IGNORE INTO messages (id, sender, avatar, ciphertext) VALUES (?, ?, ?, ?)",
                    (payload.get("id"), payload.get("sender"), payload.get("avatar"), payload.get("ciphertext"))
                )
                conn.commit()
                clean_old_messages()
                
            await manager.broadcast(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
