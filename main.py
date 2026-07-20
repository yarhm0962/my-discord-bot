from flask import Flask
from threading import Thread
import os
import re
import base64
import aiohttp
import asyncio
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

TICKET_SETTINGS = {}
TICKET_COUNT = {}

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
            return None, "Error: api.pastes.io DOES NOT EXIST! Use links like rentry.co/raw/XXX"
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

@bot.command(name='cmds')
async def show_commands(ctx):
    if ctx.author.bot: return
    commands_list = """
=== PREFIX COMMANDS ===
.d <link or loadstring> - Deobfuscate from URL
.cmds - Show this command list

=== SLASH COMMANDS ===
/deobf-file file: - Deobfuscate uploaded .lua file
/create-ticket admin_role:@Role category:Name description:Text - Create ticket panel
/ban user:@User reason: - Ban a user
/unban user_id:123456789 - Unban a user by ID
/kick user:@User reason: - Kick a user
/mute user:@User reason: - Mute a user
/unmute user:@User - Unmute a user
"""
    await ctx.author.send(commands_list.strip())
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
            return await status_msg.edit(content="Error: api.pastes.io DOES NOT EXIST! Use real links like https://rentry.co/raw/XXX")
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

@tree.command(name="create-ticket", description="Create a ticket panel")
@app_commands.describe(
    admin_role="Required: Role that manages and responds to tickets",
    category="Required: Category where tickets will be created",
    description="Optional: Custom panel description"
)
async def create_ticket_panel(interaction: discord.Interaction, admin_role: discord.Role, category: discord.CategoryChannel, description: str = ""):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Error: Administrator permission required", ephemeral=True)
    panel_description = description if description else "CREATE A TICKET BELOW"
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
                return await btn_interaction.response.send_message("Error: Panel not configured properly", ephemeral=True)
            guild = btn_interaction.guild
            ticket_category = guild.get_channel(settings["category_id"])
            staff_role = guild.get_role(settings["admin_role_id"])
            if not ticket_category or not staff_role:
                return await btn_interaction.response.send_message("Error: Category or Admin Role not found", ephemeral=True)
            TICKET_COUNT[btn_interaction.user.id] = TICKET_COUNT.get(btn_interaction.user.id, 0) + 1
            ticket_number = TICKET_COUNT[btn_interaction.user.id]
            channel_name = f"ticket-{btn_interaction.user.name}-{ticket_number}"
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
            ticket_embed = discord.Embed(title="Ticket Created", color=discord.Colour.green())
            ticket_embed.add_field(name="Created By", value=btn_interaction.user.mention, inline=False)
            ticket_embed.add_field(name="Ticket Number", value=f"#{ticket_number}", inline=False)
            ticket_embed.add_field(name="Staff", value=staff_role.mention, inline=False)
            ticket_embed.add_field(name="Access", value="Only you and staff can see this ticket", inline=False)
            ticket_embed.add_field(name="Actions", value="Click Close Ticket to close this channel", inline=False)
            await ticket_channel.send(embed=ticket_embed, view=CloseTicketView())
            await btn_interaction.response.send_message(f"Success: Ticket created → {ticket_channel.mention}", ephemeral=True)
    embed = discord.Embed(title="Create Ticket", description=panel_description, color=discord.Colour.green())
    embed.add_field(name="Admin Role", value=admin_role.mention, inline=False)
    embed.add_field(name="Ticket Category", value=category.name, inline=False)
    await interaction.response.send_message(embed=embed, view=TicketPanel())

@tree.command(name="ban", description="Ban a user from the server")
@app_commands.describe(user="Required: User to ban", reason="Optional: Reason for the ban")
async def ban_user(interaction: discord.Interaction, user: discord.Member, reason: str = ""):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("Error: Missing permission - Ban Members", ephemeral=True)
    if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("Error: Cannot ban user with higher or equal role", ephemeral=True)
    if user == interaction.user:
        return await interaction.response.send_message("Error: You cannot ban yourself", ephemeral=True)
    ban_reason = reason if reason else "No reason provided"
    await interaction.guild.ban(user, reason=ban_reason)
    await interaction.response.send_message(f"Success: Banned {user.mention} | Reason: {ban_reason}")

@tree.command(name="unban", description="Unban a user from the server")
@app_commands.describe(user_id="Required: ID of the user to unban")
async def unban_user(interaction: discord.Interaction, user_id: str):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("Error: Missing permission - Ban Members", ephemeral=True)
    try:
        user_id = int(user_id)
        banned_users = [entry async for entry in interaction.guild.bans()]
        for ban_entry in banned_users:
            if ban_entry.user.id == user_id:
                await interaction.guild.unban(ban_entry.user)
                return await interaction.response.send_message(f"Success: Unbanned {ban_entry.user.mention}")
        return await interaction.response.send_message("Error: User not found in ban list", ephemeral=True)
    except ValueError:
        return await interaction.response.send_message("Error: Invalid User ID", ephemeral=True)

@tree.command(name="kick", description="Kick a user from the server")
@app_commands.describe(user="Required: User to kick", reason="Optional: Reason for the kick")
async def kick_user(interaction: discord.Interaction, user: discord.Member, reason: str = ""):
    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message("Error: Missing permission - Kick Members", ephemeral=True)
    if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("Error: Cannot kick user with higher or equal role", ephemeral=True)
    if user == interaction.user:
        return await interaction.response.send_message("Error: You cannot kick yourself", ephemeral=True)
    kick_reason = reason if reason else "No reason provided"
    await interaction.guild.kick(user, reason=kick_reason)
    await interaction.response.send_message(f"Success: Kicked {user.mention} | Reason: {kick_reason}")

@tree.command(name="mute", description="Mute a user")
@app_commands.describe(user="Required: User to mute", reason="Optional: Reason for the mute")
async def mute_user(interaction: discord.Interaction, user: discord.Member, reason: str = ""):
    if not interaction.user.guild_permissions.manage_roles:
        return await interaction.response.send_message("Error: Missing permission - Manage Roles", ephemeral=True)
    if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("Error: Cannot mute user with higher or equal role", ephemeral=True)
    if user == interaction.user:
        return await interaction.response.send_message("Error: You cannot mute yourself", ephemeral=True)
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role:
        mute_role = await interaction.guild.create_role(name="Muted")
        for channel in interaction.guild.channels:
            await channel.set_permissions(mute_role, send_messages=False, speak=False)
    if mute_role in user.roles:
        return await interaction.response.send_message("Error: User is already muted", ephemeral=True)
    mute_reason = reason if reason else "No reason provided"
    await user.add_roles(mute_role, reason=mute_reason)
    await interaction.response.send_message(f"Success: Muted {user.mention} | Reason: {mute_reason}")

@tree.command(name="unmute", description="Unmute a user")
@app_commands.describe(user="Required: User to unmute")
async def unmute_user(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.manage_roles:
        return await interaction.response.send_message("Error: Missing permission - Manage Roles", ephemeral=True)
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role or mute_role not in user.roles:
        return await interaction.response.send_message("Error: User is not muted", ephemeral=True)
    await user.remove_roles(mute_role)
    await interaction.response.send_message(f"Success: Unmuted {user.mention}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try: await tree.sync()
    except Exception as e: print(f"Sync Error: {e}")

keep_alive()
TOKEN = os.getenv('TOKEN')
bot.run(TOKEN)
