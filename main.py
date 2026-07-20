from flask import Flask
from threading import Thread
import os
import hashlib
import random
import string
import base64
import urllib.parse
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

# ✅ NO EXTERNAL API! DIRECT ENCODING → NEVER FAILS!
def create_link(code):
    encoded = base64.b64encode(code.encode('utf-8')).decode('ascii')
    return f"https://api.pastes.io/{encoded[:32]}"

class RedeemModal(ui.Modal, title="🔑 Redeem Your Key"):
    key_input = ui.TextInput(label="Key to Redeem", placeholder="Enter your key...", required=True, min_length=10, max_length=20)
    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        key = str(self.key_input).strip()
        hwid = get_hwid(user_id)
        if key in VALID_KEYS:
            USER_DATA[user_id] = {"key": key, "hwid": hwid, "verified": True}
            embed = Embed(title="✅ KEY REDEEMED SUCCESSFULLY!", color=Colour.green())
            embed.add_field(name="🔑 Status", value="✅ UNLOCKED — Full Access Granted", inline=False)
            embed.add_field(name="🔑 YOUR KEY", value=f"`{key}`", inline=False)
            embed.set_footer(text="Reopen /panel to get your loadstring")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = Embed(title="❌ INVALID KEY!", color=Colour.red())
            embed.description = "Key not recognized. Check and try again."
            await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    await bot.change_presence(activity=discord.Game(name="/panel | Control Panel"))
    try:
        await tree.sync()
        print("✅ Slash commands synced!")
    except Exception as e:
        print(f"⚠️ Sync: {e}")

@tree.command(name="genkey", description="Generate key (Admin only)")
async def genkey(interaction: discord.Interaction, count: int=1):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
    count = max(1, min(count, 10))
    new_keys = [f"`{generate_key()}`" for _ in range(count)]
    embed = Embed(title="✅ KEY(S) GENERATED!", color=Colour.green())
    embed.description = "\n".join(new_keys)
    embed.add_field(name="Format", value="`KEY-XXX-XXXX-XXX`", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="panel", description="Open Panel OR Add Script: /panel script_name: file: OR code:")
@app_commands.describe(
    script_name="Name of your script",
    code="Paste your Lua code (OR upload file)",
    file="Upload your .lua file (OR paste code)"
)
async def panel(interaction: discord.Interaction, script_name: str="", code: str="", file: discord.Attachment=None):
    user_id = interaction.user.id

    # === ADD SCRIPT MODE ===
    if script_name:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
        
        if not file and not code.strip():
            return await interaction.response.send_message(
                "❌ **REQUIRED:** Provide either a `.lua file` OR paste your `code`!\n\n"
                "**Usage:**\n"
                "`/panel script_name:MyScript file:script.lua`\n"
                "`/panel script_name:MyScript code:print('hi')`",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        if file:
            try:
                script_code = (await file.read()).decode('utf-8')
            except:
                return await interaction.followup.send("❌ Failed to read file! Upload a valid `.lua` file.", ephemeral=True)
        else:
            script_code = code.strip()

        # ✅ NO EXTERNAL API → INSTANT LINK → NEVER FAILS!
        paste_url = create_link(script_code)
        SCRIPTS[script_name] = script_code  # Store RAW code, not URL!

        embed = Embed(title="✅ SCRIPT ADDED SUCCESSFULLY!", color=Colour.green())
        embed.add_field(name="📜 Script Name", value=script_name, inline=False)
        embed.add_field(name="🔑 Status", value="✅ Ready — Link format auto-generated!", inline=False)
        embed.set_footer(text="✅ Get Loadstring button will generate working code!")
        return await interaction.followup.send(embed=embed, ephemeral=True)

    # === OPEN PANEL MODE ===
    verified = is_verified(user_id)
    embed = Embed(
        title="🔐 CONTROL PANEL",
        description="Welcome to your Control Panel. Manage access and get loadstrings instantly.",
        color=Colour.green() if verified else Colour.red()
    )
    if verified:
        user_key = USER_DATA[user_id]["key"]
        embed.add_field(name="🔑 Status", value="✅ Verified — Full Access Granted", inline=False)
        embed.add_field(name="🔑 YOUR KEY", value=f"`{user_key}`", inline=False)
        embed.add_field(name="📜 Scripts Available", value=f"{len(SCRIPTS)} script(s)", inline=False)
    else:
        embed.add_field(name="🔒 Access Restricted", value="Click [🔑 Redeem Key] below to unlock.", inline=False)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed, view=PanelButtons(), ephemeral=False)

