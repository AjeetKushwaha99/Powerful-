import os
import asyncio
import string
import random
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, BotCommand, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated
from pymongo import MongoClient
from aiohttp import web  

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
API_ID = 37067823
API_HASH = "ed9e62ed4538d2d2b835fb54529c358f"
ADMIN_BOT_TOKEN = "8596951434:AAF98nta7kfLKqeR9ImT5pUCTZoZ1rLFOwI"

USER_BOT_PRIMARY_USERNAME = "Filling4You_bot"
USER_BOT_BACKUP_USERNAME = "FiLing4YoU_bot"

# 🔥 DUAL CHANNEL
CHANNEL_PRIMARY = -1003777551559
CHANNEL_BACKUP = -1003867841066

# 🔥 DUAL OWNER
OWNER_IDS = [6549083920, 6353210726]

# MongoDB
MONGO_URL = "mongodb+srv://Ajeet:XgGFRFWVT2NwWipw@cluster0.3lxz0p7.mongodb.net/?appName=Cluster0"

# RAILWAY DOMAIN
WEB_URL = os.environ.get("WEB_URL", "https://aapka-app.up.railway.app")

# ==========================================
# 🗄️ DATABASE
# ==========================================
mongo_client = MongoClient(MONGO_URL, maxPoolSize=50, serverSelectionTimeoutMS=5000)
db = mongo_client["FileSharingPro"]

users_col = db["users"]
files_col = db["files"]
stats_col = db["stats"]

if stats_col.find_one({"_id": "bot_stats"}) is None:
    stats_col.insert_one({
        "_id": "bot_stats",
        "total_clicks": 0,
        "active_bot": "primary",
        "active_channel": "primary"
    })

# ==========================================
# 🔧 HELPERS
# ==========================================
def is_owner(user_id):
    return user_id in OWNER_IDS

def get_active_channel():
    stats = stats_col.find_one({"_id": "bot_stats"})
    if stats and stats.get("active_channel") == "backup":
        return CHANNEL_BACKUP
    return CHANNEL_PRIMARY

def get_active_channel_name():
    stats = stats_col.find_one({"_id": "bot_stats"})
    return stats.get("active_channel", "primary") if stats else "primary"

def get_active_bot_name():
    stats = stats_col.find_one({"_id": "bot_stats"})
    return stats.get("active_bot", "primary") if stats else "primary"

def generate_file_code(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# ==========================================
# 🌐 SMART WEB REDIRECTOR
# ==========================================
async def redirect_to_bot(request):
    file_code = request.match_info.get('file_code')
    if not file_code:
        return web.Response(text="❌ Invalid Link!", status=400)

    stats = stats_col.find_one({"_id": "bot_stats"})
    active_mode = stats.get("active_bot", "primary") if stats else "primary"
    active_username = USER_BOT_PRIMARY_USERNAME if active_mode == "primary" else USER_BOT_BACKUP_USERNAME

    tg_url = f"https://t.me/{active_username}?start={file_code}"
    raise web.HTTPFound(tg_url)

async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get('/{file_code}', redirect_to_bot)
    runner = web.AppRunner(app_web)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 Smart Redirector running on port {port}")

# ==========================================
# 🤖 ADMIN BOT
# ==========================================
app = Client("admin_bot", api_id=API_ID, api_hash=API_HASH, bot_token=ADMIN_BOT_TOKEN)

# --- START ---
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    if not is_owner(message.from_user.id): 
        return await message.reply("❌ **Access Denied!**")
    
    active_bot = get_active_bot_name()
    active_channel = get_active_channel_name()
    
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🤖 Bot: {active_bot.upper()}", callback_data="switch_bot_btn"),
         InlineKeyboardButton(f"📡 Ch: {active_channel.upper()}", callback_data="switch_channel_btn")],
        [InlineKeyboardButton("📊 Live Stats", callback_data="live_stats")]
    ])
    
    await message.reply(
        f"🤖 **Premium Admin Panel**\n\n"
        f"👤 **Your ID:** `{message.from_user.id}`\n"
        f"👥 **Owners:** `{OWNER_IDS}`\n\n"
        f"🤖 **Active Bot:** {active_bot.upper()}\n"
        f"📡 **Active Channel:** {active_channel.upper()}\n"
        f"🌐 **Domain:** `{WEB_URL}`\n\n"
        f"Send any file/video to upload.\n\n"
        f"/stats - Analytics\n"
        f"/broadcast - Message Users\n"
        f"/switch - Switch Bot\n"
        f"/switchchannel - Switch Channel",
        reply_markup=btn
    )

