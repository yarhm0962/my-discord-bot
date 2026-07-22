from flask import Flask
from threading import Thread
import os
import re
import base64
import aiohttp
import asyncio
import discord
import random
import json
import subprocess
from datetime import timedelta
from discord import app_commands
from discord.ext import commands

app = Flask('')

@app.route('/')
def home():
    return "Bot is running"

def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, threaded=False, use_reloader=False)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)
tree = bot.tree

create_group = app_commands.Group(name="create", description="Commands for creation")
warning_group = app_commands.Group(name="warning", description="Warning system commands")
deobf_group = app_commands.Group(name="deobf", description="Deobfuscation commands")
auto_group = app_commands.Group(name="auto", description="Automation commands")
auto_purge_group = app_commands.Group(name="purge", description="Auto purge commands", parent=auto_group)
add_group = app_commands.Group(name="add", description="Add server features")
instant_group = app_commands.Group(name="instant", description="Instant permission commands")

tree.add_command(create_group)
tree.add_command(warning_group)
tree.add_command(deobf_group)
tree.add_command(auto_group)
tree.add_command(add_group)
tree.add_command(instant_group)

TICKET_SETTINGS = {}
AUTO_PURGE_SETTINGS = {}
TIMEOUT_DURATION = 300
MENTION_WARNINGS_ENABLED = True
IGNORED_WARNING_CHANNELS = set()
IGNORED_WARNING_ROLES = set()
PROTECTED_ROLES = set()
VERIFIED_ROLE_CACHE = {}

# Persistent warnings storage
WARNINGS_FILE = "warnings.json"

def load_warnings():
    try:
        if os.path.exists(WARNINGS_FILE):
            with open(WARNINGS_FILE, 'r') as f:
                data = json.load(f)
                return {int(g): {int(u): c for u, c in users.items()} for g, users in data.items()}
    except Exception as e:
        print(f"Error loading warnings: {e}")
    return {}

