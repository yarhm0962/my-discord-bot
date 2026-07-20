from flask import Flask
from threading import Thread
import os
import re
import base64
import aiohttp
import asyncio
import discord
from datetime import timedelta, datetime
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
WARNINGS = {}
TIMEOUT_DURATION = 300
LOADSTRING_SCHEDULES = {}

DAY_CHOICES = [
    app_commands.Choice(name="Sunday", value="0"),
    app_commands.Choice(name="Monday", value="1"),
    app_commands.Choice(name="Tuesday", value="2"),
    app_commands.Choice(name="Wednesday", value="3"),
    app_commands.Choice(name="Thursday", value="4"),
    app_commands.Choice(name="Friday", value="5"),
    app_commands.Choice(name="Saturday", value="6"),
]

DAY_NAMES = {
    "0": "Sunday", "1": "Monday", "2": "Tuesday",
    "3": "Wednesday", "4": "Thursday", "5": "Friday", "6": "Saturday"
}

def generate_wrapped_loadstring(user_url: str, active_day: str, script_name: str) -> str:
    lua_code = f'''-- ═══════════════════════════════════
-- 🔒 DAY-LOCKED SCRIPT — BOT PROTECTED
-- 📅 ACTIVE DAY: {DAY_NAMES[active_day]}
-- ═══════════════════════════════════

local ALLOWED_DAY = "{active_day}"
local TODAY = os.date("%w")

if TODAY ~= ALLOWED_DAY then
    print("🔒 SCRIPT DISABLED! Only works on {DAY_NAMES[active_day]}s")
    pcall(function()
        game:GetService("StarterGui"):SetCore("SendNotification", {{
            Title = "🔒 DISABLED",
            Text = "Only works on {DAY_NAMES[active_day]}s!",
            Duration = 6
        }})
    end)
    return
end

-- ✅ TODAY IS {DAY_NAMES[active_day]} — RUNNING YOUR SCRIPT
loadstring(game:HttpGet("{user_url}"))()
'''
    b64 = base64.b64encode(lua_code.encode('utf-8')).decode('utf-8')
    return f'loadstring(game:HttpGet("https://api-pastes.github.io/?b64={b64}"))()'

def parse_time(time_str):
    if not time_str: return None
    m = re.match(r'(\d+)([mhd])', time_str.lower().strip())
    if not m: return None
    a, u = int(m.group(1)), m.group(2)
    return a*60 if u=='m' else a*3600 if u=='h' else a*86400

def get_color(color_str):
    c = color_str.lower().strip()
    m = {"red":discord.Colour.red(),"green":discord.Colour.green(),"blue":discord.Colour.blue(),"gold":discord.Colour.gold(),"yellow":discord.Colour.yellow(),"orange":discord.Colour.orange(),"purple":discord.Colour.purple(),"pink":discord.Colour.magenta(),"cyan":discord.Colour.teal()}
    col = m.get(c, discord.Colour.green())
    if c.startswith("#"):
        try: col = discord.Colour(int(c.lstrip("#"),16))
        except: pass
    return col

def extract_url(text):
    pats = [
        r'game:HttpGet\s*\(\s*["\']([^"\']+)["\']',
        r'http\.get\s*\(\s*["\']([^"\']+)["\']',
        r'loadstring\s*\(\s*game:HttpGet\s*\(\s*["\']([^"\']+)["\']',
        r'loadstring\s*\(\s*http\.get\s*\(\s*["\']([^"\']+)["\']',
        r'["\'](https?://[^"\']+)["\']'
    ]
    for p in pats:
        m = re.search(p, text)
        if m: return None if "api.pastes.io" in m.group(1) else m.group(1)
    return text.strip() if text.strip().startswith(('http://','https://')) and "api.pastes.io" not in text else None

