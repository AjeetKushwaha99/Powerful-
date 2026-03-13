import os
import asyncio
import requests
from datetime import datetime, timedelta, timezone
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import FloodWait
from pymongo import MongoClient

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
API_ID = 37067823
API_HASH = "ed9e62ed4538d2d2b835fb54529c358f"

BOT_MODE = os.environ.get("BOT_MODE", "primary").lower()
USER_BOT_PRIMARY_TOKEN = "8537476620:AAHf1XxjpjFGJICxNAQ4i9A06gN0Z0ephDk"
USER_BOT_BACKUP_TOKEN = "7788869673:AAHheU98TueCNHmfOf6GERSHWEp9QwETyho"
BOT_TOKEN = USER_BOT_PRIMARY_TOKEN if BOT_MODE == "primary" else USER_BOT_BACKUP_TOKEN

# 🔥 DUAL CHANNEL SYSTEM
CHANNEL_PRIMARY = -1003777551559
CHANNEL_BACKUP = -1003867841066

MONGO_URL = "mongodb+srv://Ajeet:XgGFRFWVT2NwWipw@cluster0.3lxz0p7.mongodb.net/?appName=Cluster0"
SHORTENER_API = "5cbb1b2088d2ed06d7e9feae35dc17cc033169d6"
SHORTENER_URL = "vplink.in"
HELP_CHANNEL = "https://t.me/+fDEEztGJQIY5MGY1"

VERIFICATION_HOURS = 26
FREE_DAILY_LIMIT = 1
AUTO_DELETE_HOURS = 2

# ==========================================
# 🗄️ DATABASE
# ==========================================
mongo_client = MongoClient(MONGO_URL, maxPoolSize=50, serverSelectionTimeoutMS=5000)
db = mongo_client["FileSharingPro"]

users_col = db["users"]
files_col = db["files"]
verifications_col = db["verifications"]
stats_col = db["stats"]
pending_deletes_col = db["pending_deletes"]

app = Client(f"user_bot_{BOT_MODE}", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==========================================
# 🛡️ PERSISTENT AUTO-DELETE
# ==========================================
async def persistent_auto_delete_loop():
    print(f"🔄 Persistent Auto-Delete System Active on {BOT_MODE.upper()}")
    while True:
        try:
            now = datetime.now(timezone.utc)
            expired_docs = pending_deletes_col.find({"delete_at": {"$lte": now}})
            
            for doc in expired_docs:
                try:
                    await app.delete_messages(doc["chat_id"], doc["message_id"])
                    await app.send_message(doc["chat_id"], f"🗑️ **Security Notice:** Video auto-deleted after {AUTO_DELETE_HOURS} hours.")
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                except Exception:
                    pass
                pending_deletes_col.delete_one({"_id": doc["_id"]})
        except Exception as e:
            print(f"Delete loop error: {e}")
        await asyncio.sleep(60)

def generate_vplink(actual_link):
    try:
        res = requests.get(f"https://{SHORTENER_URL}/api", params={"api": SHORTENER_API, "url": actual_link}, timeout=5).json()
        return res.get("shortenedUrl", actual_link)
    except Exception:
        return actual_link

# ==========================================
# 🔧 HELPER FUNCTIONS
# ==========================================
def get_fresh_user(user_id):
    now = datetime.now(timezone.utc)
    user_data = users_col.find_one({"user_id": user_id})
    if not user_data:
        user_data = {
            "user_id": user_id,
            "videos_today": 0,
            "last_watch": now,
            "adult_accepted": False
        }
        users_col.insert_one(user_data)
    
    last_watch = user_data.get("last_watch", now)
    if hasattr(last_watch, 'date') and last_watch.date() < now.date():
        users_col.update_one({"user_id": user_id}, {"$set": {"videos_today": 0, "last_watch": now}})
        user_data["videos_today"] = 0
        user_data["last_watch"] = now
    
    return user_data

def is_user_verified(user_id):
    now = datetime.now(timezone.utc)
    verif = verifications_col.find_one({"user_id": user_id})
    if verif and verif.get("expires_at"):
        expires = verif["expires_at"]
        if hasattr(expires, 'tzinfo') and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires > now:
            return True
    return False

# ==========================================
# 📩 START HANDLER
# ==========================================
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    payload = message.command[1] if len(message.command) > 1 else None
    now = datetime.now(timezone.utc)

    user_data = get_fresh_user(user_id)

    if not payload:
        return await message.reply(
            "👋 **Welcome to the File Bot!**\n\nSend a valid link to get started.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=HELP_CHANNEL)]
            ])
        )

    is_verified_now = False
    original_file_code = payload

    if payload.startswith("verify_"):
        original_file_code = payload.replace("verify_", "")
        
        verifications_col.update_one(
            {"user_id": user_id},
            {"$set": {"expires_at": now + timedelta(hours=VERIFICATION_HOURS)}},
            upsert=True
        )
        
        users_col.update_one(
            {"user_id": user_id},
            {"$set": {"videos_today": 0}}
        )
        
        await message.reply(
            f"✅ **Verification Successful!**\n\n"
            f"🎉 You now have **{VERIFICATION_HOURS} hours** unlimited access!\n"
            f"⏳ Fetching your file..."
        )
        is_verified_now = True
        user_data = get_fresh_user(user_id)

    if not user_data.get("adult_accepted"):
        users_col.update_one({"user_id": user_id}, {"$set": {"pending_file": original_file_code}})
        return await message.reply(
            "⚠️ **Adult Content Warning**\n\n"
            "This bot contains adult content.\n"
            "By clicking continue, you confirm you are **18+**.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✔️ I am 18+ - Continue", callback_data="accept_adult")],
                [InlineKeyboardButton("❌ Exit", callback_data="reject_adult")]
            ])
        )

    await process_file_delivery(client, message, user_id, original_file_code)

