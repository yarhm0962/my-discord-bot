from flask import Flask
from threading import Thread
import os
import re
import base64
import aiohttp
import asyncio
import discord
from datetime import timedelta
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

TICKET_SETTINGS = {}
USER_TICKETS = {}
WARNINGS = {}
TIMEOUT_DURATION = 300

def parse_time(time_str):
    if not time_str: return None
    match = re.match(r'(\d+)([mhd])', time_str.lower().strip())
    if not match: return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == 'm': return amount * 60
    elif unit == 'h': return amount * 3600
    elif unit == 'd': return amount * 86400
    return None

def get_color(color_str):
    color = color_str.lower().strip()
    color_map = {
        "red": discord.Colour.red(),"green": discord.Colour.green(),"blue": discord.Colour.blue(),
        "gold": discord.Colour.gold(),"yellow": discord.Colour.yellow(),"orange": discord.Colour.orange(),
        "purple": discord.Colour.purple(),"pink": discord.Colour.magenta(),"cyan": discord.Colour.teal(),
        "black": discord.Colour.from_rgb(0,0,0),"white": discord.Colour.from_rgb(255,255,255),
        "grey": discord.Colour.light_grey()
    }
    embed_color = color_map.get(color, discord.Colour.green())
    if color.startswith("#"):
        try: embed_color = discord.Colour(int(color.lstrip("#"), 16))
        except: embed_color = discord.Colour.green()
    return embed_color

def extract_url(text):
    patterns = [
        r'game:HttpGet\s*\(\s*["\']([^"\']+)["\']',r'http\.get\s*\(\s*["\']([^"\']+)["\']',
        r'loadstring\s*\(\s*game:HttpGet\s*\(\s*["\']([^"\']+)["\']',
        r'loadstring\s*\(\s*http\.get\s*\(\s*["\']([^"\']+)["\']',r'["\'](https?://[^"\']+)["\']'
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            url = m.group(1)
            if "api.pastes.io" in url: return None
            return url
    return text.strip() if text.strip().startswith(('http://','https://')) and "api.pastes.io" not in text else None

def smart_decode(code):
    if not code or len(code) < 5: return code or ""
    original = code
    code = code.strip()
    m = re.match(r'^(loadstring\s*\(\s*)?(.+?)(\)\s*\([^)]*\)?\s*)?$', code, re.DOTALL)
    if m:
        inner = m.group(2).strip()
        if not inner.startswith('game:HttpGet') and len(inner) > 20: code = inner
    patterns = [r'base64\.decode\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']',
                r'["\']([A-Za-z0-9+/=]{30,})["\']',r'loadstring\s*\(\s*["\']([A-Za-z0-9+/=]{30,})["\']']
    for pat in patterns:
        for match in re.finditer(pat, code):
            b64_text = match.group(1)
            try:
                if len(b64_text) % 4 != 0: b64_text += '=' * (4 - len(b64_text) % 4)
                decoded = base64.b64decode(b64_text).decode('utf-8', errors='ignore')
                if decoded and len(decoded) > 10 and not decoded.startswith('--'):
                    code = decoded
                    return smart_decode(code)
            except: continue
    rev_pattern = r'string\.reverse\s*\(\s*["\']([^"\']+)["\']'
    m = re.search(rev_pattern, code)
    if m:
        try:
            reversed_str = m.group(1)[::-1]
            if len(reversed_str) > 20:
                try:
                    if len(reversed_str) % 4 != 0: reversed_str += '=' * (4 - len(reversed_str) % 4)
                    decoded = base64.b64decode(reversed_str).decode('utf-8', errors='ignore')
                    if decoded and len(decoded) > 10:
                        code = decoded
                        return smart_decode(code)
                except:
                    if len(reversed_str) > 10:
                        code = reversed_str
                        return smart_decode(code)
        except: pass
    lines = code.split('\n')
    clean_lines = []
    for line in lines:
        ls = line.strip()
        if ls.startswith('--') and len(ls) < 50: continue
        if 'obfuscated' in ls.lower() or 'generated' in ls.lower(): continue
        if len(ls) > 10 or ls: clean_lines.append(line)
    return '\n'.join(clean_lines) if len(clean_lines) > 5 else original