def smart_decode(code):
    if not code or len(code)<5: return code or ""
    orig, code = code, code.strip()
    m = re.match(r'^(loadstring\s*\(\s*)?(.+?)(\)\s*\([^)]*\)?\s*)?$', code, re.DOTALL)
    if m and not m.group(2).strip().startswith('game:HttpGet') and len(m.group(2).strip())>20: code=m.group(2).strip()
    pats = [
        r'base64\.decode\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']',
        r'["\']([A-Za-z0-9+/=]{30,})["\']',
        r'loadstring\s*\(\s*["\']([A-Za-z0-9+/=]{30,})["\']'
    ]
    for p in pats:
        for match in re.finditer(p, code):
            try:
                b64=match.group(1)
                b64+='='*(4-len(b64)%4) if len(b64)%4!=0 else ''
                d=base64.b64decode(b64).decode('utf-8',errors='ignore')
                return smart_decode(d) if len(d)>10 and not d.startswith('--') else code
            except: pass
    m=re.search(r'string\.reverse\s*\(\s*["\']([^"\']+)["\']', code)
    if m:
        rev=m.group(1)[::-1]
        if len(rev)>20:
            try:
                b64=rev
                b64+='='*(4-len(b64)%4) if len(b64)%4!=0 else ''
                d=base64.b64decode(b64).decode('utf-8',errors='ignore')
                return smart_decode(d) if len(d)>10 else smart_decode(rev)
            except: return smart_decode(rev) if len(rev)>10 else code
    lines=[l for l in code.split('\n') if not (l.strip().startswith('--')and len(l.strip())<50) and 'obfuscated'not in l.lower() and 'generated'not in l.lower() and (len(l.strip())>10 or l.strip())]
    code='\n'.join(lines)
    return code if len(code)>5 else orig

async def deobfuscate_from_url(url):
    try:
        if "api.pastes.io"in url: return None,"Error: api.pastes.io does not exist! Use links like rentry.co/raw/XXX"
        if "rentry.co"in url and "/raw/"not in url: url=url.replace("rentry.co/","rentry.co/raw/")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.get(url,timeout=30,allow_redirects=True)as r:
                if r.status!=200: return None,f"HTTP Error: Status {r.status}"
                c=await r.text()
                return (smart_decode(c),None)if c and len(c)>4 else (None,"Error: Empty response from URL")
    except Exception as e: return None,f"Fetch Error: {str(e)[:80]}"

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return await bot.process_commands(message)

    highest_role = max(message.guild.roles, key=lambda r: r.position)
    mentioned_highest = (highest_role in message.role_mentions) or any(highest_role in u.roles for u in message.mentions)
    if mentioned_highest:
        gid, uid = message.guild.id, message.author.id
        WARNINGS.setdefault(gid,{}); WARNINGS[gid].setdefault(uid,0); WARNINGS[gid][uid]+=1; c=WARNINGS[gid][uid]
        if c==1:
            e=discord.Embed(title="⚠️ Warning 1/3",color=discord.Colour.yellow())
            e.description=f"{message.author.mention}, you have received **Warning 1/3** for mentioning the highest role.\nPlease avoid doing this again."
            await message.channel.send(embed=e)
        elif c==2:
            e=discord.Embed(title="⚠️ Warning 2/3",color=discord.Colour.orange())
            e.description=f"{message.author.mention}, you have received **Warning 2/3** for mentioning the highest role.\nYou will be timed out after the next warning!"
            await message.channel.send(embed=e)
        elif c>=3:
            try: await message.author.timeout(discord.utils.utcnow()+timedelta(seconds=TIMEOUT_DURATION),reason="Mentioned highest role 3 times")
            except:pass
            e=discord.Embed(title="⚠️ Warning 3/3 — User Timed Out!",color=discord.Colour.red())
            e.description=f"{message.author.mention}, you have received **Warning 3/3** and have been **timed out for 5 minutes**.\n\n⚠️ **Your warnings have been reset.**"
            await message.channel.send(embed=e); WARNINGS[gid][uid]=0

    await bot.process_commands(message)

