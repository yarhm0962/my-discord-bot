import os
import discord
from discord.ext import commands
import aiohttp
import re
import io
import pymongo
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

TOKEN = os.getenv("TOKEN")

MONGODB_URI = "mongodb+srv://xyrielzen16_db_user:saisai1324@panelbot.aubckg7.mongodb.net/?appName=PanelBot"

try:
    mongo_client = MongoClient(MONGODB_URI, server_api=ServerApi('1'))
    mongo_client.admin.command('ping')
    print("Connected to MongoDB successfully!")
except Exception as e:
    print(f"MongoDB Connection Error: {str(e)}")
    mongo_client = None

db = mongo_client.get_database("rblxlua_data") if mongo_client else None
settings_col = db["settings"] if db else None
logs_col = db["usage_logs"] if db else None

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

COMMANDS_LIST = """
`.l <link/loadstring>` - Detect protection → Deobfuscate → Send result as file
`.get <link/loadstring>` - Fetch raw full source code → Send as file
`.env <link/loadstring>` - Bypass anti-envlog → Run envlog scan → Send full report
`.cmds` - Show this command list
`.db status` - Check MongoDB connection status
`.db clear` - Clear stored data (admin only)
"""

async def fetch_content(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.1 Safari/537.36",
            "Referer": "https://roblox.com/"
        }
        async with session.get(url, headers=headers) as resp:
            return await resp.text()

def detect_and_deobf(code: str) -> str:
    result = []

    if "Lunr" in code or ("return(function" in code and "local L={" in code):
        result.append("[✓] Detected: Lunr Obfuscation")
        code = re.sub(r'-- This file was protected using Lunr.*?\n', '', code, flags=re.DOTALL)
        result.append("[+] Applied: Lunr unpack cleanup")

    if "Luraph" in code or ("bxor" in code and "string.gsub" in code):
        result.append("[✓] Detected: Luraph / Custom XOR")

    if "Prometheus" in code or "local _=getgenv" in code:
        result.append("[✓] Detected: Prometheus / Control Flow")

    if code.isascii() and len(code) % 4 == 0 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/" for c in code.rstrip("=")):
        result.append("[✓] Detected: Raw Base64")

    result.append("\n=== BEST EFFORT RESULT ===")
    result.append(code)
    return "\n".join(result)

async def envlog_scan(code: str) -> str:
    report = ["=== ENVIRONMENT LOGGER ANALYSIS ==="]
    bypassed = code

    checks = [
        ("_ENVLOG", "Anti-Envlog Variable check"),
        ("_GALACTIC", "Anti-logger marker"),
        ("debug.getupvalue", "Debug interception"),
        ("Kick.*tampered", "Kick on tamper/log"),
        ("loadstring.*~=", "Function hook detection"),
        ("while true do end", "Infinite loop freeze"),
        ("os.exit", "Force close script")
    ]

    found = []
    for pattern, desc in checks:
        if re.search(pattern, bypassed):
            found.append(f"[!] FOUND: {desc}")
            bypassed = re.sub(pattern, f"-- BYPASSED {pattern}", bypassed)

    if found:
        report.extend(found)
        report.append("\n[+] Applied: Anti-log marker bypass")
    else:
        report.append("[✓] No strong anti-envlog found")

    report.append("\n=== SCANNED SOURCE ===")
    report.append(bypassed)
    return "\n".join(report)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    if db:
        print(f"Database: {db.name} connected")

@bot.group(name="db", invoke_without_command=True)
async def db_group(ctx):
    await ctx.send("Use `.db status` or `.db clear`")

@db_group.command(name="status")
async def db_status(ctx):
    if mongo_client:
        await ctx.send("✅ MongoDB is connected and working properly")
    else:
        await ctx.send("❌ MongoDB connection failed")

@db_group.command(name="clear")
@commands.is_owner()
async def db_clear(ctx):
    if db:
        settings_col.delete_many({})
        logs_col.delete_many({})
        await ctx.send("✅ All database data cleared")
    else:
        await ctx.send("❌ Not connected to database")

@bot.command(name="cmds")
async def show_commands(ctx):
    emb = discord.Embed(title="RblXLua Tool Commands", color=0x2b2d31)
    emb.add_field(name="Commands", value=COMMANDS_LIST, inline=False)
    emb.set_footer(text="All results sent as files")
    await ctx.send(embed=emb)

@bot.command(name="l")
async def deobf_command(ctx, *, link: str):
    await ctx.send("Processing and detecting protection...")
    try:
        url_match = re.search(r'https?://[^\s"\'<>)]+', link)
        if not url_match:
            return await ctx.send("❌ No valid URL found")
        url = url_match.group(0)
        code = await fetch_content(url)
        result = detect_and_deobf(code)
        file = discord.File(io.StringIO(result), filename="deobfuscated_result.lua")
        await ctx.send(f"✅ Done: `{url}`", file=file)
        if logs_col:
            logs_col.insert_one({
                "user_id": ctx.author.id,
                "type": "deobfuscate",
                "url": url,
                "timestamp": discord.utils.utcnow()
            })
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:120]}")

@bot.command(name="get")
async def fetch_command(ctx, *, link: str):
    await ctx.send("Fetching raw source...")
    try:
        url_match = re.search(r'https?://[^\s"\'<>)]+', link)
        if not url_match:
            return await ctx.send("❌ No valid URL found")
        url = url_match.group(0)
        code = await fetch_content(url)
        file = discord.File(io.StringIO(code), filename="raw_fetched_source.lua")
        await ctx.send(f"✅ Done: `{url}`", file=file)
        if logs_col:
            logs_col.insert_one({
                "user_id": ctx.author.id,
                "type": "fetch",
                "url": url,
                "timestamp": discord.utils.utcnow()
            })
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:120]}")

@bot.command(name="env")
async def envlog_command(ctx, *, link: str):
    await ctx.send("Scanning anti-log measures...")
    try:
        url_match = re.search(r'https?://[^\s"\'<>)]+', link)
        if not url_match:
            return await ctx.send("❌ No valid URL found")
        url = url_match.group(0)
        code = await fetch_content(url)
        result = await envlog_scan(code)
        file = discord.File(io.StringIO(result), filename="envlog_analysis.lua")
        await ctx.send(f"✅ Done: `{url}`", file=file)
        if logs_col:
            logs_col.insert_one({
                "user_id": ctx.author.id,
                "type": "envscan",
                "url": url,
                "timestamp": discord.utils.utcnow()
            })
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:120]}")

bot.run(TOKEN)
