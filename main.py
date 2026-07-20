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
    pats = [r'game:HttpGet\s*\(\s*["\']([^"\']+)["\']',r'http\.get\s*\(\s*["\']([^"\']+)["\']',r'loadstring\s*\(\s*game:HttpGet\s*\(\s*["\']([^"\']+)["\']',r'loadstring\s*\(\s*http\.get\s*\(\s*["\']([^"\']+)["\']',r'["\'](https?://[^"\']+)["\']']
    for p in pats:
        m = re.search(p,text)
        if m: return None if "api.pastes.io" in m.group(1) else m.group(1)
    return text.strip() if text.strip().startswith(('http://','https://')) and "api.pastes.io" not in text else None

def smart_decode(code):
    if not code or len(code)<5: return code or ""
    orig, code = code, code.strip()
    m = re.match(r'^(loadstring\s*\(\s*)?(.+?)(\)\s*\([^)]*\)?\s*)?$', code, re.DOTALL)
    if m and not m.group(2).strip().startswith('game:HttpGet') and len(m.group(2).strip())>20: code=m.group(2).strip()
    pats = [r'base64\.decode\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']',r'["\']([A-Za-z0-9+/=]{30,})["\']',r'loadstring\s*\(\s*["\']([A-Za-z0-9+/=]{30,})["\']']
    for p in pats:
        for match in re.finditer(p,code):
            try: b64=match.group(1); b64+='='*(4-len(b64)%4)if len(b64)%4!=0 else ''; d=base64.b64decode(b64).decode('utf-8',errors='ignore'); return smart_decode(d) if len(d)>10 and not d.startswith('--') else code
            except: pass
    m=re.search(r'string\.reverse\s*\(\s*["\']([^"\']+)["\']',code)
    if m:
        rev=m.group(1)[::-1]
        if len(rev)>20:
            try: b64=rev; b64+='='*(4-len(b64)%4)if len(b64)%4!=0 else ''; d=base64.b64decode(b64).decode('utf-8',errors='ignore'); return smart_decode(d) if len(d)>10 else smart_decode(rev)
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
        if c==1: e=discord.Embed(title="⚠️ Warning 1/3",color=discord.Colour.yellow()); e.description=f"{message.author.mention}, you have received **Warning 1/3** for mentioning the highest role.\nPlease avoid doing this again."; await message.channel.send(embed=e)
        elif c==2: e=discord.Embed(title="⚠️ Warning 2/3",color=discord.Colour.orange()); e.description=f"{message.author.mention}, you have received **Warning 2/3** for mentioning the highest role.\nYou will be timed out after the next warning!"; await message.channel.send(embed=e)
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
    e.add_field(name="Prefix",value="`.d <link>` - Deobfuscate\n`.cmds` - Show this list",inline=False)
    e.add_field(name="Slash",value="`/add_loadstring` - Create DAY-LOCKED wrapped loadstring\n`/deobf-file` - Deobfuscate file\n`/create-ticket` - Ticket panel\n`/create-embed` - Custom embed\n`/ban` `/unban` `/kick` `/mute` `/unmute`",inline=False)
    await ctx.send(embed=e); await ctx.message.delete()

@bot.command(name='d')
async def deobf_prefix(ctx,*,link:str):
    if ctx.author.bot:return
    m=await ctx.send("Processing...")
    u=extract_url(link)
    if not u: return await m.edit(content="Error: No valid URL found")
    c,e=await deobfuscate_from_url(u)
    if e: return await m.edit(content=f"Error: {e}")
    fn=f"deobf_{ctx.message.id}.lua"
    with open(fn,'w',encoding='utf-8')as f:f.write(c)
    await m.edit(content="✅ Deobfuscated successfully"); await ctx.send(file=File(fn)); os.remove(fn)

@tree.command(name="deobf-file")
async def deobf_file(interaction:discord.Interaction,file:discord.Attachment):
    if not file.filename.endswith(('.lua','.txt')):
        return await interaction.response.send_message("Error: Upload .lua or .txt",ephemeral=True)
    await interaction.response.defer()
    try: c=(await file.read()).decode('utf-8',errors='ignore')
    except Exception as e: return await interaction.followup.send(f"Error: {e}",ephemeral=True)
    d=smart_decode(c); fn=f"deobf_{interaction.id}.lua"
    with open(fn,'w',encoding='utf-8')as f:f.write(d)
    await interaction.followup.send("✅ Deobfuscated",file=File(fn)); os.remove(fn)

class CloseTicketView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label="Close Ticket",style=discord.ButtonStyle.danger,custom_id="close_ticket")
    async def close(self,i,b):
        s=TICKET_SETTINGS.get(i.channel.id)
        if not s: return await i.response.send_message("Error: Not configured",ephemeral=True)
        sr=i.guild.get_role(s["admin_role_id"])
        if not (sr in i.user.roles if sr else False) and not i.user.guild_permissions.manage_channels:
            return await i.response.send_message("No permission",ephemeral=True)
        await i.response.send_message("Closing in 3s..."); await asyncio.sleep(3); await i.channel.delete()