@tree.command(name="add_loadstring",description="Create DAY-LOCKED loadstring — Bot controls execution")
@app_commands.describe(
    script_name="Required: Name of your script",
    your_loadstring="Required: Paste your full loadstring or raw URL",
    repeat_day="Required: Day when script is ALLOWED to run"
)
async def add_loadstring_cmd(interaction: discord.Interaction, script_name: str, your_loadstring: str, repeat_day: app_commands.Choice[str]):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Administrator permission required", ephemeral=True)
    
    user_url = extract_url(your_loadstring)
    if not user_url:
        if your_loadstring.strip().startswith(('http://','https://')):
            user_url = your_loadstring.strip()
        else:
            return await interaction.response.send_message("❌ Could not find valid URL in your loadstring", ephemeral=True)
    
    day_val = repeat_day.value
    day_name = DAY_NAMES[day_val]
    
    script_id = f"{script_name.replace(' ','_')}_{day_val}"
    LOADSTRING_SCHEDULES[script_id] = {
        "name": script_name,
        "user_url": user_url,
        "active_day": day_val
    }
    
    wrapped_ls = generate_wrapped_loadstring(user_url, day_val, script_name)
    
    embed = discord.Embed(title=f"✅ {script_name}", color=discord.Colour.teal())
    embed.add_field(name="📅 Active Only", value=f"**{day_name}s**", inline=False)
    embed.add_field(name="🔒 Protection", value="✅ **WRAPPED — DAY-LOCKED**\n❌ Auto-blocked on all other days\n✅ Auto-reactivates every week", inline=False)
    embed.add_field(name="🔗 Original URL", value=f"||{user_url}||", inline=False)
    embed.description = f"**📋 COPY THIS LOADSTRING:**\n```{wrapped_ls}```"
    embed.set_footer(text=f"🔒 Runs ONLY on {day_name}s — Day check built-in")
    
    await interaction.response.send_message(embed=embed)

@bot.command(name='cmds')
async def show_cmds(ctx):
    if ctx.author.bot:return
    e=discord.Embed(title="📋 Bot Commands",color=discord.Colour.blue())
    e.add_field(name="Prefix Commands",value="`.d <link>` - Deobfuscate from URL\n`.cmds` - Show this command list",inline=False)
    e.add_field(name="Slash Commands",value="`/add_loadstring` - Create DAY-LOCKED wrapped loadstring\n`/deobf-file file:` - Deobfuscate uploaded .lua file\n`/create-ticket` - Create ticket panel\n`/create-embed description:` - Create custom embed\n`/ban user:@User` - Ban a user\n`/unban user_id:` - Unban a user by ID\n`/kick user:@User` - Kick a user\n`/mute user:@User` - Mute a user with duration\n`/unmute user:@User` - Unmute a user",inline=False)
    e.add_field(name="Auto-Features",value="**Mention Protection** - Auto-warns & times out users who mention the highest role 3 times",inline=False)
    await ctx.send(embed=e)
    try: await ctx.message.delete()
    except: pass

@bot.command(name='d')
async def deobf_prefix(ctx,*,link:str):
    if ctx.author.bot:return
    m=await ctx.send("Processing...")
    u=extract_url(link)
    if not u: return await m.edit(content="Error: No valid URL found")
    c,e=await deobfuscate_from_url(u)
    if e: return await m.edit(content=f"Error: {e}")
    fn=f"deobfuscated_{ctx.message.id}.lua"
    with open(fn,'w',encoding='utf-8')as f:f.write(c)
    await m.edit(content="✅ Deobfuscated successfully")
    await ctx.send(file=File(fn))
    os.remove(fn)

@tree.command(name="deobf-file",description="Upload a .lua file to deobfuscate")
@app_commands.describe(file="Upload your obfuscated .lua or .txt file")
async def deobf_file(interaction:discord.Interaction,file:discord.Attachment):
    if not file.filename.endswith(('.lua','.txt')):
        return await interaction.response.send_message("Error: Please upload a .lua or .txt file",ephemeral=True)
    await interaction.response.defer()
    try: c=(await file.read()).decode('utf-8',errors='ignore')
    except Exception as e: return await interaction.followup.send(f"Error: Could not read file - {str(e)}",ephemeral=True)
    d=smart_decode(c)
    fn=f"deobfuscated_{interaction.id}.lua"
    with open(fn,'w',encoding='utf-8')as f:f.write(d)
    await interaction.followup.send(content="✅ Deobfuscated successfully",file=File(fn))
    os.remove(fn)

class CloseTicketView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label="Close Ticket",style=discord.ButtonStyle.danger,custom_id="close_ticket_btn")
    async def close_btn(self,interaction:discord.Interaction,button:discord.ui.Button):
        settings = TICKET_SETTINGS.get(interaction.channel.id)
        if not settings:
            return await interaction.response.send_message("Error: Could not verify ticket permissions",ephemeral=True)
        staff_role = interaction.guild.get_role(settings["admin_role_id"])
        is_staff = staff_role in interaction.user.roles if staff_role else False
        if not (is_staff or interaction.user.guild_permissions.manage_channels):
            return await interaction.response.send_message("Error: You do not have permission to close this ticket",ephemeral=True)
        await interaction.response.send_message("Closing ticket in 3 seconds...")
        await asyncio.sleep(3)
        await interaction.channel.delete()

