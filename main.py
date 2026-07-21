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

# --- COMMAND GROUPS (Allows for spaces in command names) ---
create_group = app_commands.Group(name="create", description="Commands for creation")
warning_group = app_commands.Group(name="warning", description="Warning system commands")
deobf_group = app_commands.Group(name="deobf", description="Deobfuscation commands")
auto_group = app_commands.Group(name="auto", description="Automation commands")
auto_purge_group = app_commands.Group(name="purge", description="Auto purge commands", parent=auto_group)

tree.add_command(create_group)
tree.add_command(warning_group)
tree.add_command(deobf_group)
tree.add_command(auto_group)

TICKET_SETTINGS = {}
WARNINGS = {}
AUTO_PURGE_SETTINGS = {}  # channel_id -> {"duration": seconds, "task": asyncio.Task, "label": "1h"}
TIMEOUT_DURATION = 300  # Auto-timeout: 5 minutes = 300 seconds
MENTION_WARNINGS_ENABLED = True  # Default state for highest role mention warnings
IGNORED_WARNING_CHANNELS = set()  # Store channel IDs where mention warnings are disabled

def parse_time(time_str):
    if not time_str:
        return None
    match = re.match(r'(\d+)([smhd])', time_str.lower().strip())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == 's':
        return amount
    elif unit == 'm':
        return amount * 60
    elif unit == 'h':
        return amount * 3600
    elif unit == 'd':
        return amount * 86400
    return None

def get_color(color_str):
    color = color_str.lower().strip()
    color_map = {
        "red": discord.Colour.red(),
        "green": discord.Colour.green(),
        "blue": discord.Colour.blue(),
        "gold": discord.Colour.gold(),
        "yellow": discord.Colour.yellow(),
        "orange": discord.Colour.orange(),
        "purple": discord.Colour.purple(),
        "pink": discord.Colour.magenta(),
        "cyan": discord.Colour.teal(),
        "black": discord.Colour.from_rgb(0,0,0),
        "white": discord.Colour.from_rgb(255,255,255),
        "grey": discord.Colour.light_grey()
    }
    embed_color = color_map.get(color, discord.Colour.green())
    if color.startswith("#"):
        try:
            embed_color = discord.Colour(int(color.lstrip("#"), 16))
        except:
            embed_color = discord.Colour.green()
    return embed_color

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

def smart_decode(code):
    if not code or len(code) < 5:
        return code or ""
    original = code
    code = code.strip()
    m = re.match(r'^(loadstring\s*\(\s*)?(.+?)(\)\s*\([^)]*\)?\s*)?$', code, re.DOTALL)
    if m:
        inner = m.group(2).strip()
        if not inner.startswith('game:HttpGet') and len(inner) > 20:
            code = inner
    b64_matches = []
    patterns = [
        r'base64\.decode\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']',
        r'["\']([A-Za-z0-9+/=]{30,})["\']',
        r'loadstring\s*\(\s*["\']([A-Za-z0-9+/=]{30,})["\']'
    ]
    for pat in patterns:
        for match in re.finditer(pat, code):
            b64_matches.append(match.group(1))
    for b64_text in b64_matches:
        try:
            if len(b64_text) % 4 != 0:
                b64_text += '=' * (4 - len(b64_text) % 4)
            decoded = base64.b64decode(b64_text).decode('utf-8', errors='ignore')
            if decoded and len(decoded) > 10 and not decoded.startswith('--'):
                code = decoded
                return smart_decode(code)
        except:
            continue
    rev_pattern = r'string\.reverse\s*\(\s*["\']([^"\']+)["\']'
    m = re.search(rev_pattern, code)
    if m:
        try:
            reversed_str = m.group(1)[::-1]
            if len(reversed_str) > 20:
                try:
                    b64_part = reversed_str
                    if len(b64_part) % 4 != 0:
                        b64_part += '=' * (4 - len(b64_part) % 4)
                    decoded = base64.b64decode(b64_part).decode('utf-8', errors='ignore')
                    if decoded and len(decoded) > 10:
                        code = decoded
                        return smart_decode(code)
                except:
                    if len(reversed_str) > 10:
                        code = reversed_str
                        return smart_decode(code)
        except:
            pass
    lines = code.split('\n')
    clean_lines = []
    for line in lines:
        ls = line.strip()
        if ls.startswith('--') and len(ls) < 50:
            continue
        if 'obfuscated' in ls.lower() or 'generated' in ls.lower():
            continue
        if len(ls) > 10 or ls:
            clean_lines.append(line)
    code = '\n'.join(clean_lines)
    return code if len(code) > 5 else original

