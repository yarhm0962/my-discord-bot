from flask import Flask
from threading import Thread
import os
import re
import json
import aiohttp
import asyncio
import discord
from datetime import datetime, timedelta
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

async def upload_to_pastefy(content):
    try:
        payload = {"content": content}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post("https://pastefy.app/api/pastes", json=payload, headers={"Content-Type":"application/json"}) as r:
                if r.status in (200, 201):
                    data = await r.json()
                    paste_id = data.get("id")
                    if paste_id:
                        return f"https://pastefy.app/{paste_id}/raw"
    except Exception as e:
        print(f"Pastefy Error: {e}")
    return None

def generate_wrapped_lua(user_url):
    return f'''local D=os.date("%w")
if D~="0" then
pcall(function()
game:GetService("StarterGui"):SetCore("SendNotification",{{Title="DISABLED",Text="Only Sundays!",Duration=6}})
end)
return
end
loadstring(game:HttpGet("{user_url}"))()'''

def parse_time(time_str):
    if not time_str: return None
    m = re.match(r'(\d+)([mhd])', time_str.lower().strip())
    if not m: return None
    a,u=int(m.group(1)),m.group(2)
    return a*60 if u=='m' else a*3600 if u=='h' else a*86400

def get_color(color_str):
    c=color_str.lower().strip()
    m={"red":discord.Colour.red(),"green":discord.Colour.green(),"blue":discord.Colour.blue(),"gold":discord.Colour.gold(),"yellow":discord.Colour.yellow(),"orange":discord.Colour.orange(),"purple":discord.Colour.purple(),"pink":discord.Colour.magenta(),"cyan":discord.Colour.teal()}
    col=m.get(c,discord.Colour.green())
    if c.startswith("#"):
        try: col=discord.Colour(int(c.lstrip("#"),16))
        except:pass
    return col

def extract_url(text):
    text = text.strip()
    if text.startswith(('http://','https://')):
        return text.split()[0]
    match = re.search(r'["\'](https?://[^"\']+)["\']', text)
    if match:
        return match.group(1)
    return None

def smart_decode(code):
    if not code or len(code)<5: return code or ""
    orig,code=code,code.strip()
    m=re.match(r'^(loadstring\s*\(\s*)?(.+?)(\)\s*\([^)]*\)?\s*)?$',code,re.DOTALL)
    if m and not m.group(2).strip().startswith('game:HttpGet') and len(m.group(2).strip())>20: code=m.group(2).strip()
    pats=[r'base64\.decode\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']',r'["\']([A-Za-z0-9+/=]{30,})["\']',r'loadstring\s*\(\s*["\']([A-Za-z0-9+/=]{30,})["\']']
    for p in pats:
        for match in re.finditer(p,code):
            try:
                b64=match.group(1)
                b64+='='*(4-len(b64)%4)if len(b64)%4!=0 else ''
                d=base64.b64decode(b64).decode('utf-8',errors='ignore')
                return smart_decode(d)if len(d)>10 and not d.startswith('--')else code
            except:pass
    m=re.search(r'string\.reverse\s*\(\s*["\']([^"\']+)["\']',code)
    if m:
        rev=m.group(1)[::-1]
        if len(rev)>20:
            try:
                b64=rev
                b64+='='*(4-len(b64)%4)if len(b64)%4!=0 else ''
                d=base64.b64decode(b64).decode('utf-8',errors='ignore')
                return smart_decode(d)if len(d)>10 else smart_decode(rev)
            except:return smart_decode(rev)if len(rev)>10 else code
    lines=[l for l in code.split('\n')if len(l.strip())>10 or l.strip()]
    code='\n'.join(lines)
    return code if len(code)>5 else orig

async def deobfuscate_from_url(url):
    try:
        if "rentry.co"in url and "/raw/"not in url: url=url.replace("rentry.co/","rentry.co/raw/")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))as s:
            async with s.get(url,timeout=30,allow_redirects=True)as r:
                if r.status!=200: return None,f"HTTP Error: Status {r.status}"
                c=await r.text()
                return (smart_decode(c),None)if c and len(c)>4 else (None,"Empty response")
    except Exception as e: return None,f"Fetch Error: {str(e)[:80]}"

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return await bot.process_commands(message)
    highest_role = max(message.guild.roles, key=lambda r: r.position)
    mentioned_highest = (highest_role in message.role_mentions) or any(highest_role in u.roles for u in message.mentions)
    if mentioned_highest:
        gid, uid = str(message.guild.id), str(message.author.id)
        if gid not in WARNINGS: WARNINGS[gid] = {}
        if uid not in WARNINGS[gid]: WARNINGS[gid][uid] = 0
        WARNINGS[gid][uid] += 1
        count = WARNINGS[gid][uid]
        if count == 1:
            e = discord.Embed(title="⚠️ Warning 1/3", color=discord.Colour.yellow())
            e.description = f"{message.author.mention}, please do not mention the highest role."
            await message.channel.send(embed=e)
        elif count == 2:
            e = discord.Embed(title="⚠️ Warning 2/3", color=discord.Colour.orange())
            e.description = f"{message.author.mention}, one more warning and you will be timed out."
            await message.channel.send(embed=e)
        elif count >= 3:
            try:
                until = discord.utils.utcnow() + timedelta(seconds=TIMEOUT_DURATION)
                await message.author.timeout(until, reason="Mentioned highest role repeatedly")
            except: pass
            e = discord.Embed(title="🔒 Warning 3/3 — Timed Out!", color=discord.Colour.red())
            e.description = f"{message.author.mention} has been timed out for 5 minutes.\n**Warnings frozen at 3 — no more counting.**"
            await message.channel.send(embed=e)
            WARNINGS[gid][uid] = 3
    await bot.process_commands(message)