@tree.command(name="create-ticket",description="Create a ticket panel")
@app_commands.describe(
    admin_role="Required: Role that manages and responds to tickets",
    category="Required: Category where tickets will be created",
    description="Optional: Custom panel description",
    color="Optional: Panel embed color (name or hex, default: green)"
)
async def create_ticket_panel(interaction: discord.Interaction, admin_role: discord.Role, category: discord.CategoryChannel, description: str = "", color: str = "green"):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Error: Administrator permission is required",ephemeral=True)
    panel_description = description if description else "**CREATE A TICKET BELOW 🎟️**"
    embed_color = get_color(color)
    TICKET_SETTINGS[interaction.channel.id] = {
        "admin_role_id": admin_role.id,
        "category_id": category.id,
        "guild_id": interaction.guild.id
    }
    class TicketPanel(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
        @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.success, custom_id="create_ticket_btn")
        async def create_btn(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
            settings = TICKET_SETTINGS.get(btn_interaction.channel_id)
            if not settings:
                return await btn_interaction.response.send_message("Error: Panel is not configured properly",ephemeral=True)
            guild = btn_interaction.guild
            ticket_category = guild.get_channel(settings["category_id"])
            staff_role = guild.get_role(settings["admin_role_id"])
            if not ticket_category or not staff_role:
                return await btn_interaction.response.send_message("Error: Category or Admin Role was not found",ephemeral=True)
            channel_name = f"{btn_interaction.user.name}-ticket"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                btn_interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            }
            ticket_channel = await ticket_category.create_text_channel(name=channel_name, overwrites=overwrites)
            TICKET_SETTINGS[ticket_channel.id] = {
                "admin_role_id": admin_role.id,
                "creator_id": btn_interaction.user.id,
                "category_id": category.id
            }
            ticket_embed = discord.Embed(title="Ticket Created", description="**Please wait for a staff member to assist you**", color=discord.Colour.green())
            ticket_embed.add_field(name="Created By", value=btn_interaction.user.mention, inline=False)
            ticket_embed.add_field(name="Staff", value=staff_role.mention, inline=False)
            ticket_embed.add_field(name="Access", value="Only you and staff members can view this ticket", inline=False)
            ticket_embed.add_field(name="Actions", value="Click Close Ticket to close this channel", inline=False)
            await ticket_channel.send(embed=ticket_embed, view=CloseTicketView())
            await btn_interaction.response.send_message(f"Success: Ticket created → {ticket_channel.mention}",ephemeral=True)
    embed = discord.Embed(description=panel_description, color=embed_color)
    await interaction.response.send_message(embed=embed, view=TicketPanel())

@tree.command(name="create-embed",description="Create a custom embed")
@app_commands.describe(
    description="Required: The embed description text",
    color="Optional: Embed color (name or hex, default: green)"
)
async def create_embed(interaction: discord.Interaction, description: str, color: str = "green"):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message("Error: Missing permission — Manage Messages",ephemeral=True)
    embed_color = get_color(color)
    embed = discord.Embed(description=description, color=embed_color)
    await interaction.response.send_message(embed=embed)

@tree.command(name="ban",description="Ban a user from the server")
@app_commands.describe(user="Required: User to ban", reason="Optional: Reason for the ban")
async def ban_user(interaction: discord.Interaction, user: discord.Member, reason: str = ""):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("Error: Missing permission — Ban Members",ephemeral=True)
    if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("Error: You cannot ban a user with a higher or equal role",ephemeral=True)
    if user == interaction.user:
        return await interaction.response.send_message("Error: You cannot ban yourself",ephemeral=True)
    ban_reason = reason if reason else "No reason provided"
    await interaction.guild.ban(user, reason=ban_reason)
    embed = discord.Embed(title="🔨 User Banned", color=discord.Colour.red())
    embed.add_field(name="User", value=user.mention, inline=False)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
    embed.add_field(name="Reason", value=ban_reason, inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="unban",description="Unban a user from the server")
