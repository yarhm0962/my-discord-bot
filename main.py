from flask import Flask
from threading import Thread
import os
import hashlib
import random
import string
import discord
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
tree = app_commands.CommandTree(bot)

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

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    await bot.change_presence(activity=discord.Game(name="/panel | Control Panel"))
    try:
        await tree.sync()
        print("✅ Slash commands synced!")
    except Exception as e:
        print(f"⚠️ Sync note: {e}")

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
    embed.set_footer(text="Use /redeem to activate your key")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="panel", description="Open Control Panel")
async def panel(interaction: discord.Interaction):
    user_id = interaction.user.id
    verified = is_verified(user_id)
    embed = Embed(
        title="🔐 CONTROL PANEL",
        description="Welcome to your personal Control Panel. Manage your access, view your HWID, and retrieve your scripts & loadstrings all in one place.",
        color=Colour.green() if verified else Colour.red()
    )
    if verified:
        hwid = USER_DATA[user_id]["hwid"]
        embed.add_field(name="🔑 Status", value="✅ Verified — Full Access Granted", inline=False)
        embed.add_field(name="💻 HWID", value=f"`{hwid}`", inline=False)
        embed.add_field(name="📜 Scripts", value=f"{len(SCRIPTS)} scripts available", inline=False)
    else:
        embed.add_field(name="🔒 Access Restricted", value="Redeem a valid key to unlock all features.", inline=False)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text=f"User: {interaction.user.name} | Control Panel System")
    view = PanelButtons(verified, user_id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@tree.command(name="redeem", description="Redeem your key to unlock access")
async def redeem(interaction: discord.Interaction, key: str):
    user_id = interaction.user.id
    hwid = get_hwid(user_id)
    if key in VALID_KEYS:
        USER_DATA[user_id] = {"key": key, "hwid": hwid, "verified": True}
        embed = Embed(title="✅ KEY REDEEMED SUCCESSFULLY!", color=Colour.green())
        embed.add_field(name="🔑 Status", value="✅ UNLOCKED — Full Access Granted", inline=False)
        embed.add_field(name="💻 Your HWID", value=f"`{hwid}`", inline=False)
        embed.set_footer(text="Use /panel to open Control Panel")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = Embed(title="❌ INVALID KEY!", color=Colour.red())
        embed.description = "The key you entered is not recognized. Please check your key and try again."
        await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="reset_hwid", description="Reset your HWID")
async def reset_hwid(interaction: discord.Interaction):
    user_id = interaction.user.id
    if not is_verified(user_id):
        return await interaction.response.send_message("❌ Not verified! Use /redeem first.", ephemeral=True)
    new_hwid = get_hwid(random.randint(1000000000, 9999999999))
    USER_DATA[user_id]["hwid"] = new_hwid
    embed = Embed(title="✅ HWID RESET SUCCESSFULLY!", color=Colour.blue())
    embed.add_field(name="💻 New HWID", value=f"`{new_hwid}`", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="get_script", description="Get your script loadstring")
async def get_script(interaction: discord.Interaction, name: str=None):
    user_id = interaction.user.id
    if not is_verified(user_id):
        return await interaction.response.send_message("❌ Not verified! Use /redeem first.", ephemeral=True)
    if not name:
        return await interaction.response.send_message(f"❌ Usage: /get_script [name] | Available: {', '.join(SCRIPTS.keys()) or 'None'}", ephemeral=True)
    if name in SCRIPTS:
        code = SCRIPTS[name]
        loadstring = "loadstring(game:HttpGet('PASTE-YOUR-URL-HERE'))()"
        embed = Embed(title=f"📜 SCRIPT: {name}", color=Colour.purple())
        embed.add_field(name="🔗 Loadstring", value=f"```lua\n{loadstring}\n```", inline=False)
        embed.add_field(name="📄 Code", value=f"```lua\n{code[:800]}\n```", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Script `{name}` not found!", ephemeral=True)

@tree.command(name="add_script", description="Add a new script (Admin only)")
async def add_script(interaction: discord.Interaction, name: str, code: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
    SCRIPTS[name] = code
    await interaction.response.send_message(f"✅ Script `{name}` saved!", ephemeral=True)

class PanelButtons(ui.View):
    def __init__(self, verified, user_id):
        super().__init__(timeout=None)
        self.verified = verified
        self.user_id = user_id

    @ui.button(label="🔑 Redeem Key", style=ButtonStyle.primary)
    async def redeem_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.verified:
            return await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
        await interaction.response.send_message("👉 Use `/redeem your-key-here` to activate your access!", ephemeral=True)

    @ui.button(label="📜 Get Loadstring", style=ButtonStyle.success)
    async def loadstring_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.verified:
            return await interaction.response.send_message("❌ Not verified! Use `/redeem` first.", ephemeral=True)
        if SCRIPTS:
            embed = Embed(title="📜 AVAILABLE SCRIPTS", color=Colour.blue())
            for name in SCRIPTS:
                embed.add_field(name=f"• {name}", value=f"Use `/get_script {name}`", inline=False)
        else:
            embed = Embed(title="📜 SCRIPTS", description="No scripts added yet. Admin use `/add_script`", color=Colour.orange())
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="🔄 Reset HWID", style=ButtonStyle.secondary)
    async def reset_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.verified:
            return await interaction.response.send_message("❌ Not verified! Use `/redeem` first.", ephemeral=True)
        new_hwid = get_hwid(random.randint(1000000000, 9999999999))
        USER_DATA[self.user_id]["hwid"] = new_hwid
        embed = Embed(title="✅ HWID RESET SUCCESSFULLY!", color=Colour.blue())
        embed.add_field(name="💻 New HWID", value=f"`{new_hwid}`", inline=False)
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="❌ Close", style=ButtonStyle.danger)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

keep_alive()
TOKEN = os.getenv('TOKEN')
bot.run(TOKEN)