@tree.command(name="add_loadstring",description="Create SUNDAY-LOCKED loadstring (PASTEFY)")
@app_commands.describe(script_name="Name of your script",your_loadstring="Paste URL OR full loadstring")
async def add_loadstring_cmd(interaction:discord.Interaction,script_name:str,your_loadstring:str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Permission required: Administrator",ephemeral=True)
    await interaction.response.defer()
    user_url = extract_url(your_loadstring)
    if not user_url:
        return await interaction.followup.send("❌ No URL found. Enter direct URL like `https://...` or full loadstring",ephemeral=True)
    lua_code = generate_wrapped_lua(user_url)
    pastefy_url = await upload_to_pastefy(lua_code)
    if not pastefy_url:
        return await interaction.followup.send("❌ Pastefy upload failed. Try again in a few seconds.",ephemeral=True)
    wrapped_ls = f'loadstring(game:HttpGet("{pastefy_url}"))()'
    script_id = f"{script_name.replace(' ','_')}_SUNDAY"
    LOADSTRING_SCHEDULES[script_id] = {"name":script_name,"user_url":user_url,"pastefy_url":pastefy_url}
    embed = discord.Embed(title=f"✅ {script_name}",color=discord.Colour.teal())
    embed.add_field(name="🔒 Active Only",value="SUNDAYS ONLY",inline=False)
    embed.add_field(name="📦 Pastefy URL",value=f"||{pastefy_url}||",inline=False)
    embed.add_field(name="🔗 Original URL",value=f"||{user_url}||",inline=False)
    embed.description = f"**📋 COPY THIS LOADSTRING:**\n```lua\n{wrapped_ls}\n```"
    embed.set_footer(text="Runs ONLY on Sundays. Blocked Mon-Sat")
    await interaction.followup.send(embed=embed)

@bot.command(name='cmds')
async def show_cmds(ctx):
    if ctx.author.bot:return
    e=discord.Embed(title="Bot Commands",color=discord.Colour.blue())
    e.add_field(name="Prefix",value="`.d <link>` Deobfuscate\n`.cmds` Show commands",inline=False)
    e.add_field(name="Slash",value="`/add_loadstring` SUNDAY-LOCKED via PASTEFY\n`/deobf-file` Deobfuscate file\n`/create-ticket` Ticket panel\n`/create-embed` Custom embed\n`/ban` `/unban` `/kick` `/mute` `/unmute`",inline=False)
    await ctx.send(embed=e)
    try:await ctx.message.delete()
    except:pass

@bot.command(name='d')
async def deobf_prefix(ctx,*,link:str):
    if ctx.author.bot:return
    m=await ctx.send("Processing...")
    u=extract_url(link)
    if not u:return await m.edit(content="No valid URL found")
    c,e=await deobfuscate_from_url(u)
    if e:return await m.edit(content=f"Error: {e}")
    fn=f"deobf_{ctx.message.id}.lua"
    with open(fn,'w',encoding='utf-8')as f:f.write(c)
    await m.edit(content="Deobfuscated");await ctx.send(file=File(fn));os.remove(fn)

@tree.command(name="deobf-file",description="Upload .lua or .txt file to deobfuscate")
async def deobf_file(interaction:discord.Interaction,file:discord.Attachment):
    if not file.filename.endswith(('.lua','.txt')):
        return await interaction.response.send_message("Upload .lua or .txt file",ephemeral=True)
    await interaction.response.defer()
    try:c=(await file.read()).decode('utf-8',errors='ignore')
    except Exception as e:return await interaction.followup.send(f"Error reading file: {e}",ephemeral=True)
    d=smart_decode(c);fn=f"deobf_{interaction.id}.lua"
    with open(fn,'w',encoding='utf-8')as f:f.write(d)
    await interaction.followup.send("Deobfuscated successfully",file=File(fn));os.remove(fn)

class CloseTicketView(discord.ui.View):
    def __init__(self):super().__init__(timeout=None)
    @discord.ui.button(label="Close Ticket",style=discord.ButtonStyle.danger,custom_id="close_ticket_button")
    async def close_ticket_button(self,interaction:discord.Interaction,button:discord.ui.Button):
        settings=TICKET_SETTINGS.get(interaction.channel.id)
        if not settings:return await interaction.response.send_message("Error: Ticket settings not found",ephemeral=True)
        staff_role=interaction.guild.get_role(settings["admin_role_id"])
        is_staff=staff_role in interaction.user.roles if staff_role else False
        if not (is_staff or interaction.user.guild_permissions.manage_channels):
            return await interaction.response.send_message("No permission to close ticket",ephemeral=True)
        await interaction.response.send_message("Closing ticket in 3 seconds...")
        await asyncio.sleep(3);await interaction.channel.delete()

@tree.command(name="create-ticket",description="Create a ticket panel")
@app_commands.describe(admin_role="Role that manages tickets",category="Category where tickets appear",description="Custom panel message",color="Embed color (name or hex)")
async def create_ticket_panel(interaction:discord.Interaction,admin_role:discord.Role,category:discord.CategoryChannel,description:str="",color:str="green"):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Administrator permission required",ephemeral=True)
    panel_description=description if description else "CREATE A TICKET BELOW"
    embed_color=get_color(color)
    TICKET_SETTINGS[interaction.channel.id]={"admin_role_id":admin_role.id,"category_id":category.id}
    class TicketPanel(discord.ui.View):
        def __init__(self):super().__init__(timeout=None)
        @discord.ui.button(label="Create Ticket",style=discord.ButtonStyle.success,custom_id="create_ticket_button")
        async def create_ticket_btn(self,btn_interaction:discord.Interaction,button:discord.ui.Button):
            settings=TICKET_SETTINGS.get(btn_interaction.channel_id)
            if not settings:return await btn_interaction.response.send_message("Error: Panel not configured",ephemeral=True)
            guild=btn_interaction.guild
            ticket_category=guild.get_channel(settings["category_id"])
            staff_role=guild.get_role(settings["admin_role_id"])
            if not ticket_category or not staff_role:
                return await btn_interaction.response.send_message("Error: Category or role not found",ephemeral=True)
            channel_name=f"{btn_interaction.user.name}-ticket"
            overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=False),btn_interaction.user:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True),staff_role:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True),guild.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True)}
            ticket_channel=await ticket_category.create_text_channel(name=channel_name,overwrites=overwrites)
            ticket_embed=discord.Embed(title="Ticket Created",description="Wait for staff to assist",color=discord.Colour.green())
            ticket_embed.add_field(name="Created By",value=btn_interaction.user.mention,inline=False)
            ticket_embed.add_field(name="Staff",value=staff_role.mention,inline=False)
            await ticket_channel.send(embed=ticket_embed,view=CloseTicketView())
            await btn_interaction.response.send_message(f"Ticket created → {ticket_channel.mention}",ephemeral=True)
    embed=discord.Embed(description=panel_description,color=embed_color)
    await interaction.response.send_message(embed=embed,view=TicketPanel())