def save_warnings(warnings):
    try:
        data = {str(g): {str(u): c for u, c in users.items()} for g, users in warnings.items()}
        with open(WARNINGS_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error saving warnings: {e}")

WARNINGS = load_warnings()

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
    settings = AUTO_PURGE_SETTINGS.get(channel_id)
    if not settings:
        return
    try:
        await asyncio.sleep(settings["duration"])
    except asyncio.CancelledError:
        return
    if AUTO_PURGE_SETTINGS.get(channel_id) is not settings:
        return
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    try:
        deleted = await channel.purge(limit=None)
        purged_count = len(deleted)
    except Exception:
        purged_count = 0
    settings["message_count"] = 0
    settings["task"] = None
    embed = discord.Embed(
        title="🧹 Auto Purge Completed",
        description=f"All messages is clean 🧹\n**{purged_count}** message(s) purged from {channel.mention} after **{settings['label']}** of inactivity.",
        color=discord.Colour.green()
    )
    embed.set_footer(text="Auto Purge")
    embed.timestamp = discord.utils.utcnow()
    try:
        await channel.send(embed=embed)
    except Exception:
        pass

def deobfuscate_lua_code(content):
    match = re.search(r'local ([a-zA-Z0-9_]+)=\{"', content)
    if not match:
        return None, "String table not found"
    var_name = match.group(1)

    mock_env = """
local real_type = type
local real_concat = table.concat
local MockEnv = {}
local function create_dummy(name)
    local d = {}
    setmetatable(d, {
        __index = function(_,k)
            print("[ACCESSED] "..name.."."..k)
            return create_dummy(name.."."..k)
        end,
        __call = function(_,...)
            return create_dummy(name.."_res")
        end
    })
    return d
end
local safe = {
    string = string,
    table = {concat = table.concat, insert = table.insert, remove = table.remove},
    math = math,
    pairs = pairs,
    ipairs = ipairs,
    tonumber = tonumber,
    tostring = tostring,
    type = type,
    pcall = pcall,
    setmetatable = setmetatable,
    getmetatable = getmetatable,
    next = next
}
safe.loadstring = function(s)
    print("--- DEOBFUSCATED CODE ---")
    print(s)
    print("--- END ---")
    return function() end
end
setmetatable(MockEnv, {
    __index = function(_,k)
        if safe[k] then return safe[k] end
        if k == "game" or k == "workspace" or k == "script" then
            return create_dummy(k)
        end
        return nil
    end
})
"""

    idx_ret = content.rfind("return(function")
    if idx_ret == -1:
        return None, "Injection point not found"

    dumper = f"""
print("--- STRING TABLE ---")
if {var_name} then
    for k,v in pairs({var_name}) do
        print("["..k.."] = "..string.format("%q", v))
    end
end
"""

    new_script = mock_env + content[:idx_ret] + dumper + content[idx_ret:]
    new_script = re.sub(r'getfenv\s+and\s+getfenv\(\)\s+or\s+_ENV', 'MockEnv', new_script)
    return new_script, None

@bot.event
async def on_member_join(member):
    if member.bot:
        return
    if member.guild.id not in VERIFIED_ROLE_CACHE:
        return
    verified_role = VERIFIED_ROLE_CACHE[member.guild.id]
    not_verified_role = discord.utils.get(member.guild.roles, name="Not Verified")
    if not not_verified_role or verified_role in member.roles:
        return
    try:
        await member.add_roles(not_verified_role, reason="Auto-assigned 'Not Verified' role on join")
    except:
        pass

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id", "")
        if custom_id.startswith("verify_btn_"):
            try:
                role_id = int(custom_id.split("_")[2])
                verified_role = interaction.guild.get_role(role_id)
                not_verified_role = discord.utils.get(interaction.guild.roles, name="Not Verified")
                if not verified_role:
                    return await interaction.response.send_message("❌ Error: The verified role no longer exists.", ephemeral=True)
                await interaction.user.add_roles(verified_role)
                if not_verified_role and not_verified_role in interaction.user.roles:
                    await interaction.user.remove_roles(not_verified_role)
                await interaction.response.send_message("✅ You have been successfully verified!", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Error: I don't have permission to manage roles. Please ask an admin to move my bot role higher.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)

        elif custom_id.startswith("give_perms_"):
            try:
                parts = custom_id.split("_")
                category_id = int(parts[2])
                admin_role_id = int(parts[3])
                channel_id = int(parts[4]) if len(parts) > 4 else None
                category = interaction.guild.get_channel(category_id)
                admin_role = interaction.guild.get_role(admin_role_id)
                target_channel = interaction.guild.get_channel(channel_id) if channel_id else interaction.channel
                if not category or not admin_role or not target_channel:
                    return await interaction.response.send_message("❌ Error: Required resources not found.", ephemeral=True)
                if not interaction.user.guild_permissions.administrator:
                    return await interaction.response.send_message("❌ Error: You need Administrator permission to grant permissions.", ephemeral=True)
                bot_member = interaction.guild.get_member(bot.user.id)
                try:
                    await target_channel.set_permissions(
                        bot_member,
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        manage_messages=True,
                        embed_links=True
                    )
                except:
                    pass
                try:
                    await category.set_permissions(
                        bot_member,
                        view_channel=True,
                        send_messages=True,
                        manage_channels=True,
                        read_message_history=True,
                        create_instant_invite=True
                    )
                    await category.set_permissions(
                        admin_role,
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        create_instant_invite=True
                    )
                except:
                    pass
                # Check if permissions were granted
                channel_perms = target_channel.permissions_for(bot_member)
                category_perms = category.permissions_for(bot_member)
                if not (channel_perms.view_channel and channel_perms.send_messages and channel_perms.read_message_history and channel_perms.manage_messages and channel_perms.embed_links) or not (category_perms.view_channel and category_perms.send_messages and category_perms.manage_channels and category_perms.read_message_history and category_perms.create_instant_invite):
                    embed = discord.Embed(
                        title="⚠️ Partial Permissions Granted",
                        description="I was unable to grant all the necessary permissions automatically.",
                        color=discord.Colour.orange()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=True)
                panel_description = "**CREATE A TICKET BELOW 🎟️**"
                embed_color = discord.Colour.green()
                TICKET_SETTINGS[target_channel.id] = {
                    "admin_role_id": admin_role_id,
                    "category_id": category_id,
                    "guild_id": interaction.guild.id,
                    "enable_claim_button": True,
                    "panel_channel_id": target_channel.id
                }
                panel_view = discord.ui.View(timeout=None)
                create_btn = discord.ui.Button(
                    label="Create Ticket",
                    emoji="🎟️",
                    style=discord.ButtonStyle.success,
                    custom_id="create_ticket_btn"
                )
                panel_view.add_item(create_btn)
                embed = discord.Embed(description=panel_description, color=embed_color)
                embed.set_footer(text="Ticket System")
                await target_channel.send(embed=embed, view=panel_view)
                await interaction.followup.send(f"✅ **Permissions Granted!** Ticket panel has been created in {target_channel.mention}.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)

        elif custom_id == "create_ticket_btn":
            try:
                settings = TICKET_SETTINGS.get(interaction.channel.id)
                if not settings:
                    return await interaction.response.send_message("❌ Error: Ticket panel is not configured properly. Please contact an admin.", ephemeral=True)
                guild = interaction.guild
                ticket_category = guild.get_channel(settings["category_id"])
                staff_role = guild.get_role(settings["admin_role_id"])
                if not ticket_category or not staff_role:
                    return await interaction.response.send_message("❌ Error: Category or staff role not found.", ephemeral=True)
                for ch_id, ch_data in list(TICKET_SETTINGS.items()):
                    if isinstance(ch_data, dict) and ch_data.get("creator_id") == interaction.user.id:
                        existing_channel = guild.get_channel(ch_id)
                        if existing_channel:
                            return await interaction.response.send_message(f"⚠️ You already have an open ticket: {existing_channel.mention}. Please close it before opening a new one.", ephemeral=True)
                bot_member = guild.get_member(bot.user.id)
                category_perms = ticket_category.permissions_for(bot_member)
                if not category_perms.view_channel or not category_perms.send_messages or not category_perms.manage_channels:
                    return await interaction.response.send_message("❌ Error: I don't have the necessary permissions in the category to create tickets.", ephemeral=True)
                channel_name = f"{interaction.user.name}-ticket"
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                    staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
                }
                ticket_channel = await ticket_category.create_text_channel(name=channel_name, overwrites=overwrites, reason=f"Ticket created by {interaction.user}")
                TICKET_SETTINGS[ticket_channel.id] = {
                    "admin_role_id": settings["admin_role_id"],
                    "creator_id": interaction.user.id,
                    "category_id": settings["category_id"],
                    "enable_claim_button": settings.get("enable_claim_button", True)
                }
                ticket_embed = discord.Embed(
                    title="🎫 Ticket Created",
                    description="**Please wait for a staff member to assist you**",
                    color=discord.Colour.green()
                )
                ticket_embed.add_field(name="Created By", value=interaction.user.mention, inline=False)
                ticket_embed.set_footer(text="Ticket System")
                ticket_embed.timestamp = discord.utils.utcnow()
                view = discord.ui.View(timeout=None)
                close_btn = discord.ui.Button(
                    label="Close Ticket",
                    emoji="🔒",
                    style=discord.ButtonStyle.danger,
                    custom_id="close_ticket_btn"
                )
                close_btn.callback = close_ticket_callback
                view.add_item(close_btn)
                if settings.get("enable_claim_button", True):
                    claim_btn = discord.ui.Button(
                        label="Claim Ticket",
                        emoji="🎫",
                        style=discord.ButtonStyle.primary,
                        custom_id="claim_ticket_btn"
                    )
                    async def claim_callback(claim_interaction):
                        try:
                            claim_settings = TICKET_SETTINGS.get(claim_interaction.channel.id)
                            if not claim_settings:
                                return await claim_interaction.response.send_message("❌ Error: This ticket is not configured properly.", ephemeral=True)
                            claim_staff_role = claim_interaction.guild.get_role(claim_settings["admin_role_id"])
                            is_staff = claim_staff_role in claim_interaction.user.roles if claim_staff_role else False
                            if not (is_staff or claim_interaction.user.guild_permissions.administrator):
                                return await claim_interaction.response.send_message("❌ Error: Only an admin/staff member can claim this ticket.", ephemeral=True)
                            if claim_btn.disabled:
                                return await claim_interaction.response.send_message("❌ Error: This ticket has already been claimed.", ephemeral=True)
                            creator_id = claim_settings.get("creator_id")
                            creator_mention = f"<@{creator_id}>" if creator_id else ""
                            claim_embed = discord.Embed(
                                title="🎫 Ticket Claimed",
                                description=f"{claim_interaction.user.mention} has claimed this ticket and will be assisting you shortly!",
                                color=discord.Colour.yellow()
                            )
                            claim_btn.disabled = True
                            claim_btn.label = f"Claimed by {claim_interaction.user.display_name}"
                            await claim_interaction.response.edit_message(view=claim_btn.view)
                            await claim_interaction.channel.send(content=creator_mention, embed=claim_embed)
                        except Exception as e:
                            await claim_interaction.response.send_message(f"❌ Error claiming ticket: {str(e)}", ephemeral=True)
                    claim_btn.callback = claim_callback
                    view.add_item(claim_btn)
                await ticket_channel.send(embed=ticket_embed, view=view)
                await ticket_channel.send(f"{staff_role.mention} A new ticket has been created!")
                await interaction.response.send_message(f"✅ Ticket created successfully! → {ticket_channel.mention}", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ An error occurred while creating the ticket: {str(e)}", ephemeral=True)

@instant_group.command(name="permissions", description="Instantly disable message sending permissions for @everyone in ALL channels")
async def instant_permissions(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Error: Administrator permission is required to use this command.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    everyone_role = interaction.guild.default_role
    updated_channels = 0
    failed_channels = []
    for channel in interaction.guild.channels:
        try:
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.ForumChannel, discord.Thread)):
                await channel.set_permissions(
                    everyone_role,
                    send_messages=False,
                    send_messages_in_threads=False,
                    create_public_threads=False,
                    create_private_threads=False
                )
                updated_channels += 1
                await asyncio.sleep(0.5)
        except Exception as e:
            failed_channels.append(f"{channel.name} ({str(e)})")
    embed = discord.Embed(
        title="⚡ Instant Permissions Applied",
        description=f"Successfully disabled messaging permissions for **@everyone** in **{updated_channels}** channels.",
        color=discord.Colour.red()
    )
    embed.add_field(
        name="Permissions Disabled",
        value="❌ Send Messages\n❌ Send Messages in Threads\n❌ Create Public Threads\n❌ Create Private Threads",
        inline=False
    )
    embed.add_field(
        name="Affected Channels",
        value=f"✅ {updated_channels} channels updated",
        inline=False
    )
    embed.set_footer(text=f"Action by {interaction.user.display_name}")
    embed.timestamp = discord.utils.utcnow()
    if failed_channels:
        embed.add_field(
            name="⚠️ Failed Channels",
            value=f"Failed to update {len(failed_channels)} channels. They may be categories or the bot may lack permissions.",
            inline=False
        )
    await interaction.followup.send(embed=embed)

@add_group.command(name="verify", description="Set up a verification system and auto-role unverified members")
@app_commands.describe(
    role="Required: The role to give users when they verify",
    enabled_channel="Required: The channel where the verification embed will be sent"
)
@app_commands.rename(enabled_channel="enabled-channel")
async def add_verify(interaction: discord.Interaction, role: discord.Role, enabled_channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Error: Administrator permission is required.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    VERIFIED_ROLE_CACHE[interaction.guild.id] = role

    not_verified_role = discord.utils.get(interaction.guild.roles, name="Not Verified")
    if not not_verified_role:
        try:
            not_verified_role = await interaction.guild.create_role(
                name="Not Verified", 
                color=discord.Colour.dark_grey(), 
                reason="Auto-created for verification system"
            )
        except discord.Forbidden:
            return await interaction.followup.send("❌ Error: I lack permission to manage roles. Please check my role hierarchy.")
        except Exception as e:
            return await interaction.followup.send(f"❌ Error creating 'Not Verified' role: {str(e)}")

    try:
        await enabled_channel.set_permissions(
            interaction.guild.default_role,
            send_messages=False,
            send_messages_in_threads=False,
            create_public_threads=False,
            create_private_threads=False
        )
    except Exception:
        pass

    semaphore = asyncio.Semaphore(5)
    async def update_channel_permissions(ch):
        async with semaphore:
            try:
                if ch.id == enabled_channel.id:
                    if isinstance(ch, discord.TextChannel):
                        await ch.set_permissions(
                            not_verified_role, 
                            view_channel=True, 
                            read_message_history=True, 
                            send_messages=False,
                            send_messages_in_threads=False,
                            create_public_threads=False,
                            create_private_threads=False
                        )
                    else:
                        await ch.set_permissions(
                            not_verified_role,
                            view_channel=True,
                            read_message_history=True,
                            send_messages=False
                        )
                else:
                    await ch.set_permissions(not_verified_role, view_channel=False)
                await asyncio.sleep(0.3)
            except Exception:
                pass
    tasks = [update_channel_permissions(ch) for ch in interaction.guild.channels]
    await asyncio.gather(*tasks)

    assigned_count = 0
    failed_members = []
    members_to_update = []
    for member in interaction.guild.members:
        if not member.bot and role not in member.roles and not_verified_role not in member.roles:
            members_to_update.append(member)
    batch_size = 5
    for i in range(0, len(members_to_update), batch_size):
        batch = members_to_update[i:i + batch_size]
        tasks = []
        for member in batch:
            task = member.add_roles(not_verified_role, reason="Auto-assigned 'Not Verified' role")
            tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                failed_members.append(str(result))
            else:
                assigned_count += 1
        if i + batch_size < len(members_to_update):
            await asyncio.sleep(1.0)

    embed = discord.Embed(
        title="🔐 Server Verification",
        description=(
            "Welcome to the server! We are glad to have you here.\n\n"
            "To gain access to all the channels and features, please verify yourself by clicking the **Verify** button below.\n"
            "This helps us keep the server safe and secure."
        ),
        color=discord.Colour.green()
    )
    embed.set_footer(text="Verification System")
    view = discord.ui.View(timeout=None)
    btn = discord.ui.Button(
        label="Click to Verify",
        emoji="👥",
        style=discord.ButtonStyle.success,
        custom_id=f"verify_btn_{role.id}"
    )
    view.add_item(btn)
    await enabled_channel.send(embed=embed, view=view)
    success_message = f"✅ Verification panel setup complete in {enabled_channel.mention}!\n"
    success_message += f"Gave the 'Not Verified' role to **{assigned_count}** members.\n"
    if failed_members:
        success_message += f"⚠️ Failed to assign role to {len(failed_members)} members.\n"
    success_message += f"*(Channel is now locked to Read-Only and other channels are hidden from unverified users).*\n\n"
    success_message += f"🔄 **New members will automatically receive the 'Not Verified' role upon joining!**"
    await interaction.followup.send(success_message)

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
    ignored_channel="Optional: Select a channel where mention warnings will be ignored",
    ignored_role="Optional: Select a role that will bypass mention warnings",
    protected_role="Optional: Add/remove a role that triggers warnings when mentioned"
)
@app_commands.rename(ignored_channel="ignored-channel", ignored_role="ignore-role", protected_role="protected-role")
@app_commands.choices(status=[
    app_commands.Choice(name="On", value="on"),
    app_commands.Choice(name="Off", value="off")
])
async def warning_mention_toggle(interaction: discord.Interaction, status: app_commands.Choice[str], ignored_channel: discord.TextChannel = None, ignored_role: discord.Role = None, protected_role: discord.Role = None):
    global MENTION_WARNINGS_ENABLED
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Error: Administrator permission is required to change this setting.", ephemeral=True)
    channel_msg = ""
    if ignored_channel:
        if ignored_channel.id in IGNORED_WARNING_CHANNELS:
            IGNORED_WARNING_CHANNELS.remove(ignored_channel.id)
            channel_msg = f"\n\n✅ **Removed Channel:** Mentions in {ignored_channel.mention} will now trigger warnings."
        else:
            IGNORED_WARNING_CHANNELS.add(ignored_channel.id)
            channel_msg = f"\n\n🚫 **Ignored Channel:** Mentions in {ignored_channel.mention} will be ignored."
    role_msg = ""
    if ignored_role:
        if ignored_role.id in IGNORED_WARNING_ROLES:
            IGNORED_WARNING_ROLES.remove(ignored_role.id)
            role_msg = f"\n\n✅ **Removed Role:** Members with the {ignored_role.mention} role will now receive warnings."
        else:
            IGNORED_WARNING_ROLES.add(ignored_role.id)
            role_msg = f"\n\n🚫 **Ignored Role:** Members with the {ignored_role.mention} role will bypass warnings."
    protected_msg = ""
    if protected_role:
        if protected_role.id in PROTECTED_ROLES:
            PROTECTED_ROLES.remove(protected_role.id)
            protected_msg = f"\n\n✅ **Removed Protected Role:** {protected_role.mention} will no longer trigger warnings when mentioned."
        else:
            PROTECTED_ROLES.add(protected_role.id)
            protected_msg = f"\n\n🛡️ **Added Protected Role:** {protected_role.mention} will now trigger warnings when mentioned."
    if status.value == "on":
        MENTION_WARNINGS_ENABLED = True
        embed = discord.Embed(
            title="⚙️ Mention Protection Enabled",
            description=f"Warnings for mentioning the highest role are now **ON**.{channel_msg}{role_msg}{protected_msg}",
            color=discord.Colour.green()
        )
    else:
        MENTION_WARNINGS_ENABLED = False
        embed = discord.Embed(
            title="⚙️ Mention Protection Disabled",
            description=f"Warnings for mentioning the highest role are now **OFF** globally.{channel_msg}{role_msg}{protected_msg}",
            color=discord.Colour.red()
        )
    if PROTECTED_ROLES:
        role_list = []
        for role_id in PROTECTED_ROLES:
            role = interaction.guild.get_role(role_id)
            if role:
                role_list.append(f"• {role.mention}")
        if role_list:
            embed.add_field(
                name="🛡️ Current Protected Roles",
                value="\n".join(role_list),
                inline=False
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

@create_group.command(name="ticket", description="Create a ticket panel")
@app_commands.describe(
    admin_role="Required: Role that manages and responds to tickets",
    category="Required: Category where tickets will be created",
    select_channel="Required: Select a specific channel where the ticket panel will be sent",
    enable_claim_button="Required: Toggle the Claim Ticket button inside tickets (On/Off)",
    description="Optional: Custom panel description",
    title="Optional: Panel embed title",
    footer="Optional: Panel embed footer text",
    image="Optional: A large image to display on the panel embed",
    color="Optional: Panel embed color (name or hex, default: green)",
    button_label="Optional: Text for the ticket creation button (default: Create Ticket)",
    button_emoji="Optional: Emoji for the ticket creation button (default: 🎟️)"
)
@app_commands.rename(
    admin_role="admin-role",
    select_channel="select-channel",
    enable_claim_button="enable-claim-button",
    button_label="button-label",
    button_emoji="button-emoji"
)
async def create_ticket_panel(interaction: discord.Interaction, admin_role: discord.Role, category: discord.CategoryChannel, select_channel: discord.TextChannel, enable_claim_button: bool = True, description: str = "", title: str = "", footer: str = "", image: discord.Attachment = None, color: str = "green", button_label: str = "Create Ticket", button_emoji: str = "🎟️"):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Error: Administrator permission is required", ephemeral=True)
    if not category:
        return await interaction.response.send_message("❌ Error: The specified category does not exist.", ephemeral=True)
    if not admin_role:
        return await interaction.response.send_message("❌ Error: The specified admin role does not exist.", ephemeral=True)
    if not select_channel:
        return await interaction.response.send_message("❌ Error: The specified channel does not exist.", ephemeral=True)
    target_channel = select_channel
    bot_member = interaction.guild.get_member(bot.user.id)
    channel_perms = target_channel.permissions_for(bot_member)
    channel_missing_perms = []
    if not channel_perms.view_channel:
        channel_missing_perms.append("View Channel")
    if not channel_perms.send_messages:
        channel_missing_perms.append("Send Messages")
    if not channel_perms.read_message_history:
        channel_missing_perms.append("Read Message History")
    if not channel_perms.manage_messages:
        channel_missing_perms.append("Manage Messages")
    if not channel_perms.embed_links:
        channel_missing_perms.append("Embed Links")
    category_perms = category.permissions_for(bot_member)
    category_missing_perms = []
    if not category_perms.view_channel:
        category_missing_perms.append("View Channel")
    if not category_perms.send_messages:
        category_missing_perms.append("Send Messages")
    if not category_perms.manage_channels:
        category_missing_perms.append("Manage Channels")
    if not category_perms.read_message_history:
        category_missing_perms.append("Read Message History")
    if not category_perms.create_instant_invite:
        category_missing_perms.append("Create Instant Invite")
    all_missing = []
    if channel_missing_perms:
        all_missing.append(f"**In {target_channel.mention}:**\n• " + "\n• ".join(channel_missing_perms))
    if category_missing_perms:
        all_missing.append(f"**In {category.name} category:**\n• " + "\n• ".join(category_missing_perms))
    if all_missing:
        embed = discord.Embed(
            title="❌ Permission Error",
            description="I don't have all the necessary permissions to create tickets.",
            color=discord.Colour.red()
        )
        embed.add_field(
            name="📌 Missing Permissions",
            value="\n\n".join(all_missing),
            inline=False
        )
        embed.add_field(
            name="💡 Click the button below to auto-fix these issues",
            value="This will grant me the needed permissions in both the channel and category.",
            inline=False
        )
        view = discord.ui.View(timeout=None)
        give_perms_btn = discord.ui.Button(
            label="Give Permissions",
            emoji="🔑",
            style=discord.ButtonStyle.success,
            custom_id=f"give_perms_{category.id}_{admin_role.id}_{target_channel.id}"
        )
        view.add_item(give_perms_btn)
        cancel_btn = discord.ui.Button(
            label="Cancel",
            emoji="❌",
            style=discord.ButtonStyle.secondary,
            custom_id="cancel_ticket_setup"
        )
        async def cancel_callback(cancel_interaction):
            await cancel_interaction.response.send_message("❌ Ticket setup cancelled.", ephemeral=True)
        cancel_btn.callback = cancel_callback
        view.add_item(cancel_btn)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        return
    panel_description = description if description else "**CREATE A TICKET BELOW 🎟️**"
    embed_color = get_color(color)
    TICKET_SETTINGS[target_channel.id] = {
        "admin_role_id": admin_role.id,
        "category_id": category.id,
        "guild_id": interaction.guild.id,
        "enable_claim_button": enable_claim_button,
        "panel_channel_id": target_channel.id
    }
    panel_view = discord.ui.View(timeout=None)
    create_btn = discord.ui.Button(
        label=button_label,
        emoji=button_emoji,
        style=discord.ButtonStyle.success,
        custom_id="create_ticket_btn"
    )
    panel_view.add_item(create_btn)
    embed = discord.Embed(description=panel_description, color=embed_color)
    if title:
        embed.title = title
    if footer:
        embed.set_footer(text=footer)
    if image:
        embed.set_image(url=image.url)
    await target_channel.send(embed=embed, view=panel_view)
    await interaction.response.send_message(
        f"✅ Ticket panel created successfully in {target_channel.mention}!",
        ephemeral=True
    )

@deobf_group.command(name="file", description="Deobfuscate a Lua script from a file")
@app_commands.describe(
    file="Upload the obfuscated .lua file to deobfuscate"
)
async def deobf_file(interaction: discord.Interaction, file: discord.Attachment):
    await interaction.response.defer()
    if not file.filename.endswith('.lua') and not file.filename.endswith('.txt'):
        return await interaction.followup.send("❌ Error: Please upload a .lua or .txt file")
    try:
        content = (await file.read()).decode('utf-8', errors='ignore')
        if not content or len(content.strip()) == 0:
            return await interaction.followup.send("❌ Error: The file is empty")
        new_script, error = deobfuscate_lua_code(content)
        if error:
            return await interaction.followup.send(f"❌ Deobfuscation failed: {error}")
        timestamp = discord.utils.utcnow().strftime("%Y%m%d_%H%M%S")
        output_filename = f"deobfuscated_{timestamp}.lua"
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(new_script)
        await interaction.followup.send(
            "✅ **Deobfuscated successfully!**",
            file=discord.File(output_filename)
        )
        os.remove(output_filename)
    except Exception as e:
        await interaction.followup.send(f"❌ Error during deobfuscation: {str(e)}")

@deobf_group.command(name="code", description="Deobfuscate a Lua script from pasted code")
@app_commands.describe(
    code="Paste the obfuscated Lua code here"
)
async def deobf_code(interaction: discord.Interaction, code: str):
    await interaction.response.defer()
    if not code or len(code.strip()) == 0:
        return await interaction.followup.send("❌ Error: Please paste some Lua code to deobfuscate")
    try:
        new_script, error = deobfuscate_lua_code(code)
        if error:
            return await interaction.followup.send(f"❌ Deobfuscation failed: {error}")
        if len(new_script) > 1900:
            timestamp = discord.utils.utcnow().strftime("%Y%m%d_%H%M%S")
            output_filename = f"deobfuscated_{timestamp}.lua"
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(new_script)
            await interaction.followup.send(
                "✅ **Deobfuscated successfully!**",
                file=discord.File(output_filename)
            )
            os.remove(output_filename)
        else:
            await interaction.followup.send(f"✅ **Deobfuscated successfully!**\n```lua\n{new_script}\n```")
    except Exception as e:
        await interaction.followup.send(f"❌ Error during deobfuscation: {str(e)}")

async def close_ticket_callback(interaction: discord.Interaction):
    try:
        settings = TICKET_SETTINGS.get(interaction.channel.id)
        if not settings:
            return await interaction.response.send_message("❌ Error: This ticket channel is not configured properly.", ephemeral=True)
        staff_role = interaction.guild.get_role(settings["admin_role_id"])
        is_staff = staff_role in interaction.user.roles if staff_role else False
        if not (is_staff or interaction.user.guild_permissions.manage_channels):
            return await interaction.response.send_message("❌ Error: You do not have permission to close this ticket.", ephemeral=True)
        await interaction.response.send_message("🔒 Closing ticket in 3 seconds...")
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete()
        except discord.Forbidden:
            await interaction.followup.send("❌ Error: I don't have permission to delete this channel.")
        except Exception as e:
            await interaction.followup.send(f"❌ Error deleting channel: {str(e)}")
    except Exception as e:
        print(f"Close ticket error: {e}")
        await interaction.response.send_message(
            f"❌ An error occurred while closing the ticket: {str(e)}",
            ephemeral=True
        )

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)
    if not message.guild:
        return
    if message.channel.id in AUTO_PURGE_SETTINGS:
        settings = AUTO_PURGE_SETTINGS[message.channel.id]
        settings["message_count"] = settings.get("message_count", 0) + 1
        if settings["message_count"] >= 2:
            existing_task = settings.get("task")
            if existing_task and not existing_task.done():
                existing_task.cancel()
            settings["task"] = asyncio.create_task(schedule_auto_purge(message.channel.id))
    if PROTECTED_ROLES and message.channel.id not in IGNORED_WARNING_CHANNELS:
        has_ignored_role = any(role.id in IGNORED_WARNING_ROLES for role in message.author.roles)
        if not has_ignored_role:
            mentioned_protected = False
            for role_mention in message.role_mentions:
                if role_mention.id in PROTECTED_ROLES:
                    mentioned_protected = True
                    break
            if not mentioned_protected:
                for user in message.mentions:
                    for role in user.roles:
                        if role.id in PROTECTED_ROLES:
                            mentioned_protected = True
                            break
                    if mentioned_protected:
                        break
            if mentioned_protected:
                guild_id = message.guild.id
                user_id = message.author.id
                if guild_id not in WARNINGS:
                    WARNINGS[guild_id] = {}
                if user_id not in WARNINGS[guild_id]:
                    WARNINGS[guild_id][user_id] = 0
                WARNINGS[guild_id][user_id] += 1
                count = WARNINGS[guild_id][user_id]
                save_warnings(WARNINGS)
                if count == 1:
                    embed = discord.Embed(title="⚠️ Warning 1/3", color=discord.Colour.yellow())
                    embed.description = f"{message.author.mention}, you have received **Warning 1/3** for mentioning a protected role.\nPlease avoid doing this again."
                    await message.channel.send(embed=embed)
                elif count == 2:
                    embed = discord.Embed(title="⚠️ Warning 2/3", color=discord.Colour.orange())
                    embed.description = f"{message.author.mention}, you have received **Warning 2/3** for mentioning a protected role.\nYou will be timed out after the next warning!"
                    await message.channel.send(embed=embed)
                elif count >= 3:
                    try:
                        await message.author.timeout(discord.utils.utcnow() + timedelta(seconds=TIMEOUT_DURATION), reason="Mentioned protected role 3 times")
                        embed = discord.Embed(title="⚠️ Warning 3/3 — User Timed Out!", color=discord.Colour.red())
                        embed.description = f"{message.author.mention}, you have received **Warning 3/3** and have been **timed out for 5 minutes** for repeatedly mentioning a protected role.\n\n⚠️ **Your warnings have been reset.**"
                        await message.channel.send(embed=embed)
                        WARNINGS[guild_id][user_id] = 0
                        save_warnings(WARNINGS)
                    except Exception as e:
                        embed = discord.Embed(title="⚠️ Warning 3/3", color=discord.Colour.red())
                        embed.description = f"{message.author.mention}, you have received **Warning 3/3**! Please stop mentioning protected roles.\n\n⚠️ **Your warnings have been reset.**"
                        await message.channel.send(embed=embed)
                        WARNINGS[guild_id][user_id] = 0
                        save_warnings(WARNINGS)
    if MENTION_WARNINGS_ENABLED and message.channel.id not in IGNORED_WARNING_CHANNELS:
        has_ignored_role = any(role.id in IGNORED_WARNING_ROLES for role in message.author.roles)
        is_admin = message.author.guild_permissions.administrator
        if not has_ignored_role and not is_admin:
            highest_role = max(message.guild.roles, key=lambda r: r.position)
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
                if guild_id not in WARNINGS:
                    WARNINGS[guild_id] = {}
                if user_id not in WARNINGS[guild_id]:
                    WARNINGS[guild_id][user_id] = 0
                WARNINGS[guild_id][user_id] += 1
                count = WARNINGS[guild_id][user_id]
                save_warnings(WARNINGS)
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
                        WARNINGS[guild_id][user_id] = 0
                        save_warnings(WARNINGS)
                    except Exception as e:
                        embed = discord.Embed(title="⚠️ Warning 3/3", color=discord.Colour.red())
                        embed.description = f"{message.author.mention}, you have received **Warning 3/3**! Please stop mentioning the highest role.\n\n⚠️ **Your warnings have been reset.**"
                        await message.channel.send(embed=embed)
                        WARNINGS[guild_id][user_id] = 0
                        save_warnings(WARNINGS)

# ---- FIXED .cmds COMMAND (EMBED WITH FALLBACK) ----
@bot.command(name='cmds')
async def show_commands(ctx):
    if ctx.author.bot:
        return
    print(f".cmds triggered by {ctx.author}")  # debug

    # Build the embed
    embed = discord.Embed(title="📋 Bot Commands", color=discord.Colour.blue())
    embed.add_field(
        name="Prefix Commands",
        value="`.d <link>` – Deobfuscate from URL\n"
              "`.cmds` – Show this command list\n"
              "`.purge <amount>` – Delete messages (max 1000)",
        inline=False
    )
    embed.add_field(
        name="Auto‑Features",
        value="• **Mention Protection** – Auto‑warns & times out NON‑ADMIN users who mention the highest role 3 times\n"
              "• **Protected Roles** – Set specific roles that trigger warnings for EVERYONE (including admins) when mentioned",
        inline=False
    )
    embed.add_field(
        name="Slash Commands",
        value="`/deobf file:` – Deobfuscate from uploaded `.lua` file\n"
              "`/deobf code:` – Deobfuscate from pasted Lua code\n"
              "`/instant permissions` – Instantly disable @everyone messaging in ALL channels\n"
              "`/add verify` – Set up verification system\n"
              "`/say` – Send a custom message with mentions\n"
              "`/warning mention` – Toggle mention warnings, exclude channels/roles, protect roles\n"
              "`/auto purge messages` – Auto‑purge a channel after inactivity\n"
              "`/create ticket` – Create a ticket panel\n"
              "`/create embed` – Create a custom embed with optional plain text message\n"
              "`/ban` – Ban a user\n"
              "`/unban` – Unban a user by ID\n"
              "`/kick` – Kick a user\n"
              "`/mute` – Mute a user with duration\n"
              "`/unmute` – Unmute a user",
        inline=False
    )
    embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)

    # Try to send the embed; fall back to plain text if Embed Links is missing
    try:
        await ctx.send(embed=embed)
    except discord.Forbidden:
        # Fallback plain text (no embed)
        plain = (
            "**📋 Bot Commands**\n\n"
            "**Prefix Commands**\n"
            "`.d <link>` – Deobfuscate from URL\n"
            "`.cmds` – Show this command list\n"
            "`.purge <amount>` – Delete messages (max 1000)\n\n"
            "**Auto‑Features**\n"
            "• Mention Protection – warns & times out non‑admins\n"
            "• Protected Roles – warns everyone when mentioned\n\n"
            "**Slash Commands**\n"
            "`/deobf file/code`, `/instant permissions`, `/add verify`, `/say`,\n"
            "`/warning mention`, `/auto purge messages`, `/create ticket`, `/create embed`,\n"
            "`/ban`, `/unban`, `/kick`, `/mute`, `/unmute`"
        )
        await ctx.send(plain)

    # Delete the command message if possible
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command(name='d')
async def deobf_prefix(ctx, *, link: str):
    if ctx.author.bot:
        return
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
    await ctx.send(file=discord.File(filename))
    os.remove(filename)

@bot.command(name='purge')
@commands.has_permissions(manage_messages=True)
async def purge_messages(ctx, amount: int):
    if amount < 1:
        await ctx.send("❌ Please specify a positive number.", delete_after=3)
        return
    if amount > 1000:
        await ctx.send("❌ Maximum purge limit is 1000 messages.", delete_after=3)
        return
    try:
        deleted = await ctx.channel.purge(limit=amount + 1)
        msg = await ctx.send(f"✅ Deleted {len(deleted)-1} messages.")
        await asyncio.sleep(5)
        await msg.delete()
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to manage messages.", delete_after=3)
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {str(e)}", delete_after=5)

@purge_messages.error
async def purge_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need the **Manage Messages** permission to use this command.", delete_after=3)
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Please provide a valid number of messages to delete.\nUsage: `.purge <amount>`", delete_after=5)
    else:
        await ctx.send(f"❌ An error occurred: {str(error)}", delete_after=5)

@create_group.command(name="embed", description="Create a custom embed with an optional plain text message (both in one message)")
@app_commands.describe(
    description="Required: The embed description text",
    title="Optional: The embed title",
    footer="Optional: The embed footer text",
    image="Optional: A large image to display on the embed",
    color="Optional: Embed color (name or hex, default: green)",
    plain_message="Optional: A plain text message to include in the same message (supports @everyone, @here, role and user mentions)"
)
@app_commands.rename(plain_message="plain-message")
async def create_embed(interaction: discord.Interaction, description: str, title: str = "", footer: str = "", image: discord.Attachment = None, color: str = "green", plain_message: str = ""):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message("❌ Error: Missing permission — Manage Messages", ephemeral=True)
    embed_color = get_color(color)
    embed = discord.Embed(description=description, color=embed_color)
    if title:
        embed.title = title
    if footer:
        embed.set_footer(text=footer)
    if image:
        embed.set_image(url=image.url)
    await interaction.response.send_message("✅ Embed sent successfully!", ephemeral=True)
    allowed_mentions = discord.AllowedMentions(users=True, roles=True, everyone=True)
    await interaction.channel.send(content=plain_message if plain_message else None, embed=embed, allowed_mentions=allowed_mentions)

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
    try:
        dm_embed = discord.Embed(
            title="🔨 You Have Been Banned",
            description=f"You have been banned from **{interaction.guild.name}**",
            color=discord.Colour.red()
        )
        dm_embed.add_field(name="Reason", value=ban_reason, inline=False)
        dm_embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
        dm_embed.set_footer(text=f"Server: {interaction.guild.name}")
        dm_embed.timestamp = discord.utils.utcnow()
        await user.send(embed=dm_embed)
    except:
        pass

@tree.command(name="unban", description="Unban a user from the server")
@app_commands.describe(user_id="Required: ID of the user to unban")
@app_commands.rename(user_id="user-id")
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
                await interaction.response.send_message(embed=embed)
                try:
                    dm_embed = discord.Embed(
                        title="✅ You Have Been Unbanned",
                        description=f"You have been unbanned from **{interaction.guild.name}**",
                        color=discord.Colour.green()
                    )
                    dm_embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
                    dm_embed.set_footer(text=f"Server: {interaction.guild.name}")
                    dm_embed.timestamp = discord.utils.utcnow()
                    await ban_entry.user.send(embed=dm_embed)
                except:
                    pass
                return
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
    try:
        dm_embed = discord.Embed(
            title="👢 You Have Been Kicked",
            description=f"You have been kicked from **{interaction.guild.name}**",
            color=discord.Colour.orange()
        )
        dm_embed.add_field(name="Reason", value=kick_reason, inline=False)
        dm_embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
        dm_embed.set_footer(text=f"Server: {interaction.guild.name}")
        dm_embed.timestamp = discord.utils.utcnow()
        await user.send(embed=dm_embed)
    except:
        pass

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
            try:
                dm_embed = discord.Embed(
                    title="🔇 You Have Been Muted",
                    description=f"You have been muted in **{interaction.guild.name}**",
                    color=discord.Colour.red()
                )
                dm_embed.add_field(name="Duration", value=f"**{time}**", inline=False)
                dm_embed.add_field(name="Reason", value=mute_reason, inline=False)
                dm_embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
                dm_embed.set_footer(text=f"Server: {interaction.guild.name}")
                dm_embed.timestamp = discord.utils.utcnow()
                await user.send(embed=dm_embed)
            except:
                pass
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
        try:
            dm_embed = discord.Embed(
                title="🔇 You Have Been Muted",
                description=f"You have been permanently muted in **{interaction.guild.name}**",
                color=discord.Colour.red()
            )
            dm_embed.add_field(name="Duration", value="**Permanent**", inline=False)
            dm_embed.add_field(name="Reason", value=mute_reason, inline=False)
            dm_embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
            dm_embed.set_footer(text=f"Server: {interaction.guild.name}")
            dm_embed.timestamp = discord.utils.utcnow()
            await user.send(embed=dm_embed)
        except:
            pass

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
        try:
            dm_embed = discord.Embed(
                title="🔊 You Have Been Unmuted",
                description=f"You have been unmuted in **{interaction.guild.name}**",
                color=discord.Colour.green()
            )
            dm_embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
            dm_embed.set_footer(text=f"Server: {interaction.guild.name}")
            dm_embed.timestamp = discord.utils.utcnow()
            await user.send(embed=dm_embed)
        except:
            pass
    else:
        embed = discord.Embed(title="🔊 Timeout Removed", color=discord.Colour.green())
        embed.add_field(name="User", value=user.mention, inline=False)
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
        await interaction.response.send_message(embed=embed)
        try:
            dm_embed = discord.Embed(
                title="🔊 Your Timeout Has Been Removed",
                description=f"Your timeout has been removed in **{interaction.guild.name}**",
                color=discord.Colour.green()
            )
            dm_embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
            dm_embed.set_footer(text=f"Server: {interaction.guild.name}")
            dm_embed.timestamp = discord.utils.utcnow()
            await user.send(embed=dm_embed)
        except:
            pass

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print(f"Loaded warnings for {len(WARNINGS)} guilds")
    try:
        await tree.sync()
    except Exception as e:
        print(f"Sync Error: {e}")

if __name__ == "__main__":
    keep_alive()
    TOKEN = os.getenv('TOKEN')
    if TOKEN:
        print("Starting Discord bot...")
        bot.run(TOKEN)
    else:
        print("ERROR: TOKEN environment variable not set!")
