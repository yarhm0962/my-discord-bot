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
MONGODB_URI = os.getenv("MONGODB_URI")

mongo_client = None
db = None
settings_col = None
logs_col = None

try:
    mongo_client = MongoClient(MONGODB_URI, server_api=ServerApi('1'))
    mongo_client.admin.command('ping')
    db = mongo_client["rblxlua_data"]
    settings_col = db["settings"]
    logs_col = db["usage_logs"]
    print("✅ MongoDB Connected Successfully")
except Exception as e:
    print(f"❌ MongoDB Error: {str(e)}")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

COMMANDS_LIST = """
`.l <link/loadstring>` - Detect protection → Deobfuscate → Send file
`.get <link/loadstring>` - Fetch raw full source → Send file
`.env <link/loadstring>` - Scan anti-log & bypass → Send report
`.cmds` - Show this command list
`.db status` - Check database connection
`.db clear` - Clear all stored data (owner only)
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
    if "Luraph" in code or ("bxor" in code and "string.gsub" in code):
        result.append("[✓] Detected: Luraph / Custom XOR")
    if "Prometheus" in code or "local _=getgenv" in code:
        result.append("[✓] Detected: Prometheus / Control Flow")
    if code.isascii() and len(code) % 4 == 0 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/" for c in code.rstrip("=")):
        result.append("[✓] Detected: Raw Base64")
    result.append("\n=== RESULT ===")
    result.append(code)
    return "\n".join(result)

async def envlog_scan(code: str) -> str:
    report = ["=== ENVIRONMENT LOGGER SCAN ==="]
    bypassed = code
    checks = [
        ("_ENVLOG", "Anti-Envlog Variable"),
        ("_GALACTIC", "Anti-logger Marker"),
        ("debug.getupvalue", "Debug Interception"),
        ("Kick.*tampered", "Kick On Tamper"),
        ("loadstring.*~=", "Hook Detection"),
        ("while true do end", "Infinite Loop Freeze"),
        ("os.exit", "Force Close Script")
    ]
    found = []
    for pattern, desc in checks:
        if re.search(pattern, bypassed):
            found.append(f"[!] FOUND: {desc}")
            bypassed = re.sub(pattern, f"-- BYPASSED {pattern}", bypassed)
    if found:
        report.extend(found)
        report.append("\n[+] All markers commented out")
    else:
        report.append("[✓] No strong anti-log found")
    report.append("\n=== SCANNED CODE ===")
    report.append(bypassed)
    return "\n".join(report)

@bot.event
async def on_ready():
    print(f"✅ Logged in as: {bot.user}")
    if db is not None:
        print(f"✅ Database Ready: {db.name}")

@bot.group(name="db", invoke_without_command=True)
async def db_group(ctx):
    await ctx.send("Use `.db status` or `.db clear`")

@db_group.command(name="status")
async def db_status(ctx):
    if mongo_client is not None and db is not None:
        await ctx.send("✅ MongoDB is connected and working")
    else:
        await ctx.send("❌ Not connected to database")

@db_group.command(name="clear")
@commands.is_owner()
async def db_clear(ctx):
    if settings_col is not None and logs_col is not None:
        settings_col.delete_many({})
        logs_col.delete_many({})
        await ctx.send("✅ All database data cleared")
    else:
        await ctx.send("❌ Database not available")

@bot.command(name="cmds")
async def show_commands(ctx):
    emb = discord.Embed(title="RblXLua Tool Commands", color=0x2b2d31)
    emb.add_field(name="Available Commands", value=COMMANDS_LIST, inline=False)
    emb.set_footer(text="All results sent as downloadable files")
    await ctx.send(embed=emb)

@bot.command(name="l")
async def deobf_command(ctx, *, link: str):
    await ctx.send("Processing obfuscation detection...")
    try:
        url_match = re.search(r'https?://[^\s"\'<>)]+', link)
        if not url_match:
            return await ctx.send("❌ No valid URL found")
        url = url_match.group(0)
        code = await fetch_content(url)
        result = detect_and_deobf(code)
        file = discord.File(io.StringIO(result), filename="deobfuscated_result.lua")
        await ctx.send(f"✅ Finished: `{url}`", file=file)
        if logs_col is not None:
            logs_col.insert_one({
                "user_id": ctx.author.id,
                "action": "deobfuscate",
                "url": url,
                "time": discord.utils.utcnow()
            })
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:120]}")

@bot.command(name="get")
async def fetch_command(ctx, *, link: str):
    await ctx.send("Fetching full source code...")
    try:
        url_match = re.search(r'https?://[^\s"\'<>)]+', link)
        if not url_match:
            return await ctx.send("❌ No valid URL found")
        url = url_match.group(0)
        code = await fetch_content(url)
        file = discord.File(io.StringIO(code), filename="raw_fetched_source.lua")
        await ctx.send(f"✅ Finished: `{url}`", file=file)
        if logs_col is not None:
            logs_col.insert_one({
                "user_id": ctx.author.id,
                "action": "fetch",
                "url": url,
                "time": discord.utils.utcnow()
            })
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:120]}")

@bot.command(name="env")
async def envlog_command(ctx, *, link: str):
    await ctx.send("Scanning anti-environment logger...")
    try:
        url_match = re.search(r'https?://[^\s"\'<>)]+', link)
        if not url_match:
            return await ctx.send("❌ No valid URL found")
        url = url_match.group(0)
        code = await fetch_content(url)
        result = await envlog_scan(code)
        file = discord.File(io.StringIO(result), filename="envlog_analysis.lua")
        await ctx.send(f"✅ Finished: `{url}`", file=file)
        if logs_col is not None:
            logs_col.insert_one({
                "user_id": ctx.author.id,
                "action": "envscan",
                "url": url,
                "time": discord.utils.utcnow()
            })
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:120]}")

bot.run(TOKEN)