async def deobfuscate_from_url(url):
    try:
        if "api.pastes.io" in url:
            return None, "Error: api.pastes.io does not exist! Use links like rentry.co/raw/XXX"
        if "rentry.co" in url and "/raw/" not in url:
            url = url.replace("rentry.co/", "rentry.co/raw/")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(url, timeout=30, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None, f"HTTP Error: Status {resp.status}"
                code = await resp.text()
                if not code or len(code) < 5:
                    return None, "Error: Empty response from URL"
                deobf = smart_decode(code)
                return deobf, None
    except Exception as e:
        return None, f"Fetch Error: {str(e)[:80]}"

async def schedule_auto_purge(channel_id):
    """Waits for the configured inactivity duration, then purges the channel if no new message reset it."""
    settings = AUTO_PURGE_SETTINGS.get(channel_id)
    if not settings:
        return
    try:
        await asyncio.sleep(settings["duration"])
    except asyncio.CancelledError:
        return
    # Make sure the channel wasn't removed from auto-purge while we were sleeping
    if AUTO_PURGE_SETTINGS.get(channel_id) is not settings:
        return
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    try:
        await channel.purge(limit=None)
    except Exception:
        pass
    # Require fresh activity (2 messages) again before this can trigger next time
    settings["message_count"] = 0
    settings["task"] = None
    embed = discord.Embed(title="🧹 Auto Purge Completed", color=discord.Colour.green())
    embed.description = f"All messages in {channel.mention} were automatically purged after **{settings['label']}** of inactivity."
    try:
        await channel.send(embed=embed)
    except Exception:
        pass

@tree.command(name="say", description="Make the bot say a custom message with working mentions")
@app_commands.describe(message="Required: The message you want the bot to say")
async def say_message(interaction: discord.Interaction, message: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Error: Administrator permission is required to use this command.", ephemeral=True)
    
    await interaction.response.send_message("Message sent successfully!", ephemeral=True)
    allowed_mentions = discord.AllowedMentions(users=True, roles=True, everyone=True)
    await interaction.channel.send(content=message, allowed_mentions=allowed_mentions)

@warning_group.command(name="mention", description="Toggle mention warnings for the highest role On or Off")
@app_commands.describe(
    status="Select whether to turn mention warnings On or Off",
    ignored_channel="Optional: Select a channel where mention warnings will be ignored"
)
@app_commands.choices(status=[
    app_commands.Choice(name="On", value="on"),
    app_commands.Choice(name="Off", value="off")
])
async def warning_mention_toggle(interaction: discord.Interaction, status: app_commands.Choice[str], ignored_channel: discord.TextChannel = None):
    global MENTION_WARNINGS_ENABLED
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Error: Administrator permission is required to change this setting.", ephemeral=True)
    
    if status.value == "on":
        MENTION_WARNINGS_ENABLED = True
        if ignored_channel:
            IGNORED_WARNING_CHANNELS.add(ignored_channel.id)
            embed = discord.Embed(
                title="⚙️ Mention Protection Enabled",
                description=f"Warnings for mentioning the highest role are now **ON**.\n\n🚫 **Ignored Channel:** Mentions in {ignored_channel.mention} will be **ignored**.",
                color=discord.Colour.green()
            )
        else:
            embed = discord.Embed(
                title="⚙️ Mention Protection Enabled",
                description="Warnings for mentioning the highest role are now **ON** for all channels.",
                color=discord.Colour.green()
            )
    else:
        MENTION_WARNINGS_ENABLED = False
        if ignored_channel and ignored_channel.id in IGNORED_WARNING_CHANNELS:
            IGNORED_WARNING_CHANNELS.remove(ignored_channel.id)
        embed = discord.Embed(
            title="⚙️ Mention Protection Disabled",
            description="Warnings for mentioning the highest role are now **OFF** globally.",
            color=discord.Colour.red()
        )
        
    await interaction.response.send_message(embed=embed)

@auto_purge_group.command(name="messages", description="Auto purge a channel after a period of inactivity")
@app_commands.describe(
    channel="Required: The channel where auto purge will apply",
    time="Required: Inactivity duration before purge, e.g. 1s, 1m, 1h, 1d"
)
async def auto_purge_messages(interaction: discord.Interaction, channel: discord.TextChannel, time: str):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message("Error: Missing permission — Manage Messages", ephemeral=True)

    duration = parse_time(time)
    if not duration:
        return await interaction.response.send_message("Error: Invalid time format. Use formats like 1s, 1m, 1h, 1d", ephemeral=True)

    AUTO_PURGE_SETTINGS[channel.id] = {
        "duration": duration,
        "task": None,
        "label": time,
        "message_count": 0,
        "guild_id": interaction.guild.id
    }

    embed = discord.Embed(title="🧹 Auto Purge Enabled", color=discord.Colour.green())
    embed.add_field(name="Channel", value=channel.mention, inline=False)
    embed.add_field(name="Inactivity Duration", value=f"**{time}**", inline=False)
    embed.add_field(name="Behavior", value="Every new message in this channel resets the timer. Once the channel goes quiet for the set duration, all messages in it are purged.", inline=False)
    embed.add_field(name="Set By", value=interaction.user.mention, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return await bot.process_commands(message)

    # --- AUTO PURGE: count messages and (re)start the inactivity timer once 2+ have been sent ---
    if message.channel.id in AUTO_PURGE_SETTINGS:
        settings = AUTO_PURGE_SETTINGS[message.channel.id]
        settings["message_count"] = settings.get("message_count", 0) + 1
        if settings["message_count"] >= 2:
            existing_task = settings.get("task")
            if existing_task and not existing_task.done():
                existing_task.cancel()
            settings["task"] = asyncio.create_task(schedule_auto_purge(message.channel.id))

    # Check if mention warnings are enabled globally and channel is not ignored
    if MENTION_WARNINGS_ENABLED and message.channel.id not in IGNORED_WARNING_CHANNELS:
        # Get highest role in server
        highest_role = max(message.guild.roles, key=lambda r: r.position)
        
        # Check if highest role is mentioned OR any user with highest role is mentioned
        mentioned_highest = False
        if highest_role in message.role_mentions:
            mentioned_highest = True
        else:
            for user in message.mentions:
                if highest_role in user.roles:
                    mentioned_highest = True
                    break
        
        if mentioned_highest:
            guild_id = message.guild.id
            user_id = message.author.id
            WARNINGS.setdefault(guild_id, {})
            WARNINGS[guild_id].setdefault(user_id, 0)
            WARNINGS[guild_id][user_id] += 1
            count = WARNINGS[guild_id][user_id]
            
            if count == 1:
                embed = discord.Embed(title="⚠️ Warning 1/3", color=discord.Colour.yellow())
                embed.description = f"{message.author.mention}, you have received **Warning 1/3** for mentioning the highest role.\nPlease avoid doing this again."
                await message.channel.send(embed=embed)
            elif count == 2:
                embed = discord.Embed(title="⚠️ Warning 2/3", color=discord.Colour.orange())
                embed.description = f"{message.author.mention}, you have received **Warning 2/3** for mentioning the highest role.\nYou will be timed out after the next warning!"
                await message.channel.send(embed=embed)
            elif count >= 3:
                try:
                    await message.author.timeout(discord.utils.utcnow() + timedelta(seconds=TIMEOUT_DURATION), reason="Mentioned highest role 3 times")
                    embed = discord.Embed(title="⚠️ Warning 3/3 — User Timed Out!", color=discord.Colour.red())
                    embed.description = f"{message.author.mention}, you have received **Warning 3/3** and have been **timed out for 5 minutes** for repeatedly mentioning the highest role.\n\n⚠️ **Your warnings have been reset.**"
                    await message.channel.send(embed=embed)
                    WARNINGS[guild_id][user_id] = 0  # ✅ FULLY RESET TO 0 AFTER TIMEOUT
                except Exception as e:
                    embed = discord.Embed(title="⚠️ Warning 3/3", color=discord.Colour.red())
                    embed.description = f"{message.author.mention}, you have received **Warning 3/3**! Please stop mentioning the highest role.\n\n⚠️ **Your warnings have been reset.**"
                    await message.channel.send(embed=embed)
                    WARNINGS[guild_id][user_id] = 0  # ✅ RESET EVEN IF TIMEOUT FAILS
        
    await bot.process_commands(message)

@bot.command(name='cmds')
async def show_commands(ctx):
    if ctx.author.bot: return
    embed = discord.Embed(title="📋 Bot Commands", color=discord.Colour.blue())
    embed.add_field(name="Prefix Commands", value="""
`.d <link>` - Deobfuscate from URL
`.cmds` - Show this command list
""", inline=False)
    embed.add_field(name="Auto-Features", value="""
**Mention Protection** - Auto-warns & times out users who mention the highest role 3 times
""", inline=False)
    embed.add_field(name="Slash Commands", value="""
`/say message:` - Send a custom message as the bot with mentions
`/warning mention status:[On/Off] [ignored_channel:]` - Toggle mention warnings and exclude specific channels
`/deobf file file:` - Deobfuscate uploaded .lua file
`/auto purge messages channel: time:` - Purge a channel after it goes quiet for a set time (1s/1m/1h/1d)
`/create ticket` - Create a ticket panel
`/create embed` - Create a custom embed
`/ban user:@User` - Ban a user
`/unban user_id:` - Unban a user by ID
`/kick user:@User` - Kick a user
`/mute user:@User` - Mute a user with duration
`/unmute user:@User` - Unmute a user
""", inline=False)
    embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.send(embed=embed)
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command(name='d')
async def deobf_prefix(ctx, *, link: str):
    if ctx.author.bot: return
    status_msg = await ctx.send("Processing...")
    url = extract_url(link)
    if not url:
        if "api.pastes.io" in link:
            return await status_msg.edit(content="Error: api.pastes.io does not exist! Use valid links like https://rentry.co/raw/XXX")
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

@deobf_group.command(name="file", description="Upload a .lua file to deobfuscate")
@app_commands.describe(file="Upload your obfuscated .lua file")
async def deobf_slash(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith('.lua') and not file.filename.endswith('.txt'):
        return await interaction.response.send_message("Error: Please upload a .lua or .txt file", ephemeral=True)
    await interaction.response.defer()
    try:
        content = (await file.read()).decode('utf-8', errors='ignore')
    except Exception as e:
        return await interaction.followup.send(f"Error: Could not read file - {str(e)}", ephemeral=True)
    deobf_code = smart_decode(content)
    filename = f"deobfuscated_{interaction.id}.lua"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(deobf_code)
    await interaction.followup.send(content="Success: File deobfuscated successfully", file=File(filename))
    os.remove(filename)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = TICKET_SETTINGS.get(interaction.channel.id)
        if not settings:
            return await interaction.response.send_message("Error: Could not verify ticket permissions", ephemeral=True)
        staff_role = interaction.guild.get_role(settings["admin_role_id"])
        is_staff = staff_role in interaction.user.roles if staff_role else False
        if not (is_staff or interaction.user.guild_permissions.manage_channels):
            return await interaction.response.send_message("Error: You do not have permission to close this ticket", ephemeral=True)
        await interaction.response.send_message("Closing ticket in 3 seconds...")
        await asyncio.sleep(3)
        await interaction.channel.delete()

@create_group.command(name="ticket", description="Create a ticket panel")
@app_commands.describe(
    admin_role="Required: Role that manages and responds to tickets",
    category="Required: Category where tickets will be created",
    description="Optional: Custom panel description",
    color="Optional: Panel embed color (name or hex, default: green)"
)
async def create_ticket_panel(interaction: discord.Interaction, admin_role: discord.Role, category: discord.CategoryChannel, description: str = "", color: str = "green"):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Error: Administrator permission is required", ephemeral=True)
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
                return await btn_interaction.response.send_message("Error: Panel is not configured properly", ephemeral=True)
            guild = btn_interaction.guild
            ticket_category = guild.get_channel(settings["category_id"])
            staff_role = guild.get_role(settings["admin_role_id"])
            if not ticket_category or not staff_role:
                return await btn_interaction.response.send_message("Error: Category or Admin Role was not found", ephemeral=True)
            
            # --- PREVENT DUPLICATE OPEN TICKETS ---
            for ch_id, ch_data in list(TICKET_SETTINGS.items()):
                if isinstance(ch_data, dict) and ch_data.get("creator_id") == btn_interaction.user.id:
                    existing_channel = guild.get_channel(ch_id)
                    if existing_channel:
                        return await btn_interaction.response.send_message(
                            f"⚠️ You already have an open ticket: {existing_channel.mention}. Please close it before opening a new one.",
                            ephemeral=True
                        )

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
            await btn_interaction.response.send_message(f"Success: Ticket created → {ticket_channel.mention}", ephemeral=True)
    embed = discord.Embed(description=panel_description, color=embed_color)
    await interaction.response.send_message(embed=embed, view=TicketPanel())

@create_group.command(name="embed", description="Create a custom embed")
@app_commands.describe(
    description="Required: The embed description text",
    color="Optional: Embed color (name or hex, default: green)"
)
async def create_embed(interaction: discord.Interaction, description: str, color: str = "green"):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message("Error: Missing permission — Manage Messages", ephemeral=True)
    embed_color = get_color(color)
    embed = discord.Embed(description=description, color=embed_color)
    await interaction.response.send_message(embed=embed)

@tree.command(name="ban", description="Ban a user from the server")
@app_commands.describe(user="Required: User to ban", reason="Optional: Reason for the ban")
async def ban_user(interaction: discord.Interaction, user: discord.Member, reason: str = ""):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("Error: Missing permission — Ban Members", ephemeral=True)
    if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("Error: You cannot ban a user with a higher or equal role", ephemeral=True)
    if user == interaction.user:
        return await interaction.response.send_message("Error: You cannot ban yourself", ephemeral=True)
    ban_reason = reason if reason else "No reason provided"
    await interaction.guild.ban(user, reason=ban_reason)
    embed = discord.Embed(title="🔨 User Banned", color=discord.Colour.red())
    embed.add_field(name="User", value=user.mention, inline=False)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
    embed.add_field(name="Reason", value=ban_reason, inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="unban", description="Unban a user from the server")
@app_commands.describe(user_id="Required: ID of the user to unban")
async def unban_user(interaction: discord.Interaction, user_id: str):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("Error: Missing permission — Ban Members", ephemeral=True)
    try:
        user_id = int(user_id)
        banned_users = [entry async for entry in interaction.guild.bans()]
        for ban_entry in banned_users:
            if ban_entry.user.id == user_id:
                await interaction.guild.unban(ban_entry.user)
                embed = discord.Embed(title="✅ User Unbanned", color=discord.Colour.green())
                embed.add_field(name="User", value=ban_entry.user.mention, inline=False)
                embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
                return await interaction.response.send_message(embed=embed)
        return await interaction.response.send_message("Error: User was not found in the ban list", ephemeral=True)
    except ValueError:
        return await interaction.response.send_message("Error: Invalid User ID", ephemeral=True)

@tree.command(name="kick", description="Kick a user from the server")
@app_commands.describe(user="Required: User to kick", reason="Optional: Reason for the kick")
async def kick_user(interaction: discord.Interaction, user: discord.Member, reason: str = ""):
    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message("Error: Missing permission — Kick Members", ephemeral=True)
    if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("Error: You cannot kick a user with a higher or equal role", ephemeral=True)
    if user == interaction.user:
        return await interaction.response.send_message("Error: You cannot kick yourself", ephemeral=True)
    kick_reason = reason if reason else "No reason provided"
    await interaction.guild.kick(user, reason=kick_reason)
    embed = discord.Embed(title="👢 User Kicked", color=discord.Colour.orange())
    embed.add_field(name="User", value=user.mention, inline=False)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
    embed.add_field(name="Reason", value=kick_reason, inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="mute", description="Mute a user")
@app_commands.describe(
    user="Required: User to mute",
    time="Optional: Enter a duration such as 1m, 1h, 1d, etc.",
    reason="Optional: Reason for the mute"
)
async def mute_user(interaction: discord.Interaction, user: discord.Member, time: str = "", reason: str = ""):
    if not interaction.user.guild_permissions.manage_roles or not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message("Error: Missing permission — Manage Roles or Moderate Members", ephemeral=True)
    if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("Error: You cannot mute a user with a higher or equal role", ephemeral=True)
    if user == interaction.user:
        return await interaction.response.send_message("Error: You cannot mute yourself", ephemeral=True)
    
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
            return await interaction.response.send_message(f"Error: Could not time out user — {str(e)}", ephemeral=True)
    else:
        mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
        if not mute_role:
            mute_role = await interaction.guild.create_role(name="Muted")
            for channel in interaction.guild.channels:
                await channel.set_permissions(mute_role, send_messages=False, speak=False)
        
        if mute_role in user.roles:
            return await interaction.response.send_message("Error: User is already muted", ephemeral=True)
        
        await user.add_roles(mute_role, reason=mute_reason)
        embed = discord.Embed(title="🔇 User Muted", color=discord.Colour.red())
        embed.add_field(name="User", value=user.mention, inline=False)
        embed.add_field(name="Duration", value="**Permanent**", inline=False)
        embed.add_field(name="Reason", value=mute_reason, inline=False)
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
        await interaction.response.send_message(embed=embed)

@tree.command(name="unmute", description="Unmute a user")
@app_commands.describe(user="Required: User to unmute")
async def unmute_user(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.manage_roles or not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message("Error: Missing permission — Manage Roles or Moderate Members", ephemeral=True)
    
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
    print(f"Logged in as {bot.user}")
    try: await tree.sync()
    except Exception as e: print(f"Sync Error: {e}")

keep_alive()
TOKEN = os.getenv('TOKEN')
bot.run(TOKEN)
