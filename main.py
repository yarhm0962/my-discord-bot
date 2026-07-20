from flask import Flask
from threading import Thread
import os
import hashlib
import random
import string
import aiohttp
import discord
from discord import app_commands, ui, ButtonStyle, Embed, Colour
from discord.ext import commands

app = Flask('')
@app.route('/')
def home(): return "Bot is running"
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

# ✅ REAL WORKING LINK CREATION
async def create_paste(code):
    path = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.post(
                "https://rentry.co/api/new",
                data={"text": code, "url": path, "edit_code": path, "json": "1"},
                timeout=30
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "ok":
                        # ✅ STORE REAL WORKING LINK
                        return f"https://rentry.co/raw/{path}"
    except Exception as e:
        print(f"Error: {e}")
    return None

class RedeemModal(ui.Modal, title="Redeem Key"):
    key_input = ui.TextInput(label="Enter your key", placeholder="Paste your key here", required=True, min_length=10, max_length=30)
    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        key = str(self.key_input).strip()
        hwid = get_hwid(user_id)
        if key in VALID_KEYS:
            USER_DATA[user_id] = {"key": key, "hwid": hwid, "verified": True}
            embed = Embed(title="Success", description="Key redeemed successfully", color=Colour.green())
            embed.add_field(name="Your Key", value=f"`{key}`", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = Embed(title="Error", description="Invalid key. Check and try again.", color=Colour.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="/panel"))
    try: await tree.sync()
    except Exception as e: print(f"Sync Error: {e}")

@tree.command(name="generate-key", description="Generate a new access key")
async def genkey(interaction: discord.Interaction, count: int=1):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Permission denied", ephemeral=True)
    count = max(1, min(count, 10))
    new_keys = []
    for _ in range(count):
        key = generate_key()
        VALID_KEYS[key] = "active"
        new_keys.append(f"`{key}`")
    embed = Embed(title="Keys Generated", description="\n".join(new_keys), color=Colour.green())
    embed.add_field(name="Format", value="KEY-XXX-XXXX-XXX", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="panel", description="Add script or open control panel")
@app_commands.describe(
    script_name="Name of your script",
    code="Paste your Lua code",
    file="Upload your .lua file"
)
async def panel(interaction: discord.Interaction, script_name: str="", code: str="", file: discord.Attachment=None):
    user_id = interaction.user.id

    # === ADD SCRIPT MODE ===
    if script_name:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Permission denied", ephemeral=True)

        if not file and not code.strip():
            return await interaction.response.send_message(
                "Error: Provide either file or code.\n\nUsage:\n/panel script_name:MyScript file:script.lua\n/panel script_name:MyScript code:print('hello')",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        if file:
            try: script_code = (await file.read()).decode('utf-8')
            except: return await interaction.followup.send("Error: Failed to read file", ephemeral=True)
        else:
            script_code = code.strip()

        paste_url = await create_paste(script_code)
        if not paste_url:
            return await interaction.followup.send("Error: Failed to create link. Try again.", ephemeral=True)

        SCRIPTS[script_name] = paste_url
        embed = Embed(title="Script Added Successfully", color=Colour.green())
        embed.add_field(name="Script Name", value=script_name, inline=False)
        embed.add_field(name="Working Link", value=f"`{paste_url}`", inline=False)
        embed.add_field(name="Next Step", value="Open /panel → Click Get Loadstring", inline=False)
        return await interaction.followup.send(embed=embed, ephemeral=True)

    # === OPEN PANEL MODE (when script_name is empty) ===
    verified = is_verified(user_id)
    embed = Embed(title="Control Panel", color=Colour.green() if verified else Colour.red())
    if verified:
        user_key = USER_DATA[user_id]["key"]
        embed.add_field(name="Status", value="Verified - Full Access", inline=False)
        embed.add_field(name="Your Key", value=f"`{user_key}`", inline=False)
        embed.add_field(name="Scripts Available", value=str(len(SCRIPTS)), inline=False)
    else:
        embed.add_field(name="Status", value="Not Verified - Redeem key to unlock", inline=False)
    await interaction.response.send_message(embed=embed, view=PanelButtons(), ephemeral=False)

@tree.command(name="redeem-key", description="Redeem your access key")
async def redeem(interaction: discord.Interaction, key: str):
    key = key.strip()
    user_id = interaction.user.id
    hwid = get_hwid(user_id)
    if key in VALID_KEYS:
        USER_DATA[user_id] = {"key": key, "hwid": hwid, "verified": True}
        embed = Embed(title="Success", description="Key redeemed successfully", color=Colour.green())
        embed.add_field(name="Your Key", value=f"`{key}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = Embed(title="Error", description="Invalid key. Check and try again.", color=Colour.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="reset-hardware-id", description="Reset your hardware id")
async def reset_hwid(interaction: discord.Interaction):
    user_id = interaction.user.id
    if not is_verified(user_id):
        return await interaction.response.send_message("Error: Redeem key first", ephemeral=True)
    new_hwid = get_hwid(random.randint(1000000000, 9999999999))
    USER_DATA[user_id]["hwid"] = new_hwid
    embed = Embed(title="Hardware ID Reset", color=Colour.blue())
    embed.add_field(name="New Hardware ID", value=f"`{new_hwid}`", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

class PanelButtons(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Redeem Key", style=ButtonStyle.primary)
    async def redeem_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if is_verified(interaction.user.id):
            return await interaction.response.send_message("Already verified. Reopen panel.", ephemeral=True)
        await interaction.response.send_modal(RedeemModal())

    @ui.button(label="Get Loadstring", style=ButtonStyle.success)
    async def loadstring_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_verified(interaction.user.id):
            return await interaction.response.send_message("Error: Redeem key first", ephemeral=True)
        if not SCRIPTS:
            return await interaction.response.send_message("Error: No scripts available. Add one first.", ephemeral=True)
        user_key = USER_DATA[interaction.user.id]["key"]
        output = "Your Working Loadstring:\n```lua\n"
        for name, url in SCRIPTS.items():
            output += f"-- {name}\n"
            output += f'getgenv().SCRIPT_KEY = "{user_key}"\n'
            output += f'loadstring(game:HttpGet("{url}"))()\n\n'
        output += "```\nCopy everything and paste into your executor."
        await interaction.response.send_message(output, ephemeral=True)

    @ui.button(label="Reset Hardware ID", style=ButtonStyle.secondary)
    async def reset_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_verified(interaction.user.id):
            return await interaction.response.send_message("Error: Redeem key first", ephemeral=True)
        new_hwid = get_hwid(random.randint(1000000000, 9999999999))
        USER_DATA[interaction.user.id]["hwid"] = new_hwid
        embed = Embed(title="Hardware ID Reset", color=Colour.blue())
        embed.add_field(name="New Hardware ID", value=f"`{new_hwid}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Close", style=ButtonStyle.danger)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

keep_alive()
TOKEN = os.getenv('TOKEN')
bot.run(TOKEN)