@tree.command(name="create-embed",description="Create a custom embed message")
@app_commands.describe(description="Embed content text",color="Embed color (name or hex)")
async def create_embed_cmd(interaction:discord.Interaction,description:str,color:str="green"):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message("Manage Messages permission required",ephemeral=True)
    embed_color=get_color(color)
    embed=discord.Embed(description=description,color=embed_color)
    await interaction.response.send_message(embed=embed)

@tree.command(name="ban",description="Ban a user from the server")
@app_commands.describe(user="User to ban",reason="Reason for ban")
async def ban_user_cmd(interaction:discord.Interaction,user:discord.Member,reason:str="No reason provided"):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("Ban Members permission required",ephemeral=True)
    if user.top_role>=interaction.user.top_role and interaction.user.id!=interaction.guild.owner_id:
        return await interaction.response.send_message("Cannot ban user with higher or equal role",ephemeral=True)
    if user==interaction.user:return await interaction.response.send_message("Cannot ban yourself",ephemeral=True)
    await interaction.guild.ban(user,reason=reason)
    embed=discord.Embed(title="User Banned",color=discord.Colour.red())
    embed.add_field(name="User",value=user.mention,inline=False)
    embed.add_field(name="Moderator",value=interaction.user.mention,inline=False)
    embed.add_field(name="Reason",value=reason,inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="unban",description="Unban a user by ID")
