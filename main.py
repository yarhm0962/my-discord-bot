from flask import Flask
from threading import Thread
import os
import re
import base64
import aiohttp
import asyncio
import discord
from datetime import timedelta
from discord import app_commands
from discord.ext import commands

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

app = Flask('')
@app.route('/')
def home(): return "Bot is running"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # ⚠️ REQUIRED for the /add verify command to loop through all server members
intents.guilds = True  # Required for member join events

bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)
tree = bot.tree

create_group = app_commands.Group(name="create", description="Commands for creation")
warning_group = app_commands.Group(name="warning", description="Warning system commands")
deobf_group = app_commands.Group(name="deobf", description="Deobfuscation commands")
talking_group = app_commands.Group(name="talking", description="Commands for the AI chatbot")
auto_group = app_commands.Group(name="auto", description="Automation commands")
auto_purge_group = app_commands.Group(name="purge", description="Auto purge commands", parent=auto_group)
add_group = app_commands.Group(name="add", description="Add server features")
instant_group = app_commands.Group(name="instant", description="Instant permission commands")

tree.add_command(create_group)
tree.add_command(warning_group)
tree.add_command(deobf_group)
tree.add_command(talking_group)
tree.add_command(auto_group)
tree.add_command(add_group)
tree.add_command(instant_group)

TICKET_SETTINGS = {}
WARNINGS = {}
AUTO_PURGE_SETTINGS = {}
TIMEOUT_DURATION = 300
MENTION_WARNINGS_ENABLED = True
IGNORED_WARNING_CHANNELS = set()
IGNORED_WARNING_ROLES = set()
TALKING_CHANNELS = {}
VERIFIED_ROLE_CACHE = {}  # Cache for verified role per guild

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

@bot.event
async def on_member_join(member):
    """Automatically assign 'Not Verified' role to new members if verification system is set up"""
    if member.bot:
        return
    
    # Check if this guild has a verified role cached
    if member.guild.id not in VERIFIED_ROLE_CACHE:
        return
    
    verified_role = VERIFIED_ROLE_CACHE[member.guild.id]
    not_verified_role = discord.utils.get(member.guild.roles, name="Not Verified")
    
    # If the Not Verified role doesn't exist or the member already has verified role, skip
    if not not_verified_role or verified_role in member.roles:
        return
    
    try:
        await member.add_roles(not_verified_role, reason="Auto-assigned 'Not Verified' role on join")
        print(f"✅ Assigned 'Not Verified' role to {member.name} in {member.guild.name}")
    except discord.Forbidden:
        print(f"❌ Missing permission to assign 'Not Verified' role to {member.name}")
    except Exception as e:
        print(f"❌ Error assigning 'Not Verified' role to {member.name}: {e}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    # Handle the verification button globally so it survives bot restarts
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

@instant_group.command(name="permissions", description="Instantly disable message sending permissions for @everyone in ALL channels")
async def instant_permissions(interaction: discord.Interaction):
    """Disable Send Messages, Send Messages in Threads, Create Public Threads, and Create Private Threads for @everyone in all channels"""
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Error: Administrator permission is required to use this command.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    
    # Get the @everyone role
    everyone_role = interaction.guild.default_role
    
    updated_channels = 0
    failed_channels = []
    
    # Loop through all channels in the guild
    for channel in interaction.guild.channels:
        try:
            # Only apply to text channels (including forums and threads)
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.ForumChannel, discord.Thread)):
                await channel.set_permissions(
                    everyone_role,
                    send_messages=False,
                    send_messages_in_threads=False,
                    create_public_threads=False,
                    create_private_threads=False
                )
                updated_channels += 1
                await asyncio.sleep(0.1)  # Prevent rate limiting
        except Exception as e:
            failed_channels.append(f"{channel.name} ({str(e)})")
    
    # Create response embed
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

    # Cache the verified role for this guild
    VERIFIED_ROLE_CACHE[interaction.guild.id] = role

    # 1. Check for or create the "Not Verified" role
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

    # 2. Make the verification channel strictly Read-Only for @everyone
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

    # 3. Update Channel Permissions 
    # Hides all channels from "Not Verified", except the enabled_channel (and forces read-only on it)
    for ch in interaction.guild.channels:
        try:
            if ch.id == enabled_channel.id:
                # For the verification channel, use the full set of permissions
                # Check if it's a text channel before using thread permissions
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
                    # For non-text channels, just set basic permissions
                    await ch.set_permissions(
                        not_verified_role,
                        view_channel=True,
                        read_message_history=True,
                        send_messages=False
                    )
            else:
                # For other channels, just hide them
                await ch.set_permissions(not_verified_role, view_channel=False)
            await asyncio.sleep(0.05) # Prevent Discord API rate limits
        except Exception:
            pass # Ignore channels the bot cannot edit

    # 4. Add "Not Verified" to everyone who is missing the verified role - FAST VERSION
    assigned_count = 0
    failed_members = []
    
    # Gather all members who need the role
    members_to_update = []
    for member in interaction.guild.members:
        if not member.bot and role not in member.roles and not_verified_role not in member.roles:
            members_to_update.append(member)
    
    # Process members in batches to avoid rate limits while being fast
    batch_size = 10  # Process 10 members at a time
    for i in range(0, len(members_to_update), batch_size):
        batch = members_to_update[i:i + batch_size]
        tasks = []
        for member in batch:
            task = member.add_roles(not_verified_role, reason="Auto-assigned 'Not Verified' role")
            tasks.append(task)
        
        # Wait for all tasks in this batch to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successes and failures
        for result in results:
            if isinstance(result, Exception):
                failed_members.append(str(result))
            else:
                assigned_count += 1
        
        # Small delay between batches to prevent rate limiting
        if i + batch_size < len(members_to_update):
            await asyncio.sleep(0.5)

    # 5. Create and send the Verification Embed to the specified channel
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
    
    # Send completion message with stats
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

