from flask import Flask
from threading import Thread
import os
import discord
from discord.ext import commands

app = Flask('')
@app.route('/')
def home(): return "✅ Bot is alive!"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ SUCCESS! Logged in as {bot.user}')

keep_alive()
TOKEN = os.getenv('TOKEN')
print("🔑 Token loaded:", "YES" if TOKEN else "NO ❌")
bot.run(TOKEN)