@app_commands.describe(user_id="ID of user to unban")
async def unban_user_cmd(interaction:discord.Interaction,user_id:str):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("Ban Members permission required",ephemeral=True)
    try:uid=int(user_id);banned_users=[entry async for entry in interaction.guild.bans()]
    except ValueError:return await interaction.response.send_message("Invalid User ID",ephemeral=True)
    for ban_entry in banned_users:
        if ban_entry.user.id==uid:
            await interaction.guild.unban(ban_entry.user)
            embed=discord.Embed(title="User Unbanned",color=discord.Colour.green())
            embed.add_field(name="User",value=ban_entry.user.mention,inline=False)
            embed.add_field(name="Moderator",value=interaction.user.mention,inline=False)
            return await interaction.response.send_message(embed=embed)
    await interaction.response.send_message("User not found in ban list",ephemeral=True)

@tree.command(name="kick",description="Kick a user from the server")
@app_commands.describe(user="User to kick",reason="Reason for kick")
async def kick_user_cmd(interaction:discord.Interaction,user:discord.Member,reason:str="No reason provided"):
    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message("Kick Members permission required",ephemeral=True)
    if user.top_role>=interaction.user.top_role and interaction.user.id!=interaction.guild.owner_id:
        return await interaction.response.send_message("Cannot kick user with higher or equal role",ephemeral=True)
    if user==interaction.user:return await interaction.response.send_message("Cannot kick yourself",ephemeral=True)
    await interaction.guild.kick(user,reason=reason)
    embed=discord.Embed(title="User Kicked",color=discord.Colour.orange())
    embed.add_field(name="User",value=user.mention,inline=False)
    embed.add_field(name="Moderator",value=interaction.user.mention,inline=False)
    embed.add_field(name="Reason",value=reason,inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="mute",description="Mute or timeout a user")
@app_commands.describe(user="User to mute",time="Duration like 1m, 1h, 1d",reason="Reason for mute")
async def mute_user_cmd(interaction:discord.Interaction,user:discord.Member,time:str="",reason:str="No reason provided"):
    if not interaction.user.guild_permissions.manage_roles or not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message("Manage Roles or Moderate Members permission required",ephemeral=True)
    if user.top_role>=interaction.user.top_role and interaction.user.id!=interaction.guild.owner_id:
        return await interaction.response.send_message("Cannot mute user with higher or equal role",ephemeral=True)
    if user==interaction.user:return await interaction.response.send_message("Cannot mute yourself",ephemeral=True)
    duration=parse_time(time)
    if duration:
        await user.timeout(discord.utils.utcnow()+timedelta(seconds=duration),reason=reason)
        embed=discord.Embed(title="User Timed Out",color=discord.Colour.orange())
        embed.add_field(name="User",value=user.mention,inline=False)
        embed.add_field(name="Duration",value=time,inline=False)
        embed.add_field(name="Reason",value=reason,inline=False)
        embed.add_field(name="Moderator",value=interaction.user.mention,inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        mute_role=discord.utils.get(interaction.guild.roles,name="Muted")
        if not mute_role:
            mute_role=await interaction.guild.create_role(name="Muted")
            for channel in interaction.guild.channels:
                await channel.set_permissions(mute_role,send_messages=False,speak=False)
        if mute_role in user.roles:
            return await interaction.response.send_message("User is already muted",ephemeral=True)
        await user.add_roles(mute_role,reason=reason)
        embed=discord.Embed(title="User Muted",color=discord.Colour.red())
        embed.add_field(name="User",value=user.mention,inline=False)
        embed.add_field(name="Duration",value="Permanent",inline=False)
        embed.add_field(name="Reason",value=reason,inline=False)
        embed.add_field(name="Moderator",value=interaction.user.mention,inline=False)
        await interaction.response.send_message(embed=embed)

@tree.command(name="unmute",description="Remove mute or timeout from user")
@app_commands.describe(user="User to unmute")
async def unmute_user_cmd(interaction:discord.Interaction,user:discord.Member):
    if not interaction.user.guild_permissions.manage_roles or not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message("Manage Roles or Moderate Members permission required",ephemeral=True)
    try:await user.timeout(None)
    except:pass
    mute_role=discord.utils.get(interaction.guild.roles,name="Muted")
    if mute_role and mute_role in user.roles:
        await user.remove_roles(mute_role)
        embed=discord.Embed(title="User Unmuted",color=discord.Colour.green())
        embed.add_field(name="User",value=user.mention,inline=False)
        embed.add_field(name="Moderator",value=interaction.user.mention,inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        embed=discord.Embed(title="Timeout Removed",color=discord.Colour.green())
        embed.add_field(name="User",value=user.mention,inline=False)
        embed.add_field(name="Moderator",value=interaction.user.mention,inline=False)
        await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:await tree.sync()
    except Exception as e:print(f"Sync Error: {e}")

keep_alive()
TOKEN=os.getenv('TOKEN')
bot.run(TOKEN)
