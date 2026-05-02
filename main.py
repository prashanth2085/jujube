import sqlite3, json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

app = FastAPI()

# Database Setup
conn = sqlite3.connect('chat_history.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS rooms (password TEXT PRIMARY KEY, room_name TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, sender TEXT, avatar TEXT, ciphertext TEXT, password TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
conn.commit()

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

@app.get("/history/{password}")
async def get_history(password: str):
    cursor.execute("DELETE FROM messages WHERE created_at <= datetime('now', '-48 hours')")
    cursor.execute("SELECT id, sender, avatar, ciphertext FROM messages WHERE password = ? ORDER BY created_at ASC", (password,))
    return [{"id": r[0], "sender": r[1], "avatar": r[2], "ciphertext": r[3], "type": "message"} for r in cursor.fetchall()]

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            if payload.get("type") == "join":
                cursor.execute("SELECT room_name FROM rooms WHERE password = ?", (payload['password'],))
                res = cursor.fetchone()
                await websocket.send_text(json.dumps({"type": "room_info", "room_name": res[0] if res else None}))

            elif payload.get("type") == "create_room":
                cursor.execute("INSERT OR IGNORE INTO rooms (password, room_name) VALUES (?, ?)", (payload['password'], payload['room_name']))
                conn.commit()

            elif payload.get("type") == "message":
                cursor.execute("INSERT INTO messages (id, sender, avatar, ciphertext, password) VALUES (?, ?, ?, ?, ?)",
                    (payload['id'], payload['sender'], payload['avatar'], payload['ciphertext'], payload['password']))
                conn.commit()
                await manager.broadcast(data)

            elif payload.get("type") == "delete":
                cursor.execute("DELETE FROM messages WHERE id = ?", (payload['id'],))
                conn.commit()
                await manager.broadcast(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
