from flask import Flask
from threading import Thread
import os
import hashlib
import random
import string
import discord
from discord import ui, ButtonStyle, Embed, Colour
from discord.ext import commands

app = Flask('')
@app.route('/')
def home(): return "✅ Bot is alive!"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

USER_DATA = {}
VALID_KEYS = {}
SCRIPTS = {}

def generate_key():
    part1 = ''.join(random.choices(string.ascii_uppercase, k=3))
    part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    part3 = ''.join(random.choices(string.ascii_uppercase, k=3))
    return f"KEY-{part1}-{part2}-{part3}"

def get_hwid(user_id: int) -> str:
    return hashlib.md5(str(user_id).encode()).hexdigest()[:16].upper()

def is_verified(user_id: int) -> bool:
    return user_id in USER_DATA and USER_DATA[user_id].get("verified", False)

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    await bot.change_presence(activity=discord.Game(name="!panel | Key System"))

@bot.command(name='genkey')
@commands.has_permissions(administrator=True)
async def gen_key(ctx, count: int=1):
    if count < 1: count = 1
    if count > 10: count = 10
    new_keys = []
    for _ in range(count):
        key = generate_key()
        VALID_KEYS[key] = "premium"
        new_keys.append(f"`{key}`")
    embed = Embed(title="✅ KEY(S) GENERATED!", color=Colour.green())
    embed.description = "\n".join(new_keys)
    embed.add_field(name="Format", value="`KEY-XXX-XXXX-XXX`", inline=False)
    embed.set_footer(text="Use !key YOUR-KEY to activate")
    await ctx.send(embed=embed)

@bot.command(name='key')
async def activate_key(ctx, key_input: str=None):
    if not key_input:
        return await ctx.send("❌ **Usage:** `!key YOUR-KEY-HERE`")
    user_id = ctx.author.id
    hwid = get_hwid(user_id)
    if key_input in VALID_KEYS:
        USER_DATA[user_id] = {
            "key": key_input,
            "hwid": hwid,
            "verified": True
        }
        embed = Embed(title="✅ KEY ACTIVATED SUCCESSFULLY!", color=Colour.green())
        embed.add_field(name="🔑 Status", value="✅ UNLOCKED — Full Access Granted", inline=False)
        embed.add_field(name="💻 Your HWID", value=f"`{hwid}`", inline=False)
        embed.set_footer(text="Use !panel to open Control Panel")
        await ctx.send(embed=embed)
    else:
        embed = Embed(title="❌ INVALID KEY!", color=Colour.red())
        embed.description = "Key not recognized. Ask an admin to generate one."
        await ctx.send(embed=embed)

@bot.command(name='panel')
async def panel(ctx):
    user_id = ctx.author.id
    verified = is_verified(user_id)
    embed = Embed(
        title="🔐 M1RAGE CONTROL PANEL",
        description="✅ **VERIFIED — Full Access**" if verified else "❌ **NOT VERIFIED — Use !key to activate**",
        color=Colour.green() if verified else Colour.red()
    )
    if verified:
        hwid = USER_DATA[user_id]["hwid"]
        embed.add_field(name="🔑 Status", value="✅ Active & Verified", inline=False)
        embed.add_field(name="💻 Your HWID", value=f"`{hwid}`", inline=False)
        embed.add_field(name="📜 Scripts", value=f"{len(SCRIPTS)} scripts available", inline=False)
        embed.add_field(name="⚙️ Commands", value="`!hwid` - Show HWID\n`!script NAME` - Get Loadstring", inline=False)
    else:
        embed.add_field(name="🔒 Access Locked", value="Use `!key YOUR-KEY` to unlock panel", inline=False)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    view = PanelButtons(verified, user_id)
    await ctx.send(embed=embed, view=view)

@bot.command(name='hwid')
async def show_hwid(ctx):
    if not is_verified(ctx.author.id):
        return await ctx.send("❌ **Not verified!** Use `!key YOUR-KEY` first")
    hwid = USER_DATA[ctx.author.id]["hwid"]
    embed = Embed(title="💻 YOUR HWID", color=Colour.blue())
    embed.description = f"```\n{hwid}\n```"
    await ctx.send(embed=embed)

@bot.command(name='script')
async def get_script(ctx, name: str=None):
    if not is_verified(ctx.author.id):
        return await ctx.send("❌ **Not verified!** Use `!key YOUR-KEY` first")
    if not name:
        return await ctx.send(f"❌ Usage: `!script NAME` | Available: {', '.join(SCRIPTS.keys()) or 'None'}")
    if name in SCRIPTS:
        code = SCRIPTS[name]
        loadstring = f"loadstring(game:HttpGet('PASTE-YOUR-URL-HERE'))()"
        embed = Embed(title=f"📜 SCRIPT: {name}", color=Colour.purple())
        embed.add_field(name="🔗 Loadstring", value=f"```lua\n{loadstring}\n```", inline=False)
        embed.add_field(name="📄 Code", value=f"```lua\n{code[:800]}\n```", inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ Script `{name}` not found!")

@bot.command(name='addscript')
@commands.has_permissions(administrator=True)
async def add_script(ctx, name: str, *, code: str):
    SCRIPTS[name] = code
    await ctx.send(f"✅ Script `{name}` saved!")

class PanelButtons(ui.View):
    def __init__(self, verified, user_id):
        super().__init__(timeout=None)
        self.verified = verified
        self.user_id = user_id

    @ui.button(label="📜 Scripts", style=ButtonStyle.primary)
    async def scripts_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.verified:
            return await interaction.response.send_message("❌ Not verified! Use `!key` first", ephemeral=True)
        embed = Embed(title="📜 AVAILABLE SCRIPTS", color=Colour.blue())
        if SCRIPTS:
            for name in SCRIPTS:
                embed.add_field(name=f"• {name}", value=f"`!script {name}`", inline=False)
        else:
            embed.description = "No scripts added yet! Admin use `!addscript`"
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="💻 My HWID", style=ButtonStyle.secondary)
    async def hwid_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.verified:
            return await interaction.response.send_message("❌ Not verified! Use `!key` first", ephemeral=True)
        hwid = USER_DATA[self.user_id]["hwid"]
        embed = Embed(title="💻 YOUR HWID", color=Colour.green())
        embed.description = f"```\n{hwid}\n```"
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="🔑 Status", style=ButtonStyle.success)
    async def status_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.verified:
            return await interaction.response.send_message("❌ Not verified! Use `!key` first", ephemeral=True)
        embed = Embed(title="✅ ACCOUNT STATUS", color=Colour.green())
        embed.add_field(name="Verification", value="✅ Verified", inline=False)
        embed.add_field(name="HWID Locked", value="✅ Yes", inline=False)
        embed.add_field(name="Access Level", value="🔓 Premium", inline=False)
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="❌ Close", style=ButtonStyle.danger)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

keep_alive()
TOKEN = os.getenv('TOKEN')
bot.run(TOKEN)
