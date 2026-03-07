import asyncio
import string
import random
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, PeerIdInvalid
from pymongo import MongoClient

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
API_ID = 37067823
API_HASH = "ed9e62ed4538d2d2b835fb54529c358f"

ADMIN_BOT_TOKEN = "8596951434:AAF98nta7kfLKqeR9ImT5pUCTZoZ1rLFOwI"
USER_BOT_PRIMARY_USERNAME = "Filling4You_bot"
USER_BOT_BACKUP_USERNAME = "FiLing4YoU_bot"

CHANNEL_ID = -1003777551559
OWNER_ID = 6549083920

# MongoDB Connection (Optimized for High Traffic)
MONGO_URL = "mongodb+srv://Ajeet:XgGFRFWVT2NwWipw@cluster0.3lxz0p7.mongodb.net/?appName=Cluster0"

# ==========================================
# 🗄️ DATABASE CONNECTION
# ==========================================
mongo_client = MongoClient(MONGO_URL, maxPoolSize=50, serverSelectionTimeoutMS=5000)
db = mongo_client["FileSharingPro"]

users_col = db["users"]
files_col = db["files"]
stats_col = db["stats"]

if stats_col.find_one({"_id": "bot_stats"}) is None:
    stats_col.insert_one({"_id": "bot_stats", "total_clicks": 0, "active_bot": "primary"})

# ==========================================
# 🤖 BOT INITIALIZATION
# ==========================================
app = Client("admin_bot", api_id=API_ID, api_hash=API_HASH, bot_token=ADMIN_BOT_TOKEN)

def generate_file_code(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def get_active_bot_username():
    stats = stats_col.find_one({"_id": "bot_stats"})
    if stats and stats.get("active_bot") == "backup":
        return USER_BOT_BACKUP_USERNAME
    return USER_BOT_PRIMARY_USERNAME

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    if message.from_user.id != OWNER_ID: return
    await message.reply("🤖 **Premium Admin Panel**\n\nSend me any file/video to upload and generate a secure link.\n\nCommands:\n/stats - View analytics\n/switch - Switch Primary/Backup bot\n/broadcast - Message all users")

@app.on_message(filters.private & (filters.video | filters.document | filters.audio | filters.photo) & filters.user(OWNER_ID))
async def upload_file(client, message: Message):
    msg = await message.reply("⏳ **Uploading to encrypted storage...**")
    try:
        forwarded = await message.copy(CHANNEL_ID)
        
        file_code = generate_file_code()
        while files_col.find_one({"file_code": file_code}):
            file_code = generate_file_code()
            
        file_type = "video" if message.video else "document" if message.document else "photo" if message.photo else "audio"
        file_name = getattr(message, file_type).file_name if hasattr(getattr(message, file_type), 'file_name') else f"File_{file_code}"

        files_col.insert_one({
            "file_code": file_code,
            "message_id": forwarded.id,
            "file_type": file_type,
            "file_name": file_name,
            "upload_time": datetime.now(timezone.utc),
            "clicks": 0
        })

        active_bot = get_active_bot_username()
        share_link = f"https://t.me/{active_bot}?start={file_code}"
        
        await msg.edit_text(
            f"✅ **Upload Complete!**\n\n📁 **Name:** `{file_name}`\n🔑 **Code:** `{file_code}`\n\n🔗 **Link:**\n`{share_link}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Open Link", url=share_link)]])
        )
    except Exception as e:
        await msg.edit_text(f"❌ Upload Failed: {e}")

@app.on_message(filters.command("switch") & filters.user(OWNER_ID))
async def switch_bot(client, message: Message):
    stats = stats_col.find_one({"_id": "bot_stats"})
    current = stats.get("active_bot", "primary") if stats else "primary"
    new_mode = "backup" if current == "primary" else "primary"
    
    stats_col.update_one({"_id": "bot_stats"}, {"$set": {"active_bot": new_mode}}, upsert=True)
    await message.reply(f"🔄 **Bot Switched!**\n\nNow generating links for: **{new_mode.upper()}**")

@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def show_stats(client, message: Message):
    users = users_col.count_documents({})
    files = files_col.count_documents({})
    stats = stats_col.find_one({"_id": "bot_stats"})
    clicks = stats.get("total_clicks", 0) if stats else 0
    await message.reply(f"📊 **System Analytics**\n\n👥 Users: `{users}`\n📁 Files: `{files}`\n🖱️ Total Clicks: `{clicks}`")

@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast(client, message: Message):
    if not message.reply_to_message:
        return await message.reply("⚠️ Reply to a message with /broadcast")
        
    msg = await message.reply("📢 **Broadcasting...**")
    users = users_col.find({}, {"user_id": 1})
    
    success, failed, blocked = 0, 0, 0
    for user in users:
        try:
            await message.reply_to_message.copy(user["user_id"])
            success += 1
            await asyncio.sleep(0.05)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await message.reply_to_message.copy(user["user_id"])
            success += 1
        except (UserIsBlocked, InputUserDeactivated):
            blocked += 1
            users_col.delete_one({"user_id": user["user_id"]})
        except Exception:
            failed += 1
            
    await msg.edit_text(f"✅ **Broadcast Done!**\n\n✔️ Sent: {success}\n🚫 Blocked/Deleted: {blocked}\n❌ Failed: {failed}")

if __name__ == "__main__":
    print("🚀 Enhanced Admin Bot Started...")
    app.run()