async def deobfuscate_from_url(url):
    try:
        if "api.pastes.io" in url: return None, "Error: api.pastes.io does not exist! Use links like rentry.co/raw/XXX"
        if "rentry.co" in url and "/raw/" not in url: url = url.replace("rentry.co/","rentry.co/raw/")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(url, timeout=30, allow_redirects=True) as resp:
                if resp.status != 200: return None, f"HTTP Error: Status {resp.status}"
                code = await resp.text()
                if not code or len(code) < 5: return None, "Error: Empty response from URL"
                return smart_decode(code), None
    except Exception as e: return None, f"Fetch Error: {str(e)[:80]}"

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return await bot.process_commands(message)
    highest_role = max(message.guild.roles, key=lambda r: r.position)
    mentioned_highest = highest_role in message.role_mentions or any(highest_role in u.roles for u in message.mentions)
    if mentioned_highest:
        gid, uid = message.guild.id, message.author.id
        WARNINGS.setdefault(gid, {}).setdefault(uid, 0)
        WARNINGS[gid][uid] += 1
        count = WARNINGS[gid][uid]
        if count == 1:
            e = discord.Embed(title="⚠️ Warning 1/3", color=discord.Colour.yellow())
            e.description = f"{message.author.mention}, **Warning 1/3** — do not mention the highest role."
            await message.channel.send(embed=e)
        elif count == 2:
            e = discord.Embed(title="⚠️ Warning 2/3", color=discord.Colour.orange())
            e.description = f"{message.author.mention}, **Warning 2/3** — next violation = timeout!"
            await message.channel.send(embed=e)
        elif count >= 3:
            try:
                await message.author.timeout(discord.utils.utcnow() + timedelta(seconds=TIMEOUT_DURATION), reason="Mentioned highest role 3x")
                e = discord.Embed(title="⚠️ Warning 3/3 — TIMEOUT", color=discord.Colour.red())
                e.description = f"{message.author.mention} timed out **5 min**. Warnings reset."
                await message.channel.send(embed=e)
            except:
                e = discord.Embed(title="⚠️ Warning 3/3", color=discord.Colour.red())
                e.description = f"{message.author.mention} stop! Warnings reset."
                await message.channel.send(embed=e)
            WARNINGS[gid][uid] = 0
    await bot.process_commands(message)

@bot.command(name='cmds')
async def show_commands(ctx):
    if ctx.author.bot: return
    e = discord.Embed(title="📋 Bot Commands", color=discord.Colour.blue())
    e.add_field(name="Prefix", value="`.d <link>` — Deobfuscate\n`.cmds` — This list", inline=False)
    e.add_field(name="Slash Commands", value="`/deobf-file` `.lua` deobfuscate\n`/create-ticket` Ticket system\n`/create-embed` Custom embed\n`/ban`/`/unban`/`/kick` Moderation\n`/mute`/`/unmute` Timeout/Mute", inline=False)
    e.add_field(name="Auto", value="Highest role mention protection", inline=False)
    e.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.send(embed=e)
    try: await ctx.message.delete()
    except: pass

@bot.command(name='d')
async def deobf_prefix(ctx, *, link: str):
    if ctx.author.bot: return
    msg = await ctx.send("Processing...")
    url = extract_url(link)
    if not url:
        return await msg.edit(content="Error: Invalid URL. Use rentry.co/raw/XXX or direct link.")
    code, err = await deobfuscate_from_url(url)
    if err: return await msg.edit(content=err)
    fn = f"deobf_{ctx.message.id}.lua"
    with open(fn,'w',encoding='utf-8') as f: f.write(code)
    await msg.edit(content="✅ Success — deobfuscated:")
    await ctx.send(file=File(fn))
    os.remove(fn)