@tree.command(name="create-ticket")
@app_commands.describe(admin_role="Staff role",category="Ticket category",description="Panel text",color="Embed color")
async def create_ticket(i,admin_role:discord.Role,category:discord.CategoryChannel,description:str="",color:str="green"):
    if not i.user.guild_permissions.administrator: return await i.response.send_message("No permission",ephemeral=True)
    desc=description or "**🎟️ CREATE A TICKET BELOW**"
    TICKET_SETTINGS[i.channel.id]={"admin_role_id":admin_role.id,"category_id":category.id}
    class Panel(discord.ui.View):
        def __init__(s):super().__init__(timeout=None)
        @discord.ui.button(label="Create Ticket",style=discord.ButtonStyle.success)
        async def create(s,int,b):
            cat=int.guild.get_channel(TICKET_SETTINGS[int.channel_id]["category_id"])
            sr=int.guild.get_role(TICKET_SETTINGS[int.channel_id]["admin_role_id"])
            overwrites={int.guild.default_role:discord.PermissionOverwrite(view_channel=False),int.user:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True),sr:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True),int.guild.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True)}
            ch=await cat.create_text_channel(name=f"{int.user.name}-ticket",overwrites=overwrites)
            e=discord.Embed(title="Ticket Created",description="**Wait for staff to assist**",color=discord.Colour.green())
            e.add_field(name="Created By",value=int.user.mention,inline=False)
            e.add_field(name="Staff",value=sr.mention,inline=False)
            await ch.send(embed=e,view=CloseTicketView()); await int.response.send_message(f"✅ Created → {ch.mention}",ephemeral=True)
    await i.response.send_message(embed=discord.Embed(description=desc,color=get_color(color)),view=Panel())

@tree.command(name="create-embed")
async def make_embed(i,description:str,color:str="green"):
    if not i.user.guild_permissions.manage_messages: return await i.response.send_message("No permission",ephemeral=True)
    await i.response.send_message(embed=discord.Embed(description=description,color=get_color(color)))

@tree.command(name="ban")
async def ban(i,user:discord.Member,reason:str="No reason provided"):
    if not i.user.guild_permissions.ban_members: return await i.response.send_message("No permission",ephemeral=True)
    if user.top_role>=i.user.top_role and i.user.id!=i.guild.owner_id: return await i.response.send_message("Cannot ban higher role",ephemeral=True)
    if user==i.user: return await i.response.send_message("Cannot ban yourself",ephemeral=True)
    await i.guild.ban(user,reason=reason); e=discord.Embed(title="🔨 User Banned",color=discord.Colour.red())
    e.add_field(name="User",value=user.mention); e.add_field(name="Reason",value=reason); await i.response.send_message(embed=e)

@tree.command(name="unban")
async def unban(i,user_id:str):
    if not i.user.guild_permissions.ban_members: return await i.response.send_message("No permission",ephemeral=True)
    try: uid=int(user_id); bans=[e async for e in i.guild.bans()]
    except: return await i.response.send_message("Invalid ID",ephemeral=True)
    for b in bans:
        if b.user.id==uid: await i.guild.unban(b.user); return await i.response.send_message(embed=discord.Embed(title="✅ Unbanned",description=b.user.mention,color=discord.Colour.green()))
    await i.response.send_message("User not banned",ephemeral=True)

@tree.command(name="kick")
async def kick(i,user:discord.Member,reason:str="No reason provided"):
    if not i.user.guild_permissions.kick_members: return await i.response.send_message("No permission",ephemeral=True)
    if user.top_role>=i.user.top_role and i.user.id!=i.guild.owner_id: return await i.response.send_message("Cannot kick higher role",ephemeral=True)
    if user==i.user: return await i.response.send_message("Cannot kick yourself",ephemeral=True)
    await i.guild.kick(user,reason=reason); e=discord.Embed(title="👢 User Kicked",color=discord.Colour.orange())
    e.add_field(name="User",value=user.mention); e.add_field(name="Reason",value=reason); await i.response.send_message(embed=e)

@tree.command(name="mute")
async def mute(i,user:discord.Member,time:str="",reason:str="No reason provided"):
    if not i.user.guild_permissions.manage_roles or not i.user.guild_permissions.moderate_members: return await i.response.send_message("No permission",ephemeral=True)
    if user.top_role>=i.user.top_role and i.user.id!=i.guild.owner_id: return await i.response.send_message("Cannot mute higher role",ephemeral=True)
    if user==i.user: return await i.response.send_message("Cannot mute yourself",ephemeral=True)
    dur=parse_time(time)
    if dur:
        await user.timeout(discord.utils.utcnow()+timedelta(seconds=dur),reason=reason)
        e=discord.Embed(title="🔇 Timed Out",color=discord.Colour.orange())
        e.add_field(name="User",value=user.mention); e.add_field(name="Duration",value=time); e.add_field(name="Reason",value=reason)
        await i.response.send_message(embed=e)
    else:
        r=discord.utils.get(i.guild.roles,name="Muted") or await i.guild.create_role(name="Muted")
        if r in user.roles: return await i.response.send_message("Already muted",ephemeral=True)
        [await ch.set_permissions(r,send_messages=False,speak=False) for ch in i.guild.channels]
        await user.add_roles(r,reason=reason)
        e=discord.Embed(title="🔇 Muted",color=discord.Colour.red())
        e.add_field(name="User",value=user.mention); e.add_field(name="Reason",value=reason); await i.response.send_message(embed=e)

@tree.command(name="unmute")
async def unmute(i,user:discord.Member):
    if not i.user.guild_permissions.manage_roles or not i.user.guild_permissions.moderate_members: return await i.response.send_message("No permission",ephemeral=True)
    try: await user.timeout(None)
    except:pass
    r=discord.utils.get(i.guild.roles,name="Muted")
    if r and r in user.roles: await user.remove_roles(r); txt="🔊 Unmuted"
    else: txt="🔊 Timeout Removed"
    await i.response.send_message(embed=discord.Embed(title=txt,color=discord.Colour.green()).add_field(name="User",value=user.mention))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try: await tree.sync()
    except Exception as e: print(f"Sync Error: {e}")

keep_alive()
TOKEN=os.getenv('TOKEN')
bot.run(TOKEN)
