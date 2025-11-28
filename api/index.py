import os
import random
import string
import datetime
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pymongo import MongoClient
from pymongo.collection import Collection
from pydantic import BaseModel, Field
from typing import List, Optional
from bson import ObjectId
from dotenv import load_dotenv
import pathlib

# Load .env file for local development
# Vercel will use environment variables set in the dashboard
load_dotenv()

# --- Database Setup ---
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    # This will be visible in Vercel logs if the env var is missing
    print("WARNING: MONGO_URI environment variable not set.")
    
client = MongoClient(MONGO_URI)
db = client.get_database("anon_chat_db") # You can name this anything

rooms_collection: Collection = db.get_collection("rooms")
messages_collection: Collection = db.get_collection("messages")

# --- Pydantic Models (Data Validation) ---
class Room(BaseModel):
    room_code: str
    hostId: str
    createdAt: datetime.datetime = Field(default_factory=datetime.datetime.now)

class Message(BaseModel):
    id: str = Field(alias="_id") # To map MongoDB's _id
    room_code: str
    text: str
    isCompleted: bool = False
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        validate_by_name = True

# Request body models
class CreateRoomRequest(BaseModel):
    hostId: str

class SendMessageRequest(BaseModel):
    room_code: str
    text: str

class ToggleMessageRequest(BaseModel):
    message_id: str
    is_completed: bool

class DeleteMessageRequest(BaseModel):
    message_id: str

# --- FastAPI App ---
# Vercel looks for an 'app' variable
app = FastAPI()

# Get the directory containing index.py
current_dir = pathlib.Path(__file__).parent
static_dir = current_dir

# Mount the static files directory
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# --- CORS Middleware ---
# This allows your frontend (on a different domain) to talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins (you can restrict this in production)
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# --- Helper Functions ---
def generate_room_code():
    chars = 'ABCDEFGHIJKLMNPQRSTUVWXYZ123456789'
    return ''.join(random.choice(chars) for _ in range(6))

# --- API Endpoints ---

# Serve the main HTML file at the root
@app.get("/")
async def read_index():
    return FileResponse(str(static_dir / "index.html"))

# Vercel requires this root endpoint for health checks
@app.get("/api")
def api_root():
    return {"status": "ok", "message": "Anon-Sphere API is running."}

@app.post("/api/create_room")
def create_room(request: CreateRoomRequest):
    """Creates a new chat room and stores it in the database."""
    new_code = generate_room_code()
    # Ensure code is unique
    while rooms_collection.find_one({"room_code": new_code}):
        new_code = generate_room_code()
    
    new_room = Room(
        room_code=new_code,
        hostId=request.hostId
    )
    
    rooms_collection.insert_one(new_room.dict())
    return new_room

@app.get("/api/join_room")
def join_room(room_code: str):
    """Checks if a room exists and returns its data."""
    room = rooms_collection.find_one({"room_code": room_code.upper()})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    # Convert MongoDB's _id to string
    room["_id"] = str(room["_id"])
    return room

@app.post("/api/send_message")
def send_message(request: SendMessageRequest):
    """Saves a new anonymous message to the database."""
    message_data = {
        "room_code": request.room_code.upper(),
        "text": request.text,
        "isCompleted": False,
        "timestamp": datetime.datetime.now()
    }
    result = messages_collection.insert_one(message_data)
    return {"status": "ok", "message_id": str(result.inserted_id)}

@app.get("/api/get_messages", response_model=List[Message])
def get_messages(room_code: str):
    """Gets all messages for a specific room, sorted by time."""
    messages = list(messages_collection.find(
        {"room_code": room_code.upper()}
    ).sort("timestamp", 1)) # 1 for ascending
    
    # Manually map _id to id
    for msg in messages:
        msg['_id'] = str(msg['_id'])
        
    return messages

@app.put("/api/toggle_message")
def toggle_message(request: ToggleMessageRequest):
    """Host: Marks a message as completed or incomplete."""
    try:
        msg_id = ObjectId(request.message_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid message_id")
        
    result = messages_collection.update_one(
        {"_id": msg_id},
        {"$set": {"isCompleted": request.is_completed}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "ok"}

@app.delete("/api/delete_message")
def delete_message(request: DeleteMessageRequest):
    """Host: Deletes a message."""
    try:
        msg_id = ObjectId(request.message_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid message_id")

    result = messages_collection.delete_one({"_id": msg_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "ok"}
