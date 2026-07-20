from flask import Flask
from threading import Thread
import os
import discord
from discord import ui, ButtonStyle, Embed, Colour
from discord.ext import commands

app = Flask('')
@app.route('/')
def home(): return "✅ Bot is alive!"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

# === BOT SETUP ===
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# === BOT IS READY ===
@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    await bot.change_presence(activity=discord.Game(name="!panel | Online!"))

# === 📊 PANEL COMMAND — YOUR MAIN PANEL! ===
@bot.command(name='panel')
async def panel(ctx):
    embed = Embed(
        title="🤖 BOT CONTROL PANEL",
        description="Welcome to the Bot Panel! Choose an option below!",
        color=Colour.purple()
    )
    embed.add_field(name="📋 Commands", value="`!help` - Show all commands\n`!ping` - Check bot latency", inline=False)
    embed.add_field(name="🛠️ Moderation", value="`!clear` - Clear messages\n`!kick` - Kick user", inline=False)
    embed.add_field(name="ℹ️ Info", value="`!botinfo` - Bot info\n`!serverinfo` - Server info", inline=False)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)

    view = PanelButtons()
    await ctx.send(embed=embed, view=view)

# === 🎯 BUTTONS FOR PANEL ===
class PanelButtons(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📋 Commands", style=ButtonStyle.primary, custom_id="cmds")
    async def cmds(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = Embed(title="📋 ALL COMMANDS", color=Colour.blue())
        embed.add_field(name="!panel", value="Show this panel", inline=False)
        embed.add_field(name="!help", value="Help menu", inline=False)
        embed.add_field(name="!ping", value="Bot latency", inline=False)
        embed.add_field(name="!clear [number]", value="Clear messages", inline=False)
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="ℹ️ About", style=ButtonStyle.secondary, custom_id="about")
    async def about(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = Embed(title="ℹ️ ABOUT THIS BOT", color=Colour.green())
        embed.description = "**My Custom Discord Bot**\nBuilt with discord.py • Hosted 24/7!"
        embed.add_field(name="Status", value="✅ Online & Running", inline=False)
        embed.add_field(name="Prefix", value="`!`", inline=False)
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="❌ Close", style=ButtonStyle.danger, custom_id="close")
    async def close_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

# === 🟢 SIMPLE COMMANDS ===
@bot.command(name='ping')
async def ping(ctx):
    await ctx.send(f"🏓 Pong! Bot latency: **{round(bot.latency * 1000)}ms**")

@bot.command(name='help')
async def help_cmd(ctx):
    await ctx.send("""
**📋 BOT COMMANDS:**
`!panel` → Show Control Panel
`!ping` → Check bot response time
`!clear 10` → Clear last 10 messages
`!help` → Show this list
    """)

@bot.command(name='clear')
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount=5):
    await ctx.channel.purge(limit=amount+1)
    msg = await ctx.send(f"✅ Cleared **{amount}** messages!")
    await msg.delete(delay=3)

# === BOT STARTUP ===
keep_alive()
TOKEN = os.getenv('TOKEN')
bot.run(TOKEN)