# --- SWITCH BOT ---
@app.on_callback_query(filters.regex("^switch_bot_btn$"))
async def switch_bot_btn(client, query: CallbackQuery):
    if not is_owner(query.from_user.id): return
    current = get_active_bot_name()
    new_mode = "backup" if current == "primary" else "primary"
    stats_col.update_one({"_id": "bot_stats"}, {"$set": {"active_bot": new_mode}}, upsert=True)
    active_channel = get_active_channel_name()
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🤖 Bot: {new_mode.upper()}", callback_data="switch_bot_btn"),
         InlineKeyboardButton(f"📡 Ch: {active_channel.upper()}", callback_data="switch_channel_btn")],
        [InlineKeyboardButton("📊 Live Stats", callback_data="live_stats")]
    ])
    await query.message.edit_reply_markup(reply_markup=btn)
    await query.answer(f"✅ Bot → {new_mode.upper()}", show_alert=True)

# --- SWITCH CHANNEL ---
@app.on_callback_query(filters.regex("^switch_channel_btn$"))
async def switch_channel_btn(client, query: CallbackQuery):
    if not is_owner(query.from_user.id): return
    current = get_active_channel_name()
    new_ch = "backup" if current == "primary" else "primary"
    stats_col.update_one({"_id": "bot_stats"}, {"$set": {"active_channel": new_ch}}, upsert=True)
    active_bot = get_active_bot_name()
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🤖 Bot: {active_bot.upper()}", callback_data="switch_bot_btn"),
         InlineKeyboardButton(f"📡 Ch: {new_ch.upper()}", callback_data="switch_channel_btn")],
        [InlineKeyboardButton("📊 Live Stats", callback_data="live_stats")]
    ])
    await query.message.edit_reply_markup(reply_markup=btn)
    await query.answer(f"✅ Channel → {new_ch.upper()}", show_alert=True)

# --- LIVE STATS ---
@app.on_callback_query(filters.regex("^live_stats$"))
async def live_stats_btn(client, query: CallbackQuery):
    if not is_owner(query.from_user.id): return
    users = users_col.count_documents({})
    files = files_col.count_documents({})
    stats = stats_col.find_one({"_id": "bot_stats"})
    clicks = stats.get("total_clicks", 0) if stats else 0
    await query.answer(f"👥 Users: {users}\n📁 Files: {files}\n🖱️ Clicks: {clicks}", show_alert=True)

