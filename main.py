from flask import Flask
from threading import Thread
import os
import hashlib
import random
import string
import discord
import aiohttp
from discord import app_commands, ui, ButtonStyle, Embed, Colour
from discord.ext import commands

app = Flask('')
@app.route('/')
def home(): return "✅ Bot is alive!"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
tree = bot.tree

USER_DATA = {}
VALID_KEYS = {}
SCRIPTS = {}

def generate_key():
    part1 = ''.join(random.choices(string.ascii_uppercase, k=3))
    part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    part3 = ''.join(random.choices(string.ascii_uppercase, k=3))
    return f"KEY-{part1}-{part2}-{part3}"

def get_hwid(user_id):
    return hashlib.md5(str(user_id).encode()).hexdigest()[:16].upper()

def is_verified(user_id):
    return user_id in USER_DATA and USER_DATA[user_id].get("verified", False)

async def create_paste(code):
    url = "https://rentry.co/api/new"
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choice(chars) for _ in range(8))
    payload = {
        "text": code,
        "url": suffix,
        "edit_code": suffix,
        "json": "1"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("status") == "ok":
                    return f"https://rentry.co/raw/{suffix}"
    return None

class RedeemModal(ui.Modal, title="🔑 Redeem Your Key"):
    key_input = ui.TextInput(
        label="Key to Redeem",
        placeholder="Enter your key...",
        required=True,
        min_length=10,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        key = str(self.key_input).strip()
        hwid = get_hwid(user_id)
        if key in VALID_KEYS:
            USER_DATA[user_id] = {"key": key, "hwid": hwid, "verified": True}
            embed = Embed(title="✅ KEY REDEEMED SUCCESSFULLY!", color=Colour.green())
            embed.add_field(name="🔑 Status", value="✅ UNLOCKED — Full Access Granted", inline=False)
            embed.set_footer(text="Reopen /panel to see your access")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = Embed(title="❌ INVALID KEY!", color=Colour.red())
            embed.description = "The key you entered is not recognized. Please check your key and try again."
            await interaction.response.send_message(embed=embed, ephemeral=True)

class AddScriptModal(ui.Modal, title="➕ Add New Script"):
    name_input = ui.TextInput(label="Script Name", placeholder="e.g. MyScript", required=True)
    code_input = ui.TextInput(label="Paste Your Lua Code", placeholder="Paste your full script code here...", required=True, style=discord.TextStyle.long)

    async def on_submit(self, interaction: discord.Interaction):
        name = str(self.name_input).strip()
        code = str(self.code_input).strip()
        await interaction.response.defer(ephemeral=True)
        paste_url = await create_paste(code)
        if not paste_url:
            return await interaction.followup.send("❌ Failed to create paste link! Try again.", ephemeral=True)
        SCRIPTS[name] = paste_url
        embed = Embed(title="✅ SCRIPT UPLOADED!", color=Colour.green())
        embed.add_field(name="Script Name", value=name, inline=False)
        embed.add_field(name="🔗 Generated Link", value=f"`{paste_url}`", inline=False)
        embed.set_footer(text="Users get auto loadstring from panel!")
        await interaction.followup.send(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    await bot.change_presence(activity=discord.Game(name="/panel | Control Panel"))
    try:
        await tree.sync()
        print("✅ Slash commands synced!")
    except Exception as e:
        print(f"⚠️ Sync: {e}")

@tree.command(name="genkey", description="Generate a new key (Admin only)")
async def genkey(interaction: discord.Interaction, count: int=1):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
    count = max(1, min(count, 10))
    new_keys = []
    for _ in range(count):
        key = generate_key()
        VALID_KEYS[key] = "premium"
        new_keys.append(f"`{key}`")
    embed = Embed(title="✅ KEY(S) GENERATED!", color=Colour.green())
    embed.description = "\n".join(new_keys)
    embed.add_field(name="Format", value="`KEY-XXX-XXXX-XXX`", inline=False)
    embed.set_footer(text="Click 🔑 Redeem Key on panel to activate")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="panel", description="Open Control Panel")
async def panel(interaction: discord.Interaction):
    user_id = interaction.user.id
    verified = is_verified(user_id)
    embed = Embed(
        title="🔐 CONTROL PANEL",
        description="Welcome to your Control Panel. Manage your access and retrieve your script loadstrings instantly.",
        color=Colour.green() if verified else Colour.red()
    )
    if verified:
        embed.add_field(name="🔑 Status", value="✅ Verified — Full Access Granted", inline=False)
        embed.add_field(name="📜 Scripts Available", value=f"{len(SCRIPTS)} script(s)", inline=False)
    else:
        embed.add_field(name="🔒 Access Restricted", value="Click [🔑 Redeem Key] below to unlock all features.", inline=False)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    view = PanelButtons()
    await interaction.response.send_message(embed=embed, view=view)

@tree.command(name="redeem", description="Redeem your key to unlock access")
async def redeem(interaction: discord.Interaction, key: str):
    user_id = interaction.user.id
    hwid = get_hwid(user_id)
    if key in VALID_KEYS:
        USER_DATA[user_id] = {"key": key, "hwid": hwid, "verified": True}
        embed = Embed(title="✅ KEY REDEEMED SUCCESSFULLY!", color=Colour.green())
        embed.add_field(name="🔑 Status", value="✅ UNLOCKED — Full Access Granted", inline=False)
        embed.set_footer(text="Reopen /panel to see your access")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = Embed(title="❌ INVALID KEY!", color=Colour.red())
        embed.description = "The key you entered is not recognized. Please check your key and try again."
        await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="reset_hwid", description="Reset your HWID")
async def reset_hwid(interaction: discord.Interaction):
    user_id = interaction.user.id
    if not is_verified(user_id):
        return await interaction.response.send_message("❌ Not verified! Redeem your key first.", ephemeral=True)
    new_hwid = get_hwid(random.randint(1000000000, 9999999999))
    USER_DATA[user_id]["hwid"] = new_hwid
    embed = Embed(title="✅ HWID RESET SUCCESSFULLY!", color=Colour.blue())
    embed.add_field(name="💻 New HWID", value=f"`{new_hwid}`", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

class PanelButtons(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="🔑 Redeem Key", style=ButtonStyle.primary)
    async def redeem_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if is_verified(interaction.user.id):
            return await interaction.response.send_message("✅ Already verified! Reopen /panel to see your access.", ephemeral=True)
        await interaction.response.send_modal(RedeemModal())

    @ui.button(label="➕ Add Script", style=ButtonStyle.blurple)
    async def add_script_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
        await interaction.response.send_modal(AddScriptModal())

    @ui.button(label="📜 Get Loadstring", style=ButtonStyle.success)
    async def loadstring_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_verified(interaction.user.id):
            return await interaction.response.send_message("❌ Not verified! Click [🔑 Redeem Key] first.", ephemeral=True)
        if not SCRIPTS:
            return await interaction.response.send_message("❌ No scripts available yet. Ask an admin to add one.", ephemeral=True)
        output = "📋 **YOUR WORKING LOADSTRING:**\n```lua\n"
        for name, url in SCRIPTS.items():
            output += f'-- {name}\nloadstring(game:HttpGet("{url}"))()\n\n'
        output += "```\n✅ **COPY & EXECUTE DIRECTLY IN ROBLOX! LINK WORKS 100%!**"
        await interaction.response.send_message(output, ephemeral=True)

    @ui.button(label="🔄 Reset HWID", style=ButtonStyle.secondary)
    async def reset_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_verified(interaction.user.id):
            return await interaction.response.send_message("❌ Not verified! Click [🔑 Redeem Key] first.", ephemeral=True)
        new_hwid = get_hwid(random.randint(1000000000, 9999999999))
        USER_DATA[interaction.user.id]["hwid"] = new_hwid
        embed = Embed(title="✅ HWID RESET SUCCESSFULLY!", color=Colour.blue())
        embed.add_field(name="💻 New HWID", value=f"`{new_hwid}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="❌ Close", style=ButtonStyle.danger)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

keep_alive()
TOKEN = os.getenv('TOKEN')
bot.run(TOKEN)