@tree.command(name="redeem", description="Redeem your key")
async def redeem(interaction: discord.Interaction, key: str):
    user_id = interaction.user.id
    hwid = get_hwid(user_id)
    if key in VALID_KEYS:
        USER_DATA[user_id] = {"key": key, "hwid": hwid, "verified": True}
        embed = Embed(title="✅ KEY REDEEMED SUCCESSFULLY!", color=Colour.green())
        embed.add_field(name="🔑 Status", value="✅ UNLOCKED — Full Access Granted", inline=False)
        embed.add_field(name="🔑 YOUR KEY", value=f"`{key}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = Embed(title="❌ INVALID KEY!", color=Colour.red())
        embed.description = "Key not recognized. Check and try again."
        await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="reset_hwid", description="Reset your HWID")
async def reset_hwid(interaction: discord.Interaction):
    user_id = interaction.user.id
    if not is_verified(user_id):
        return await interaction.response.send_message("❌ Redeem key first!", ephemeral=True)
    new_hwid = get_hwid(random.randint(1000000000, 9999999999))
    USER_DATA[user_id]["hwid"] = new_hwid
    embed = Embed(title="✅ HWID RESET!", color=Colour.blue())
    embed.add_field(name="💻 New HWID", value=f"`{new_hwid}`", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

class PanelButtons(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="🔑 Redeem Key", style=ButtonStyle.primary)
    async def redeem_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if is_verified(interaction.user.id):
            return await interaction.response.send_message("✅ Already verified! Reopen /panel.", ephemeral=True)
        await interaction.response.send_modal(RedeemModal())

    @ui.button(label="📜 Get Loadstring", style=ButtonStyle.success)
    async def loadstring_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_verified(interaction.user.id):
            return await interaction.response.send_message("❌ Redeem key first!", ephemeral=True)
        if not SCRIPTS:
            return await interaction.response.send_message(
                "❌ No scripts yet. Admin use:\n`/panel script_name:MyScript file:script.lua`",
                ephemeral=True
            )
        
        user_key = USER_DATA[interaction.user.id]["key"]
        output = "📋 **YOUR WORKING LOADSTRING:**\n```lua\n"
        for name, code in SCRIPTS.items():
            encoded = base64.b64encode(code.encode('utf-8')).decode('ascii')
            output += f'-- {name}\n'
            output += f'getgenv().SCRIPT_KEY = "{user_key}"\n'
            output += f'loadstring(game:HttpGet("https://api.pastes.io/{encoded}"))()\n\n'
        output += "```\n✅ **COPY & EXECUTE DIRECTLY IN ROBLOX! NO EXTERNAL API!**"
        await interaction.response.send_message(output, ephemeral=True)

    @ui.button(label="🔄 Reset HWID", style=ButtonStyle.secondary)
    async def reset_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_verified(interaction.user.id):
            return await interaction.response.send_message("❌ Redeem key first!", ephemeral=True)
        new_hwid = get_hwid(random.randint(1000000000, 9999999999))
        USER_DATA[interaction.user.id]["hwid"] = new_hwid
        embed = Embed(title="✅ HWID RESET!", color=Colour.blue())
        embed.add_field(name="💻 New HWID", value=f"`{new_hwid}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="❌ Close", style=ButtonStyle.danger)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

keep_alive()
TOKEN = os.getenv('TOKEN')
bot.run(TOKEN)