@talking_group.command(name="bot", description="Toggle the AI talking bot in a specific channel")
@app_commands.describe(
    status="Select whether to turn the bot On or Off",
    channel="Required if On: The channel where the bot will reply to user messages"
)
@app_commands.choices(status=[
    app_commands.Choice(name="On", value="on"),
    app_commands.Choice(name="Off", value="off")
])
async def setup_talking_bot(interaction: discord.Interaction, status: app_commands.Choice[str], channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Error: Administrator permission is required.", ephemeral=True)
    
    if status.value == "on":
        if not channel:
            return await interaction.response.send_message("❌ Error: You must provide a channel when turning the bot On.", ephemeral=True)
        TALKING_CHANNELS[interaction.guild.id] = channel.id
        embed = discord.Embed(
            title="🤖 Talking Bot Enabled", 
            description=f"The AI chatbot is now active in {channel.mention}!\nAny message sent there will be answered by the bot.", 
            color=discord.Colour.blue()
        )
    else:
        if interaction.guild.id in TALKING_CHANNELS:
            del TALKING_CHANNELS[interaction.guild.id]
        embed = discord.Embed(
            title="🤖 Talking Bot Disabled", 
            description="The AI chatbot has been turned off for this server.", 
            color=discord.Colour.red()
        )
        
    await interaction.response.send_message(embed=embed)

@warning_group.command(name="mention", description="Toggle mention warnings for the highest role On or Off")
@app_commands.describe(
    status="Select whether to turn mention warnings On or Off",
    ignored_channel="Optional: Select a channel where mention warnings will be ignored",
    ignored_role="Optional: Select a role that will bypass mention warnings"
)
@app_commands.rename(ignored_channel="ignored-channel", ignored_role="ignore-role")
@app_commands.choices(status=[
    app_commands.Choice(name="On", value="on"),
    app_commands.Choice(name="Off", value="off")
])
async def warning_mention_toggle(interaction: discord.Interaction, status: app_commands.Choice[str], ignored_channel: discord.TextChannel = None, ignored_role: discord.Role = None):
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

    if status.value == "on":
        MENTION_WARNINGS_ENABLED = True
        embed = discord.Embed(
            title="⚙️ Mention Protection Enabled",
            description=f"Warnings for mentioning the highest role are now **ON**.{channel_msg}{role_msg}",
            color=discord.Colour.green()
        )
    else:
        MENTION_WARNINGS_ENABLED = False
        embed = discord.Embed(
            title="⚙️ Mention Protection Disabled",
            description=f"Warnings for mentioning the highest role are now **OFF** globally.{channel_msg}{role_msg}",
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

    if message.guild.id in TALKING_CHANNELS and message.channel.id == TALKING_CHANNELS[message.guild.id]:
        if not message.content.startswith(bot.command_prefix):
            async with message.channel.typing():
                gemini_key = os.getenv('GEMINI_API_KEY')
                
                if HAS_GENAI and gemini_key:
                    try:
                        genai.configure(api_key=gemini_key)
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        
                        prompt = (
                            f"You are a helpful, intelligent Discord bot interacting in a server called '{message.guild.name}'. "
                            f"The server currently has {message.guild.member_count} members. "
                            f"The user you are replying to is named '{message.author.display_name}'. "
                            f"You have deep knowledge of everything on Earth, especially Lua programming, scripting, and Discord mechanics. "
                            f"Be friendly, concise (under 1800 characters), and format your text nicely for Discord. "
                            f"\n\nUser says: {message.content}"
                        )
                        
                        response = await model.generate_content_async(prompt)
                        if response.text:
                            await message.reply(response.text[:1990])
                    except Exception as e:
                        await message.reply("⚠️ My AI brain ran into an error processing that request.")
                else:
                    await message.reply(
                        "⚠️ **AI is not properly configured!**\n"
                        "To use the talking bot, the owner must:\n"
                        "1. Install the package (`pip install google-generativeai`)\n"
                        "2. Add a `GEMINI_API_KEY` to the environment variables."
                    )
            return

    if message.channel.id in AUTO_PURGE_SETTINGS:
        settings = AUTO_PURGE_SETTINGS[message.channel.id]
        settings["message_count"] = settings.get("message_count", 0) + 1
        if settings["message_count"] >= 2:
            existing_task = settings.get("task")
            if existing_task and not existing_task.done():
                existing_task.cancel()
            settings["task"] = asyncio.create_task(schedule_auto_purge(message.channel.id))

    # MENTION WARNINGS - FIXED: Now warns ANYONE who mentions the highest role
    # regardless of their permissions (except ignored roles)
    if MENTION_WARNINGS_ENABLED and message.channel.id not in IGNORED_WARNING_CHANNELS:
        # Check if the message AUTHOR has an ignored role
        has_ignored_role = any(role.id in IGNORED_WARNING_ROLES for role in message.author.roles)
        
        # Only skip if the author has an ignored role
        # This means: NO admin bypass - EVERYONE gets warned unless they have an ignored role
        if not has_ignored_role:
            highest_role = max(message.guild.roles, key=lambda r: r.position)
            
            mentioned_highest = False
            # Check if the highest role was mentioned directly
            if highest_role in message.role_mentions:
                mentioned_highest = True
            else:
                # Check if any mentioned user has the highest role
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
                        WARNINGS[guild_id][user_id] = 0
                    except Exception as e:
                        embed = discord.Embed(title="⚠️ Warning 3/3", color=discord.Colour.red())
                        embed.description = f"{message.author.mention}, you have received **Warning 3/3**! Please stop mentioning the highest role.\n\n⚠️ **Your warnings have been reset.**"
                        await message.channel.send(embed=embed)
                        WARNINGS[guild_id][user_id] = 0
        
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
**AI Talking Bot** - Chats contextually in designated channels
""", inline=False)
    embed.add_field(name="Slash Commands", value="""
`/instant permissions` - Instantly disable @everyone messaging in ALL channels
`/talking bot status:[On/Off] [channel:]` - Set up a channel where the bot will chat using AI
`/add verify role:@role enabled-channel:#channel` - Set up verification system and auto-role members
`/say message:` - Send a custom message as the bot with mentions
`/warning mention status:[On/Off] [ignored-channel:] [ignore-role:]` - Toggle mention warnings and exclude specific channels or roles
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
    await ctx.send(file=discord.File(filename))
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
    await interaction.followup.send(content="Success: File deobfuscated successfully", file=discord.File(filename))
    os.remove(filename)

async def close_ticket_callback(interaction: discord.Interaction):
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

def build_ticket_actions_view(include_claim: bool = True):
    view = discord.ui.View(timeout=None)
    close_btn = discord.ui.Button(label="Close Ticket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    close_btn.callback = close_ticket_callback
    view.add_item(close_btn)
    if include_claim:
        claim_btn = discord.ui.Button(label="Claim Ticket", emoji="🎫", style=discord.ButtonStyle.primary, custom_id="claim_ticket_btn")

        async def claim_ticket_callback(interaction: discord.Interaction):
            settings = TICKET_SETTINGS.get(interaction.channel.id)
            if not settings:
                return await interaction.response.send_message("Error: Could not verify ticket permissions", ephemeral=True)
            staff_role = interaction.guild.get_role(settings["admin_role_id"])
            is_staff = staff_role in interaction.user.roles if staff_role else False
            if not (is_staff or interaction.user.guild_permissions.administrator):
                return await interaction.response.send_message("Error: Only an admin/staff member can claim this ticket", ephemeral=True)
            if claim_btn.disabled:
                return await interaction.response.send_message("Error: This ticket has already been claimed", ephemeral=True)

            creator_id = settings.get("creator_id")
            creator_mention = f"<@{creator_id}>" if creator_id else ""
            claim_embed = discord.Embed(
                title="🎫 Ticket Claimed",
                description=f"{interaction.user.mention} has claimed this ticket and will be assisting you shortly!",
                color=discord.Colour.yellow()
            )
            claim_btn.disabled = True
            claim_btn.label = f"Claimed by {interaction.user.display_name}"
            await interaction.response.edit_message(view=claim_btn.view)
            await interaction.channel.send(content=creator_mention, embed=claim_embed)

        claim_btn.callback = claim_ticket_callback
        view.add_item(claim_btn)
    return view

@create_group.command(name="ticket", description="Create a ticket panel")
@app_commands.describe(
    admin_role="Required: Role that manages and responds to tickets",
    category="Required: Category where tickets will be created",
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
    enable_claim_button="enable-claim-button",
    button_label="button-label",
    button_emoji="button-emoji"
)
async def create_ticket_panel(interaction: discord.Interaction, admin_role: discord.Role, category: discord.CategoryChannel, enable_claim_button: bool, description: str = "", title: str = "", footer: str = "", image: discord.Attachment = None, color: str = "green", button_label: str = "Create Ticket", button_emoji: str = "🎟️"):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Error: Administrator permission is required", ephemeral=True)
    panel_description = description if description else "**CREATE A TICKET BELOW 🎟️**"
    embed_color = get_color(color)
    TICKET_SETTINGS[interaction.channel.id] = {
        "admin_role_id": admin_role.id,
        "category_id": category.id,
        "guild_id": interaction.guild.id,
        "enable_claim_button": enable_claim_button
    }

    async def create_ticket_callback(btn_interaction: discord.Interaction):
        settings = TICKET_SETTINGS.get(btn_interaction.channel_id)
        if not settings:
            return await btn_interaction.response.send_message("Error: Panel is not configured properly", ephemeral=True)
        guild = btn_interaction.guild
        ticket_category = guild.get_channel(settings["category_id"])
        staff_role = guild.get_role(settings["admin_role_id"])
        if not ticket_category or not staff_role:
            return await btn_interaction.response.send_message("Error: Category or Admin Role was not found", ephemeral=True)

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
            "category_id": category.id,
            "enable_claim_button": enable_claim_button
        }
        ticket_embed = discord.Embed(title="Ticket Created", description="**Please wait for a staff member to assist you**", color=discord.Colour.green())
        ticket_embed.add_field(name="Created By", value=btn_interaction.user.mention, inline=False)
        await ticket_channel.send(embed=ticket_embed, view=build_ticket_actions_view(enable_claim_button))
        await btn_interaction.response.send_message(f"Success: Ticket created → {ticket_channel.mention}", ephemeral=True)

    panel_view = discord.ui.View(timeout=None)
    create_btn = discord.ui.Button(label=button_label, emoji=button_emoji, style=discord.ButtonStyle.success, custom_id="create_ticket_btn")
    create_btn.callback = create_ticket_callback
    panel_view.add_item(create_btn)

    embed = discord.Embed(description=panel_description, color=embed_color)
    if title:
        embed.title = title
    if footer:
        embed.set_footer(text=footer)
    if image:
        embed.set_image(url=image.url)
    await interaction.response.send_message("Ticket panel created!", ephemeral=True)
    await interaction.channel.send(embed=embed, view=panel_view)

@create_group.command(name="embed", description="Create a custom embed")
@app_commands.describe(
    description="Required: The embed description text",
    title="Optional: The embed title",
    footer="Optional: The embed footer text",
    image="Optional: A large image to display on the embed",
    color="Optional: Embed color (name or hex, default: green)"
)
async def create_embed(interaction: discord.Interaction, description: str, title: str = "", footer: str = "", image: discord.Attachment = None, color: str = "green"):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message("Error: Missing permission — Manage Messages", ephemeral=True)
    embed_color = get_color(color)
    embed = discord.Embed(description=description, color=embed_color)
    if title:
        embed.title = title
    if footer:
        embed.set_footer(text=footer)
    if image:
        embed.set_image(url=image.url)
    await interaction.response.send_message("Embed sent successfully!", ephemeral=True)
    await interaction.channel.send(embed=embed)

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