@tree.command(name="deobf-file")
@app_commands.describe(file=".lua or .txt file")
async def deobf_file(inter: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith(('.lua','.txt')):
        return await inter.response.send_message("Error: .lua or .txt only", ephemeral=True)
    await inter.response.defer()
    try: txt = (await file.read()).decode('utf-8','ignore')
    except: return await inter.followup.send("Error: Cannot read file", ephemeral=True)
    fn = f"deobf_{inter.id}.lua"
    with open(fn,'w',encoding='utf-8') as f: f.write(smart_decode(txt))
    await inter.followup.send("✅ Success:", file=File(fn))
    os.remove(fn)

class CloseTicket(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_tkt")
    async def close_btn(self, inter: discord.Interaction, btn: discord.ui.Button):
        s = TICKET_SETTINGS.get(inter.channel.id)
        if not s:
            return await inter.response.send_message("Error: Config missing", ephemeral=True)
        sr = inter.guild.get_role(s['admin_role_id'])
        creator_id = s.get('creator_id')
        if not (sr and sr in inter.user.roles) and not inter.user.guild_permissions.manage_channels:
            return await inter.response.send_message("No permission", ephemeral=True)
        await inter.response.send_message("Closing in 3 seconds...")
        await asyncio.sleep(3)
        if creator_id:
            gid = inter.guild.id
            USER_TICKETS.setdefault(gid, {})
            if creator_id in USER_TICKETS[gid]:
                del USER_TICKETS[gid][creator_id]
        await inter.channel.delete()

@tree.command(name="create-ticket")
@app_commands.describe(admin_role="Staff role", category="Ticket category", description="Panel text", color="Embed color")
async def tkt_panel(inter: discord.Interaction, admin_role: discord.Role, category: discord.CategoryChannel, description: str="", color: str="green"):
    if not inter.user.guild_permissions.administrator:
        return await inter.response.send_message("Need Administrator", ephemeral=True)
    TICKET_SETTINGS[inter.channel.id] = {'admin_role_id':admin_role.id,'category_id':category.id}

    class Panel(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
        @discord.ui.button(label="🎟️ Create Ticket", style=discord.ButtonStyle.success, custom_id="make_tkt")
        async def mk(self, b_int: discord.Interaction, btn: discord.ui.Button):
            gid = b_int.guild.id
            uid = b_int.user.id
            USER_TICKETS.setdefault(gid, {})
            if uid in USER_TICKETS[gid]:
                ch = b_int.guild.get_channel(USER_TICKETS[gid][uid])
                if ch:
                    return await b_int.response.send_message(f"⚠️ You already have an open ticket! Close it first: {ch.mention}", ephemeral=True)
                del USER_TICKETS[gid][uid]
            s = TICKET_SETTINGS.get(b_int.channel_id)
            cat = b_int.guild.get_channel(s['category_id'])
            sr = b_int.guild.get_role(s['admin_role_id'])
            if not cat or not sr:
                return await b_int.response.send_message("Setup error", ephemeral=True)
            ow = {
                b_int.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                b_int.user: discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True),
                sr: discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True),
                b_int.guild.me: discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True)
            }
            ch = await cat.create_text_channel(name=f"{b_int.user.name}-ticket", overwrites=ow)
            USER_TICKETS[gid][uid] = ch.id
            TICKET_SETTINGS[ch.id] = {'admin_role_id':sr.id,'creator_id':uid}
            e = discord.Embed(title="🎟️ Ticket Created", color=discord.Colour.green())
            e.add_field(name="Created By", value=b_int.user.mention, inline=False)
            e.add_field(name="Staff Role", value=sr.mention, inline=False)
            await ch.send(embed=e, view=CloseTicket())
            await b_int.response.send_message(f"✅ Ticket created → {ch.mention}", ephemeral=True)

    e = discord.Embed(description=description or "**🎟️ CREATE A TICKET BELOW**", color=get_color(color))
    await inter.response.send_message(embed=e, view=Panel())

@tree.command(name="create-embed")
@app_commands.describe(description="Embed text", color="Color name or hex")
async def mk_embed(inter: discord.Interaction, description: str, color: str="green"):
    if not inter.user.guild_permissions.manage_messages:
        return await inter.response.send_message("Need Manage Messages", ephemeral=True)
    await inter.response.send_message(embed=discord.Embed(description=description, color=get_color(color)))

@tree.command(name="ban")
@app_commands.describe(user="User to ban", reason="Reason")
async def ban(inter: discord.Interaction, user: discord.Member, reason: str="No reason"):
    if not inter.user.guild_permissions.ban_members: return await inter.response.send_message("No permission", ephemeral=True)
    if user.top_role >= inter.user.top_role and inter.user.id != inter.guild.owner_id:
        return await inter.response.send_message("Cannot ban higher/equal role", ephemeral=True)
    if user == inter.user: return await inter.response.send_message("Cannot ban yourself", ephemeral=True)
    await inter.guild.ban(user, reason=reason)
    e = discord.Embed(title="🔨 Banned", color=discord.Colour.red())
    e.add_field(name="User", value=user.mention, inline=False)
    e.add_field(name="Mod", value=inter.user.mention, inline=False)
    e.add_field(name="Reason", value=reason, inline=False)
    await inter.response.send_message(embed=e)

