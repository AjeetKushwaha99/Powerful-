import os
import asyncio
import string
import random
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, BotCommand
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

CHANNEL_ID = -1003777551559
OWNER_ID = 6549083920

# MongoDB Connection
MONGO_URL = "mongodb+srv://Ajeet:XgGFRFWVT2NwWipw@cluster0.3lxz0p7.mongodb.net/?appName=Cluster0"

# RAILWAY DOMAIN URL
WEB_URL = os.environ.get("WEB_URL", "https://aapka-app.up.railway.app")

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
    print(f"🌐 Smart Redirector Server running on port {port}")

# ==========================================
# 🤖 ADMIN BOT COMMANDS & HANDLERS
# ==========================================
app = Client("admin_bot", api_id=API_ID, api_hash=API_HASH, bot_token=ADMIN_BOT_TOKEN)

def generate_file_code(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# --- START COMMAND (WITH BUTTON) ---
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    if message.from_user.id != OWNER_ID: 
        return await message.reply("❌ **Access Denied!** You are not the owner.")
    
    # Check current active bot
    stats = stats_col.find_one({"_id": "bot_stats"})
    active_mode = stats.get("active_bot", "primary") if stats else "primary"
    
    # Create Switch Button
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔄 Switch Bot (Current: {active_mode.upper()})", callback_data="switch_bot_btn")]
    ])
    
    await message.reply(
        "🤖 **Premium Admin Panel (Ban-Proof)**\n\n"
        "Send me any file/video to upload. I will generate a Smart Web Link.\n\n"
        "Commands:\n"
        "/stats - Analytics\n"
        "/broadcast - Message Users",
        reply_markup=btn
    )

# --- SWITCH BUTTON CLICK HANDLER ---
@app.on_callback_query(filters.regex("^switch_bot_btn$"))
async def switch_btn_click(client, query):
    if query.from_user.id != OWNER_ID: return
    
    stats = stats_col.find_one({"_id": "bot_stats"})
    current = stats.get("active_bot", "primary") if stats else "primary"
    new_mode = "backup" if current == "primary" else "primary"
    
    # Update DB
    stats_col.update_one({"_id": "bot_stats"}, {"$set": {"active_bot": new_mode}}, upsert=True)
    
    # Update Button Text
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔄 Switch Bot (Current: {new_mode.upper()})", callback_data="switch_bot_btn")]
    ])
    
    await query.message.edit_text(query.message.text, reply_markup=btn)
    await query.answer(f"✅ Bot Switched to {new_mode.upper()}", show_alert=True)

# --- FILE UPLOAD ---
@app.on_message(filters.private & (filters.video | filters.document | filters.audio | filters.photo) & filters.user(OWNER_ID))
async def upload_file(client, message: Message):
    msg = await message.reply("⏳ **Uploading and generating Smart Link...**")
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

        smart_link = f"{WEB_URL}/{file_code}"
        
        await msg.edit_text(
            f"✅ **Upload Complete!**\n\n📁 **Name:** `{file_name}`\n\n🔗 **Smart Link (Share this):**\n`{smart_link}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Open Link", url=smart_link)]])
        )
    except Exception as e:
        await msg.edit_text(f"❌ Upload Failed: {e}")

# --- OLD SWITCH COMMAND (Also kept just in case) ---
@app.on_message(filters.command("switch") & filters.user(OWNER_ID))
async def switch_bot_cmd(client, message: Message):
    stats = stats_col.find_one({"_id": "bot_stats"})
    current = stats.get("active_bot", "primary") if stats else "primary"
    new_mode = "backup" if current == "primary" else "primary"
    stats_col.update_one({"_id": "bot_stats"}, {"$set": {"active_bot": new_mode}}, upsert=True)
    await message.reply(f"🔄 **Bot Switched!**\n\nSmart links will now automatically redirect users to: **{new_mode.upper()}**")

# --- STATS COMMAND ---
@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def show_stats(client, message: Message):
    users = users_col.count_documents({})
    files = files_col.count_documents({})
    stats = stats_col.find_one({"_id": "bot_stats"})
    clicks = stats.get("total_clicks", 0) if stats else 0
    await message.reply(f"📊 **System Analytics**\n\n👥 Users: `{users}`\n📁 Files: `{files}`\n🖱️ Total Clicks: `{clicks}`")

# --- BROADCAST COMMAND ---
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

# ==========================================
# 🚀 APP LAUNCHER
# ==========================================
async def main():
    print("🚀 Starting Smart Redirector and Admin Bot...")
    
    # Setup Telegram Commands Menu Automatically
    await app.start()
    try:
        await app.set_bot_commands([
            BotCommand("start", "Start Admin Panel"),
            BotCommand("stats", "View Bot Analytics"),
            BotCommand("switch", "Switch Primary/Backup"),
            BotCommand("broadcast", "Send message to all users")
        ])
        print("✅ Telegram Commands Menu Updated!")
    except Exception as e:
        print(f"⚠️ Could not set commands: {e}")

    await start_web_server()
    import pyrogram
    await pyrogram.idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
