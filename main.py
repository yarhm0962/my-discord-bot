from flask import Flask
from threading import Thread
import os
import re
import base64
import aiohttp
import discord
from discord import app_commands, File
from discord.ext import commands

app = Flask('')
@app.route('/')
def home(): return "Bot is running"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)
tree = bot.tree

def extract_url(text):
    patterns = [
        r'game:HttpGet\s*\(\s*["\']([^"\']+)["\']',
        r'http\.get\s*\(\s*["\']([^"\']+)["\']',
        r'loadstring\s*\(\s*game:HttpGet\s*\(\s*["\']([^"\']+)["\']',
        r'loadstring\s*\(\s*http\.get\s*\(\s*["\']([^"\']+)["\']',
        r'["\'](https?://[^"\']+)["\']'
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            url = m.group(1)
            if "api.pastes.io" in url:
                return None
            return url
    return text.strip() if text.strip().startswith(('http://', 'https://')) and "api.pastes.io" not in text else None

def try_decode(code):
    if not code: return "Error: Empty code"
    original = code
    code = code.strip()
    b64_patterns = [
        r'loadstring\s*\(\s*base64\.decode\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']',
        r'base64\.decode\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']',
        r'["\']([A-Za-z0-9+/=]{20,})["\']'
    ]
    for pat in b64_patterns:
        m = re.search(pat, code)
        if m:
            try:
                decoded = base64.b64decode(m.group(1)).decode('utf-8', errors='ignore')
                if decoded and len(decoded) > 10:
                    code = decoded
            except: pass
    m = re.match(r'^loadstring\s*\(\s*(.+)\s*\)\s*\([^)]*\)?\s*$', code.strip(), re.DOTALL)
    if m:
        inner = m.group(1).strip()
        if not inner.startswith('game:HttpGet'):
            code = inner
    return code if code else original

async def deobfuscate_from_url(url):
    try:
        if "api.pastes.io" in url:
            return None, "Error: api.pastes.io does NOT exist! Use real links like rentry.co or paste.gg"
        if "rentry.co" in url and "/raw/" not in url:
            url = url.replace("rentry.co/", "rentry.co/raw/")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(url, timeout=30, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None, f"HTTP Error: Status {resp.status}"
                code = await resp.text()
                if not code or len(code) < 5:
                    return None, "Error: Empty response from URL"
                deobf = try_decode(code)
                return deobf, None
    except Exception as e:
        return None, f"Fetch Error: {str(e)[:80]}"

@bot.command(name='d')
async def deobf_prefix(ctx, *, link: str):
    if ctx.author.bot: return
    status_msg = await ctx.send("Processing...")
    url = extract_url(link)
    if not url:
        if "api.pastes.io" in link:
            return await status_msg.edit(content="Error: api.pastes.io DOES NOT EXIST! Use real working links like https://rentry.co/raw/XXX or https://paste.gg/raw/XXX")
        return await status_msg.edit(content="Error: Could not find a valid URL or loadstring")
    deobf_code, error = await deobfuscate_from_url(url)
    if error:
        return await status_msg.edit(content=f"Error: {error}")
    filename = f"deobfuscated_{ctx.message.id}.lua"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(deobf_code)
    await status_msg.edit(content="Success: Loadstring deobfuscated successfully")
    await ctx.send(file=File(filename))
    os.remove(filename)

@tree.command(name="deobf-file", description="Upload a .lua file to deobfuscate")
@app_commands.describe(file="Upload your obfuscated .lua file")
async def deobf_slash(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith('.lua'):
        return await interaction.response.send_message("Error: Please upload a .lua file", ephemeral=True)
    await interaction.response.defer()
    try:
        content = (await file.read()).decode('utf-8', errors='ignore')
    except Exception as e:
        return await interaction.followup.send(f"Error: Could not read file - {str(e)}", ephemeral=True)
    deobf_code = try_decode(content)
    filename = f"deobfuscated_{interaction.id}.lua"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(deobf_code)
    await interaction.followup.send(content="Success: File deobfuscated successfully", file=File(filename))
    os.remove(filename)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try: await tree.sync()
    except Exception as e: print(f"Sync Error: {e}")

keep_alive()
TOKEN = os.getenv('TOKEN')
bot.run(TOKEN)
