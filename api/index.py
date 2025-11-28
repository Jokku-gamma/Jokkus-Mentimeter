import os
import random
import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pydantic import BaseModel, Field
from typing import List
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

# --- Database Setup ---
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client.get_database("anon_chat_db")
rooms_collection = db.get_collection("rooms")
messages_collection = db.get_collection("messages")

# --- Models ---
class Room(BaseModel):
    room_code: str
    hostId: str
    createdAt: datetime.datetime = Field(default_factory=datetime.datetime.now)

class Message(BaseModel):
    id: str = Field(alias="_id")
    room_code: str
    text: str
    isCompleted: bool = False
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

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

# --- App ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def generate_room_code():
    chars = 'ABCDEFGHIJKLMNPQRSTUVWXYZ123456789'
    return ''.join(random.choice(chars) for _ in range(6))

@app.get("/api")
def api_root():
    return {"status": "ok"}

@app.post("/api/create_room")
def create_room(request: CreateRoomRequest):
    new_code = generate_room_code()
    while rooms_collection.find_one({"room_code": new_code}):
        new_code = generate_room_code()
    
    new_room = Room(room_code=new_code, hostId=request.hostId)
    rooms_collection.insert_one(new_room.dict())
    return new_room

@app.get("/api/join_room")
def join_room(room_code: str):
    room = rooms_collection.find_one({"room_code": room_code.upper()})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    room["_id"] = str(room["_id"])
    return room

@app.post("/api/send_message")
def send_message(request: SendMessageRequest):
    message_data = {
        "room_code": request.room_code.upper(),
        "text": request.text,
        "isCompleted": False,
        "timestamp": datetime.datetime.now()
    }
    result = messages_collection.insert_one(message_data)
    return {"status": "ok", "message_id": str(result.inserted_id)}

@app.get("/api/get_messages")
def get_messages(room_code: str):
    messages = list(messages_collection.find({"room_code": room_code.upper()}).sort("timestamp", 1))
    for msg in messages:
        msg['_id'] = str(msg['_id'])
    return messages

@app.put("/api/toggle_message")
def toggle_message(request: ToggleMessageRequest):
    try:
        msg_id = ObjectId(request.message_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID")
    result = messages_collection.update_one({"_id": msg_id}, {"$set": {"isCompleted": request.is_completed}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": "ok"}

@app.delete("/api/delete_message")
def delete_message(request: DeleteMessageRequest):
    try:
        msg_id = ObjectId(request.message_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID")
    messages_collection.delete_one({"_id": msg_id})
    return {"status": "ok"}