@app.on_callback_query(filters.regex("^accept_adult$"))
async def accept_adult(client, query: CallbackQuery):
    user_id = query.from_user.id
    
    users_col.update_one({"user_id": user_id}, {"$set": {"adult_accepted": True}})
    await query.message.edit_text("✅ **Warning accepted!**\n\n⏳ Fetching your file...")
    
    user_data = get_fresh_user(user_id)
    pending_file = user_data.get("pending_file")
    
    if pending_file:
        users_col.update_one({"user_id": user_id}, {"$unset": {"pending_file": ""}})
        await process_file_delivery(client, query.message, user_id, pending_file)
    else:
        await query.message.reply("👋 Send a valid file link to get started!")

@app.on_callback_query(filters.regex("^reject_adult$"))
async def reject_adult(client, query: CallbackQuery):
    await query.message.edit_text("❌ You have exited. You cannot use this bot.")

# ==========================================
# 🔥 DUAL CHANNEL FILE DELIVERY
# ==========================================
async def process_file_delivery(client, message, user_id, file_code):
    now = datetime.now(timezone.utc)
    
    user_data = get_fresh_user(user_id)
    
    file_data = files_col.find_one({"file_code": file_code})
    if not file_data:
        return await message.reply("❌ **Invalid or Expired File Code.**")

    verified = is_user_verified(user_id)

    if not verified and user_data.get("videos_today", 0) >= FREE_DAILY_LIMIT:
        bot_username = (await client.get_me()).username
        verify_url = generate_vplink(f"https://t.me/{bot_username}?start=verify_{file_code}")
        return await message.reply(
            f"🛑 **Daily Free Limit Reached!**\n\n"
            f"You have used your **{FREE_DAILY_LIMIT} free** video today.\n\n"
            f"✅ **Verify once** to get **{VERIFICATION_HOURS} hours** unlimited access!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Verify Now (Free)", url=verify_url)],
                [InlineKeyboardButton("❓ How To Verify", url=HELP_CHANNEL)]
            ])
        )

    # 🔥 DUAL CHANNEL: Try primary first, then backup
    delivered = False
    
    # Try 1: Use stored channel_id and message_id
    try:
        channel_id = file_data.get("channel_id", CHANNEL_PRIMARY)
        message_id = file_data.get("message_id")
        
        msg = await client.copy_message(
            chat_id=user_id,
            from_chat_id=channel_id,
            message_id=message_id,
            caption=f"📁 **Here is your file!**\n\n⚠️ Will auto-delete in **{AUTO_DELETE_HOURS} hours**.\n💾 Save/Download it quickly!",
            protect_content=True
        )
        delivered = True
    except Exception as e:
        print(f"Primary delivery failed: {e}")
    
    # Try 2: If primary failed, try backup channel message_id
    if not delivered and file_data.get("message_id_backup"):
        try:
            msg = await client.copy_message(
                chat_id=user_id,
                from_chat_id=CHANNEL_BACKUP,
                message_id=file_data["message_id_backup"],
                caption=f"📁 **Here is your file!**\n\n⚠️ Will auto-delete in **{AUTO_DELETE_HOURS} hours**.\n💾 Save/Download it quickly!",
                protect_content=True
            )
            delivered = True
        except Exception as e:
            print(f"Backup delivery failed: {e}")
    
    # Try 3: If backup also failed, try primary channel message_id
    if not delivered and file_data.get("message_id_primary"):
        try:
            msg = await client.copy_message(
                chat_id=user_id,
                from_chat_id=CHANNEL_PRIMARY,
                message_id=file_data["message_id_primary"],
                caption=f"📁 **Here is your file!**\n\n⚠️ Will auto-delete in **{AUTO_DELETE_HOURS} hours**.\n💾 Save/Download it quickly!",
                protect_content=True
            )
            delivered = True
        except Exception as e:
            print(f"All delivery attempts failed: {e}")
    
    if delivered:
        files_col.update_one({"file_code": file_code}, {"$inc": {"clicks": 1}})
        stats_col.update_one({"_id": "bot_stats"}, {"$inc": {"total_clicks": 1}})
        users_col.update_one(
            {"user_id": user_id},
            {"$inc": {"videos_today": 1}, "$set": {"last_watch": now}}
        )

        pending_deletes_col.insert_one({
            "chat_id": user_id,
            "message_id": msg.id,
            "delete_at": now + timedelta(hours=AUTO_DELETE_HOURS)
        })

        if verified:
            await message.reply("✅ **Verified User** - Unlimited access active!")
    else:
        await message.reply(
            "❌ **Error delivering file.**\n\nPlease try again later.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{(await client.get_me()).username}?start={file_code}")]
            ])
        )

# ==========================================
# 🚀 APP LAUNCHER
# ==========================================
if __name__ == "__main__":
    app.start()
    print(f"🚀 User Bot ({BOT_MODE.upper()}) Started Successfully!")
    print(f"📡 Primary Channel: {CHANNEL_PRIMARY}")
    print(f"📡 Backup Channel: {CHANNEL_BACKUP}")
    loop = asyncio.get_event_loop()
    loop.create_task(persistent_auto_delete_loop())
    idle()