@app_commands.describe(user_id="Required: ID of the user to unban")
async def unban_user(interaction: discord.Interaction, user_id: str):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("Error: Missing permission — Ban Members",ephemeral=True)
    try:
        user_id = int(user_id)
        banned_users = [entry async for entry in interaction.guild.bans()]
    except ValueError:
        return await interaction.response.send_message("Error: Invalid User ID",ephemeral=True)
    for ban_entry in banned_users:
        if ban_entry.user.id == user_id:
            await interaction.guild.unban(ban_entry.user)
            embed = discord.Embed(title="✅ User Unbanned", color=discord.Colour.green())
            embed.add_field(name="User", value=ban_entry.user.mention, inline=False)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
            return await interaction.response.send_message(embed=embed)
    return await interaction.response.send_message("Error: User was not found in the ban list",ephemeral=True)

@tree.command(name="kick",description="Kick a user from the server")
@app_commands.describe(user="Required: User to kick", reason="Optional: Reason for the kick")
async def kick_user(interaction: discord.Interaction, user: discord.Member, reason: str = ""):
    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message("Error: Missing permission — Kick Members",ephemeral=True)
    if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("Error: You cannot kick a user with a higher or equal role",ephemeral=True)
    if user == interaction.user:
        return await interaction.response.send_message("Error: You cannot kick yourself",ephemeral=True)
    kick_reason = reason if reason else "No reason provided"
    await interaction.guild.kick(user, reason=kick_reason)
    embed = discord.Embed(title="👢 User Kicked", color=discord.Colour.orange())
    embed.add_field(name="User", value=user.mention, inline=False)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
    embed.add_field(name="Reason", value=kick_reason, inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="mute",description="Mute a user")
@app_commands.describe(
    user="Required: User to mute",
    time="Optional: Enter a duration such as 1m, 1h, 1d, etc.",
    reason="Optional: Reason for the mute"
)
async def mute_user(interaction: discord.Interaction, user: discord.Member, time: str = "", reason: str = ""):
    if not interaction.user.guild_permissions.manage_roles or not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message("Error: Missing permission — Manage Roles or Moderate Members",ephemeral=True)
    if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("Error: You cannot mute a user with a higher or equal role",ephemeral=True)
    if user == interaction.user:
        return await interaction.response.send_message("Error: You cannot mute yourself",ephemeral=True)
    
    mute_reason = reason if reason else "No reason provided"
    duration = parse_time(time)
    
    if duration:
        try:
            await user.timeout(discord.utils.utcnow() + timedelta(seconds=duration), reason=mute_reason)
            embed = discord.Embed(title="🔇 User Timed Out", color=discord.Colour.orange())
            embed.add_field(name="User", value=user.mention, inline=False)
            embed.add_field(name="Duration", value=f"**{time}**", inline=False)
            embed.add_field(name="Reason", value=mute_reason, inline=False)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            return await interaction.response.send_message(f"Error: Could not time out user — {str(e)}",ephemeral=True)
    else:
        mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
        if not mute_role:
            mute_role = await interaction.guild.create_role(name="Muted")
            for channel in interaction.guild.channels:
                await channel.set_permissions(mute_role, send_messages=False, speak=False)
        
        if mute_role in user.roles:
            return await interaction.response.send_message("Error: User is already muted",ephemeral=True)
        
        await user.add_roles(mute_role, reason=mute_reason)
        embed = discord.Embed(title="🔇 User Muted", color=discord.Colour.red())
        embed.add_field(name="User", value=user.mention, inline=False)
        embed.add_field(name="Duration", value="**Permanent**", inline=False)
        embed.add_field(name="Reason", value=mute_reason, inline=False)
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
        await interaction.response.send_message(embed=embed)

@tree.command(name="unmute",description="Unmute a user")
@app_commands.describe(user="Required: User to unmute")
async def unmute_user(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.manage_roles or not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message("Error: Missing permission — Manage Roles or Moderate Members",ephemeral=True)
    
    try:
        await user.timeout(None)
    except:
        pass
    
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if mute_role and mute_role in user.roles:
        await user.remove_roles(mute_role)
        embed = discord.Embed(title="🔊 User Unmuted", color=discord.Colour.green())
        embed.add_field(name="User", value=user.mention, inline=False)
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(title="🔊 Timeout Removed", color=discord.Colour.green())
        embed.add_field(name="User", value=user.mention, inline=False)
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
        await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        await tree.sync()
        print("✅ Slash commands synced!")
    except Exception as e:
        print(f"⚠️ Sync Error: {e}")

keep_alive()
TOKEN = os.getenv('TOKEN')
bot.run(TOKEN)
