import os
import zipfile

# Files dictionary
files = {
    "requirements.txt": """python-telegram-bot==20.8
python-dotenv==1.0.1
""",
    "Procfile": "worker: python bot.py\n",
    ".env.example": """BOT_TOKEN=your_bot_token_here
OWNER_ID=your_numeric_id_here
OWNER_USERNAME=@your_username
""",
    "README.md": """# Telegram Official Quiz Bot Clone
Full feature Official QuizBot with Leaderboard, Group Contests, and Owner Info.
"""
}

# Create zip
zip_name = "official_quiz_bot.zip"
with zipfile.ZipFile(zip_name, "w") as z:
    for filename, content in files.items():
        z.writestr(filename, content)
    if os.path.exists("bot.py"):
        z.write("bot.py")

print(f"🎉 Success! '{zip_name}' file successfully ban chuki hai!")
