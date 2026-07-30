import os
import sys
import secrets
import string
from datetime import datetime
from threading import Thread
from flask import Flask, request, render_template_string
import discord
from discord import app_commands
from discord.ext import commands
import pymongo
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import requests

REQUIRED_ENV = ["DISCORD_TOKEN", "MONGODB_URI", "GUILD_ID", "PREMIUM_ROLE_ID"]
missing = [var for var in REQUIRED_ENV if not os.getenv(var)]
if missing:
    print(f"❌ Missing required environment variables: {', '.join(missing)}")
    print("Please set them and restart.")
    sys.exit(1)

TOKEN = os.getenv("DISCORD_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
GUILD_ID = int(os.getenv("GUILD_ID"))
PREMIUM_ROLE_ID = int(os.getenv("PREMIUM_ROLE_ID"))
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
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Premium License Verification</title>
    <link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap" rel="stylesheet">
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body {
            font-family: 'Press Start 2P', monospace;
            background: #0d0d1a;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 30px;
            color: #e0e0e0;
        }
        .container {
            background: #1a1a2e;
            border: 2px solid #2c3e99;
            border-radius: 20px;
            padding: 45px 35px;
            max-width: 520px;
            width: 100%;
            box-shadow: 0 0 40px rgba(44, 62, 153, 0.4);
            text-align: center;
        }
        .lock-icon {
            font-size: 52px;
            margin-bottom: 12px;
            display: block;
        }
        h1 {
            font-size: 22px;
            color: #2c3e99;
            text-shadow: 0 0 12px #2c3e99;
            letter-spacing: 2px;
            margin-bottom: 10px;
        }
        .sub {
            font-size: 11px;
            color: #8892b0;
            margin-bottom: 35px;
            line-height: 1.8;
        }
        .form-group {
            margin-bottom: 20px;
            text-align: left;
        }
        .form-group label {
            font-size: 10px;
            display: block;
            margin-bottom: 8px;
            color: #8892b0;
            letter-spacing: 1px;
        }
        input {
            width: 100%;
            padding: 14px 16px;
            font-family: 'Press Start 2P', monospace;
            font-size: 14px;
            background: #0f0f23;
            border: 2px solid #2c3e99;
            border-radius: 8px;
            color: #e0e0e0;
            outline: none;
            transition: 0.2s;
            text-align: center;
            letter-spacing: 2px;
        }
        input:focus {
            border-color: #6b8cff;
            box-shadow: 0 0 20px rgba(44, 62, 153, 0.5);
        }
        input.user-id {
            text-align: left;
            letter-spacing: 0;
        }
        button {
            width: 100%;
            padding: 16px;
            margin-top: 8px;
            font-family: 'Press Start 2P', monospace;
            font-size: 14px;
            background: #2c3e99;
            border: none;
            border-radius: 8px;
            color: #fff;
            cursor: pointer;
            transition: 0.2s;
            letter-spacing: 1px;
        }
        button:hover {
            background: #1e2a6b;
            box-shadow: 0 0 20px rgba(44, 62, 153, 0.6);
        }
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .message {
            margin-top: 22px;
            font-size: 11px;
            line-height: 1.6;
            padding: 12px;
            border-radius: 6px;
            display: none;
        }
        .message.error {
            display: block;
            color: #ff6b6b;
            border: 1px solid #ff6b6b;
            background: rgba(255, 107, 107, 0.1);
        }
        .message.success {
            display: block;
            color: #51cf66;
            border: 1px solid #51cf66;
            background: rgba(81, 207, 102, 0.1);
        }
        .footer {
            margin-top: 30px;
            font-size: 8px;
            color: #4a4a6a;
        }
        .loader {
            display: none;
            margin: 12px auto;
            width: 30px;
            height: 30px;
            border: 4px solid #2c3e99;
            border-top-color: #6b8cff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .hint {
            font-size: 8px;
            color: #4a6a8a;
            margin-top: 6px;
            text-align: left;
            padding-left: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <span class="lock-icon">🔒</span>
        <h1>PREMIUM ACCESS</h1>
        <p class="sub">Enter your license key and your Discord User ID<br>to activate premium features.</p>

        <form id="verifyForm" method="POST" action="/verify">
            <div class="form-group">
                <label for="license_key">License Key</label>
                <input type="text" name="license_key" id="license_key" placeholder="LLNNLNNLLN" required autocomplete="off" maxlength="10" style="text-transform:uppercase;">
            </div>
            <div class="form-group">
                <label for="user_id">Discord User ID</label>
                <input type="text" name="user_id" id="user_id" class="user-id" placeholder="123456789012345678" required autocomplete="off">
                <div class="hint">Find your ID by enabling Developer Mode in Discord → Right‑click your profile → Copy ID</div>
            </div>
            <button type="submit" id="submitBtn">ACTIVATE PREMIUM</button>
            <div class="loader" id="loader"></div>
        </form>
        <div id="message" class="message">
            {% if error %}
                <div class="error">{{ error }}</div>
            {% elif success %}
                <div class="success">{{ success }}</div>
            {% endif %}
        </div>
        <div class="footer">© 2026 RblXLua Premium</div>
    </div>

    <script>
        (function() {
            var form = document.getElementById('verifyForm');
            var submitBtn = document.getElementById('submitBtn');
            var loader = document.getElementById('loader');
            var msgDiv = document.getElementById('message');
            var keyInput = document.getElementById('license_key');
            var userIdInput = document.getElementById('user_id');

            if (keyInput) {
                keyInput.addEventListener('input', function() {
                    this.value = this.value.toUpperCase();
                });
            }

            if (form) {
                form.addEventListener('submit', function(e) {
                    loader.style.display = 'block';
                    submitBtn.disabled = true;
                    msgDiv.className = 'message';
                    msgDiv.textContent = '';
                });
            }

            var errorMsg = document.querySelector('.message .error');
            var successMsg = document.querySelector('.message .success');
            if (errorMsg || successMsg) {
                if (msgDiv) {
                    msgDiv.className = 'message ' + (errorMsg ? 'error' : 'success');
                    msgDiv.textContent = errorMsg ? errorMsg.textContent : successMsg.textContent;
                }
            }
        })();
    </script>
</body>
</html>
"""

@flask_app.route("/verify", methods=["GET"])
def verify_page():
    return render_template_string(VERIFY_HTML, error=None, success=None)

@flask_app.route("/verify", methods=["POST"])
def verify_license():
    license_key = request.form.get("license_key", "").strip().upper()
    user_id = request.form.get("user_id", "").strip()

    if not license_key or not user_id:
        return render_template_string(VERIFY_HTML, error="Please fill in all fields.", success=None)

    if not user_id.isdigit():
        return render_template_string(VERIFY_HTML, error="User ID must be a number.", success=None)

    doc = licenses_col.find_one({"_id": license_key})
    if not doc:
        return render_template_string(VERIFY_HTML, error="Invalid license key.", success=None)
    if doc["used"]:
        return render_template_string(VERIFY_HTML, error="This license has already been used.", success=None)

    licenses_col.update_one(
        {"_id": license_key},
        {"$set": {"used": True, "used_by": user_id, "used_at": datetime.utcnow()}}
    )

    headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
    add_role_url = f"https://discord.com/api/guilds/{GUILD_ID}/members/{user_id}/roles/{PREMIUM_ROLE_ID}"
    resp = requests.put(add_role_url, headers=headers)

    users_col.insert_one({
        "user_id": user_id,
        "license_key": license_key,
        "granted_at": datetime.utcnow()
    })

    if resp.status_code in (200, 204):
        success_msg = f"✅ License verified! Premium role granted to <@{user_id}>."
    else:
        success_msg = f"⚠️ License verified but role could not be assigned automatically. Please contact staff. (User ID: {user_id})"

    return render_template_string(VERIFY_HTML, error=None, success=success_msg)

def run_flask():
    flask_app.run(host="0.0.0.0", port=10000, debug=False)

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