@tree.command(name="unban")
@app_commands.describe(user_id="User ID")
async def unban(inter: discord.Interaction, user_id: str):
    if not inter.user.guild_permissions.ban_members: return await inter.response.send_message("No permission", ephemeral=True)
    try: uid = int(user_id)
    except: return await inter.response.send_message("Invalid ID", ephemeral=True)
    async for entry in inter.guild.bans():
        if entry.user.id == uid:
            await inter.guild.unban(entry.user)
            e = discord.Embed(title="✅ Unbanned", color=discord.Colour.green())
            e.add_field(name="User", value=entry.user.mention, inline=False)
            e.add_field(name="Mod", value=inter.user.mention, inline=False)
            return await inter.response.send_message(embed=e)
    await inter.response.send_message("User not banned", ephemeral=True)

@tree.command(name="kick")
@app_commands.describe(user="User to kick", reason="Reason")
async def kick(inter: discord.Interaction, user: discord.Member, reason: str="No reason"):
    if not inter.user.guild_permissions.kick_members: return await inter.response.send_message("No permission", ephemeral=True)
    if user.top_role >= inter.user.top_role and inter.user.id != inter.guild.owner_id:
        return await inter.response.send_message("Cannot kick higher/equal role", ephemeral=True)
    if user == inter.user: return await inter.response.send_message("Cannot kick yourself", ephemeral=True)
    await inter.guild.kick(user, reason=reason)
    e = discord.Embed(title="👢 Kicked", color=discord.Colour.orange())
    e.add_field(name="User", value=user.mention, inline=False)
    e.add_field(name="Mod", value=inter.user.mention, inline=False)
    e.add_field(name="Reason", value=reason, inline=False)
    await inter.response.send_message(embed=e)

@tree.command(name="mute")
@app_commands.describe(user="User", time="1m/1h/1d", reason="Reason")
async def mute(inter: discord.Interaction, user: discord.Member, time: str="", reason: str="No reason"):
    if not inter.user.guild_permissions.moderate_members: return await inter.response.send_message("No permission", ephemeral=True)
    if user.top_role >= inter.user.top_role and inter.user.id != inter.guild.owner_id:
        return await inter.response.send_message("Cannot mute higher/equal role", ephemeral=True)
    if user == inter.user: return await inter.response.send_message("Cannot mute yourself", ephemeral=True)
    dur = parse_time(time)
    if dur:
        await user.timeout(discord.utils.utcnow()+timedelta(seconds=dur), reason=reason)
        e = discord.Embed(title="🔇 Timed Out", color=discord.Colour.orange())
        e.add_field(name="User", value=user.mention, inline=False)
        e.add_field(name="Duration", value=time, inline=False)
        e.add_field(name="Reason", value=reason, inline=False)
        await inter.response.send_message(embed=e)
    else:
        role = discord.utils.get(inter.guild.roles, name="Muted")
        if not role:
            role = await inter.guild.create_role(name="Muted")
            for ch in inter.guild.channels: await ch.set_permissions(role, send_messages=False, speak=False)
        if role in user.roles: return await inter.response.send_message("Already muted", ephemeral=True)
        await user.add_roles(role, reason=reason)
        e = discord.Embed(title="🔇 Muted", color=discord.Colour.red())
        e.add_field(name="User", value=user.mention, inline=False)
        e.add_field(name="Reason", value=reason, inline=False)
        await inter.response.send_message(embed=e)

@tree.command(name="unmute")
@app_commands.describe(user="User to unmute")
async def unmute(inter: discord.Interaction, user: discord.Member):
    if not inter.user.guild_permissions.moderate_members: return await inter.response.send_message("No permission", ephemeral=True)
    try: await user.timeout(None)
    except: pass
    role = discord.utils.get(inter.guild.roles, name="Muted")
    if role and role in user.roles: await user.remove_roles(role)
    e = discord.Embed(title="🔊 Unmuted", color=discord.Colour.green())
    e.add_field(name="User", value=user.mention, inline=False)
    await inter.response.send_message(embed=e)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try: await tree.sync()
    except Exception as e: print(f"Sync Error: {e}")

keep_alive()
TOKEN = os.getenv('TOKEN')
bot.run(TOKEN)
