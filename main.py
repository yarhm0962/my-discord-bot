import os
import secrets
import string
from datetime import datetime
from threading import Thread
from flask import Flask, request, redirect, render_template_string, session, url_for
import discord
from discord import app_commands
from discord.ext import commands
import pymongo
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import requests

TOKEN = os.getenv("DISCORD_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
GUILD_ID = int(os.getenv("GUILD_ID"))
PREMIUM_ROLE_ID = int(os.getenv("PREMIUM_ROLE_ID"))
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
BOT_TOKEN = TOKEN

flask_app = Flask(__name__)
flask_app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(16))

mongo_client = MongoClient(MONGODB_URI, server_api=ServerApi('1'))
db = mongo_client["premium_bot"]
licenses_col = db["licenses"]
users_col = db["users"]

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)
tree = bot.tree

def generate_license_key():
    pattern = ['L','L','N','N','L','N','L','L','N','L']
    chars = []
    for p in pattern:
        chars.append(secrets.choice(string.ascii_uppercase if p == 'L' else string.digits))
    return ''.join(chars)

def is_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.id == bot.application.owner.id:
        return True
    return interaction.permissions.administrator

@tree.command(name="access", description="Get premium access with a license key")
async def access_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔒 Access Premium Dumper Bot",
        description=(
            "Unlock full access to all premium features including live game exploration, "
            "advanced dumper tools, anti-deobfuscation bypass, and priority updates. "
            "Verify your license below to get started."
        ),
        color=0x2c3e99
    )
    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="Verify License & Get Access",
        url="https://your-website.com/verify"
    ))
    await interaction.response.send_message(embed=embed, view=view)

@tree.command(name="license_key", description="Generate a new premium license key (admin only)")
@app_commands.default_permissions(administrator=True)
async def license_key_command(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    key = generate_license_key()
    while licenses_col.find_one({"_id": key}):
        key = generate_license_key()
    licenses_col.insert_one({
        "_id": key,
        "used": False,
        "used_by": None,
        "used_at": None,
        "created_at": datetime.utcnow()
    })
    await interaction.response.send_message(f"✅ New license key generated:\n`{key}`", ephemeral=True)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print("✅ Slash commands synced")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="/access | /license_key"))

VERIFY_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>License Verification</title>
    <style>
        body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .container { background: #16213e; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); width: 400px; text-align: center; }
        h1 { color: #2c3e99; }
        input { width: 90%; padding: 12px; margin: 10px 0; border: none; border-radius: 6px; background: #0f3460; color: white; font-size: 16px; }
        button { background: #2c3e99; color: white; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-size: 16px; }
        button:hover { background: #1e2a6b; }
        .error { color: #ff6b6b; margin-top: 10px; }
        .success { color: #51cf66; margin-top: 10px; }
        .login-btn { background: #5865F2; margin-top: 10px; display: inline-block; padding: 12px 24px; border-radius: 6px; text-decoration: none; color: white; }
        .login-btn:hover { background: #4752c4; }
    </style>
</head>
<body>
    <div class="container">
        {% if user %}
            <h2>Welcome, {{ user.username }}!</h2>
            <form method="POST">
                <input type="text" name="license_key" placeholder="Enter your license key" required>
                <button type="submit">Verify</button>
            </form>
            {% if error %}
                <div class="error">{{ error }}</div>
            {% endif %}
            {% if success %}
                <div class="success">{{ success }}</div>
            {% endif %}
        {% else %}
            <h1>🔒 Premium Access</h1>
            <p>Login with Discord to verify your license</p>
            <a href="{{ login_url }}" class="login-btn">Login with Discord</a>
        {% endif %}
    </div>
</body>
</html>
"""

@flask_app.route("/verify")
def verify_page():
    user = session.get("user")
    if not user:
        params = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "identify guilds.join"
        }
        login_url = "https://discord.com/oauth2/authorize?" + "&".join([f"{k}={v}" for k, v in params.items()])
        return render_template_string(VERIFY_HTML, user=None, login_url=login_url)
    return render_template_string(VERIFY_HTML, user=user, error=None, success=None)

@flask_app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "No code provided", 400
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
    if resp.status_code != 200:
        return "Failed to get token", 400
    token_data = resp.json()
    access_token = token_data["access_token"]
    user_resp = requests.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {access_token}"})
    if user_resp.status_code != 200:
        return "Failed to get user info", 400
    user_data = user_resp.json()
    session["user"] = user_data
    return redirect(url_for("verify_page"))

@flask_app.route("/verify", methods=["POST"])
def verify_license():
    user = session.get("user")
    if not user:
        return redirect(url_for("verify_page"))
    license_key = request.form.get("license_key", "").strip().upper()
    if not license_key:
        return render_template_string(VERIFY_HTML, user=user, error="Please enter a license key.", success=None)
    doc = licenses_col.find_one({"_id": license_key})
    if not doc:
        return render_template_string(VERIFY_HTML, user=user, error="Invalid license key.", success=None)
    if doc["used"]:
        return render_template_string(VERIFY_HTML, user=user, error="This license has already been used.", success=None)
    licenses_col.update_one(
        {"_id": license_key},
        {"$set": {"used": True, "used_by": user["id"], "used_at": datetime.utcnow()}}
    )
    headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
    guild_id = GUILD_ID
    user_id = user["id"]
    role_id = PREMIUM_ROLE_ID
    add_role_url = f"https://discord.com/api/guilds/{guild_id}/members/{user_id}/roles/{role_id}"
    resp = requests.put(add_role_url, headers=headers)
    if resp.status_code in (200, 204):
        success_msg = "✅ License verified! You have been granted the Premium role."
    else:
        success_msg = "⚠️ License verified but role could not be assigned automatically. Please contact staff."
    users_col.insert_one({
        "user_id": user["id"],
        "username": user["username"],
        "license_key": license_key,
        "granted_at": datetime.utcnow()
    })
    return render_template_string(VERIFY_HTML, user=user, error=None, success=success_msg)

def run_flask():
    flask_app.run(host="0.0.0.0", port=10000, debug=False)

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