# --- FILE UPLOAD (DUAL CHANNEL) ---
@app.on_message(filters.private & (filters.video | filters.document | filters.audio | filters.photo))
async def upload_file(client, message: Message):
    if not is_owner(message.from_user.id):
        return await message.reply("❌ **Access Denied!**")
    
    msg = await message.reply("⏳ **Uploading to BOTH channels...**")
    try:
        forwarded_primary = None
        forwarded_backup = None
        
        try:
            forwarded_primary = await message.copy(CHANNEL_PRIMARY)
        except Exception as e:
            print(f"Primary upload failed: {e}")
        
        try:
            forwarded_backup = await message.copy(CHANNEL_BACKUP)
        except Exception as e:
            print(f"Backup upload failed: {e}")
        
        if not forwarded_primary and not forwarded_backup:
            return await msg.edit_text("❌ Upload Failed! Make bot admin in both channels.")
        
        file_code = generate_file_code()
        while files_col.find_one({"file_code": file_code}):
            file_code = generate_file_code()
            
        file_type = "video" if message.video else "document" if message.document else "photo" if message.photo else "audio"
        file_name = getattr(message, file_type).file_name if hasattr(getattr(message, file_type), 'file_name') else f"File_{file_code}"

        file_doc = {
            "file_code": file_code,
            "file_type": file_type,
            "file_name": file_name,
            "upload_time": datetime.now(timezone.utc),
            "clicks": 0,
            "uploaded_by": message.from_user.id
        }
        
        if forwarded_primary:
            file_doc["message_id_primary"] = forwarded_primary.id
            file_doc["message_id"] = forwarded_primary.id
            file_doc["channel_id"] = CHANNEL_PRIMARY
        
        if forwarded_backup:
            file_doc["message_id_backup"] = forwarded_backup.id
            if not forwarded_primary:
                file_doc["message_id"] = forwarded_backup.id
                file_doc["channel_id"] = CHANNEL_BACKUP
        
        files_col.insert_one(file_doc)

        smart_link = f"{WEB_URL}/{file_code}"
        
        status = ""
        if forwarded_primary and forwarded_backup:
            status = "✅ Primary + ✅ Backup"
        elif forwarded_primary:
            status = "✅ Primary Only"
        else:
            status = "✅ Backup Only"
        
        await msg.edit_text(
            f"✅ **Upload Complete!**\n\n"
            f"📁 **Name:** `{file_name}`\n"
            f"📡 **Stored:** {status}\n"
            f"👤 **By:** `{message.from_user.id}`\n\n"
            f"🔗 **Smart Link:**\n`{smart_link}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Open Link", url=smart_link)]])
        )
    except Exception as e:
        await msg.edit_text(f"❌ Upload Failed: {e}")

# --- TEXT COMMANDS ---
@app.on_message(filters.command("switch") & filters.private)
async def switch_cmd(client, message: Message):
    if not is_owner(message.from_user.id): return
    current = get_active_bot_name()
    new_mode = "backup" if current == "primary" else "primary"
    stats_col.update_one({"_id": "bot_stats"}, {"$set": {"active_bot": new_mode}}, upsert=True)
    await message.reply(f"🔄 Bot → **{new_mode.upper()}**")

@app.on_message(filters.command("switchchannel") & filters.private)
async def switch_ch_cmd(client, message: Message):
    if not is_owner(message.from_user.id): return
    current = get_active_channel_name()
    new_ch = "backup" if current == "primary" else "primary"
    stats_col.update_one({"_id": "bot_stats"}, {"$set": {"active_channel": new_ch}}, upsert=True)
    await message.reply(f"📡 Channel → **{new_ch.upper()}**")

@app.on_message(filters.command("stats") & filters.private)
async def show_stats(client, message: Message):
    if not is_owner(message.from_user.id): return
    users = users_col.count_documents({})
    files = files_col.count_documents({})
    stats = stats_col.find_one({"_id": "bot_stats"})
    clicks = stats.get("total_clicks", 0) if stats else 0
    await message.reply(
        f"📊 **Analytics**\n\n"
        f"👥 Users: `{users}`\n"
        f"📁 Files: `{files}`\n"
        f"🖱️ Clicks: `{clicks}`\n\n"
        f"🤖 Bot: **{get_active_bot_name().upper()}**\n"
        f"📡 Channel: **{get_active_channel_name().upper()}**"
    )

@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast(client, message: Message):
    if not is_owner(message.from_user.id): return
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
    await msg.edit_text(f"✅ **Done!** ✔️{success} 🚫{blocked} ❌{failed}")

# ==========================================
# 🚀 LAUNCHER
# ==========================================
async def main():
    print("🚀 Starting Dual-Owner Admin Bot...")
    await app.start()
    try:
        await app.set_bot_commands([
            BotCommand("start", "Start Admin Panel"),
            BotCommand("stats", "View Analytics"),
            BotCommand("switch", "Switch Bot"),
            BotCommand("switchchannel", "Switch Channel"),
            BotCommand("broadcast", "Broadcast Message")
        ])
        print("✅ Commands Menu Set!")
    except Exception as e:
        print(f"⚠️ Commands error: {e}")

    await start_web_server()
    print(f"✅ Owners: {OWNER_IDS}")
    print(f"✅ Primary Channel: {CHANNEL_PRIMARY}")
    print(f"✅ Backup Channel: {CHANNEL_BACKUP}")
    print(f"✅ Domain: {WEB_URL}")
    
    import pyrogram
    await pyrogram.idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
