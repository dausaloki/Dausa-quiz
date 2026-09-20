import os
import json
import asyncio
import sqlite3
import logging
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Poll,
)
from telegram.constants import PollType, ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    PollAnswerHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

load_dotenv()

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# CONFIGURATION
BOT_TOKEN = os.getenv("BOT_TOKEN", "AAPKA_BOT_TOKEN_HERE")
OWNER_ID = os.getenv("OWNER_ID", "123456789")  # Aapki Telegram Numeric ID
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@AapkaUsername")  # Aapka Username

# DATABASE SETUP (SQLite)
def init_db():
    conn = sqlite3.connect("quizbot.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            description TEXT,
            timer INTEGER DEFAULT 15
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id INTEGER,
            question TEXT,
            options TEXT,
            correct_option_id INTEGER,
            explanation TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# State definitions for ConversationHandler
TITLE, DESC, QUESTIONS_STATE, TIMER = range(4)

# Global active games tracker: {chat_id: game_instance}
ACTIVE_GAMES = {}

# ==================== OWNER BRANDING HELPER ====================
def get_owner_banner():
    return (
        f"\n━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 **Official Bot Owner:**\n"
        f"🆔 **ID:** `{OWNER_ID}`\n"
        f"👤 **Username:** {OWNER_USERNAME}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

# ==================== BASIC COMMANDS ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    # Agar user kisi quiz link ke through aaya ho: /start quiz_123
    if args and args[0].startswith("quiz_"):
        quiz_id = args[0].split("_")[1]
        await start_quiz_in_chat(update.effective_chat.id, int(quiz_id), context)
        return

    text = (
        f"👋 Namaste **{user.first_name}**!\n\n"
        f"Main Telegram ka **Official Style Quiz Contest Bot** hoon.\n\n"
        f"📌 **Aap kya kar sakte hain?**\n"
        f"🔹 /newquiz - Naya quiz banayein\n"
        f"🔹 /myquizzes - Apne banaye huye quizzes dekhein\n"
        f"🔹 /help - Bot use karne ka tarika\n"
        f"{get_owner_banner()}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# Group me bot add hone par Welcome message + Owner ID
async def on_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            chat = update.effective_chat
            text = (
                f"🎉 Dhanyawad mujhe **{chat.title}** me add karne ke liye!\n\n"
                f"Main yahan live quizzes host kar sakta hoon leaderboard ke sath.\n"
                f"Quiz shuru karne ke liye `/myquizzes` use karein ya link share karein.\n"
                f"{get_owner_banner()}"
            )
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ==================== QUIZ CREATION FLOW ====================
async def newquiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("❌ Quiz sirf Bot ke private chat me create kiya ja sakta hai!")
        return ConversationHandler.END

    await update.message.reply_text(
        "📝 **Naya Quiz Banayein**\n\nKripya apne Quiz ka **Title (Naam)** bhejein:",
        parse_mode=ParseMode.MARKDOWN
    )
    return TITLE

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["quiz_title"] = update.message.text
    await update.message.reply_text(
        "📄 Ab is quiz ka ek chhota **Description (Vivaran)** bhejein (ya `/skip` karein):"
    )
    return DESC

async def receive_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data["quiz_desc"] = "" if text == "/skip" else text
    context.user_data["questions"] = []

    await update.message.reply_text(
        "🎯 **Ab Sawal Bhejiye!**\n\n"
        "Aapko Telegram ke Poll option ka use karke **Quiz Mode** me poll create karke yahan send karna hai.\n\n"
        "Jab aapke saare questions complete ho jayein, toh `/done` type karein.",
        parse_mode=ParseMode.MARKDOWN
    )
    return QUESTIONS_STATE

async def receive_question_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message.poll:
        await message.reply_text("⚠️ Kripya valid Telegram Poll (Quiz type) send karein, ya `/done` likhein.")
        return QUESTIONS_STATE

    poll = message.poll
    if poll.type != PollType.QUIZ:
        await message.reply_text("⚠️ Yeh normal poll hai! Kripya 'Quiz Mode' poll bhejein jisme sahi jawab selected ho.")
        return QUESTIONS_STATE

    q_data = {
        "question": poll.question,
        "options": [opt.text for opt in poll.options],
        "correct_option_id": poll.correct_option_id,
        "explanation": poll.explanation or ""
    }
    context.user_data["questions"].append(q_data)
    count = len(context.user_data["questions"])
    await message.reply_text(f"✅ Question #{count} save ho gaya! Agla question bhejein ya finish karne ke liye `/done` likhein.")
    return QUESTIONS_STATE

async def done_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("questions"):
        await update.message.reply_text("❌ Aapne ek bhi question add nahi kiya! `/newquiz` dubara karein.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("10 Sec", callback_data="t_10"), InlineKeyboardButton("15 Sec", callback_data="t_15")],
        [InlineKeyboardButton("30 Sec", callback_data="t_30"), InlineKeyboardButton("60 Sec", callback_data="t_60")]
    ]
    await update.message.reply_text(
        "⏱ **Har sawal ke liye kitna time dena chahte hain?**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    return TIMER

async def receive_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    timer_val = int(query.data.split("_")[1])
    user_id = query.from_user.id
    title = context.user_data["quiz_title"]
    desc = context.user_data["quiz_desc"]
    questions = context.user_data["questions"]

    # Save to SQLite DB
    conn = sqlite3.connect("quizbot.db")
    c = conn.cursor()
    c.execute("INSERT INTO quizzes (user_id, title, description, timer) VALUES (?, ?, ?, ?)",
              (user_id, title, desc, timer_val))
    quiz_id = c.lastrowid

    for q in questions:
        c.execute(
            "INSERT INTO questions (quiz_id, question, options, correct_option_id, explanation) VALUES (?, ?, ?, ?, ?)",
            (quiz_id, q["question"], json.dumps(q["options"]), q["correct_option_id"], q["explanation"])
        )
    conn.commit()
    conn.close()

    bot_username = (await context.bot.get_me()).username
    share_url = f"https://t.me/{bot_username}?start=quiz_{quiz_id}"

    await query.edit_message_text(
        f"🎉 **Quiz Safaltapoorvak Ban Gaya!**\n\n"
        f"📌 **Title:** {title}\n"
        f"❓ **Total Questions:** {len(questions)}\n"
        f"⏱ **Timer:** {timer_val} seconds\n\n"
        f"🔗 **Quiz Link:**\n`{share_url}`\n\n"
        f"Ise kisi bhi group me paste karke ya forward karke khel sakte hain!"
        f"{get_owner_banner()}",
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Quiz creation cancel kar diya gaya.")
    return ConversationHandler.END

# ==================== QUIZ RUNNER & LEADERBOARD ====================
async def myquizzes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect("quizbot.db")
    c = conn.cursor()
    c.execute("SELECT id, title FROM quizzes WHERE user_id = ?", (user_id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Aapne abhi tak koi quiz nahi banaya. Banane ke liye `/newquiz` likhein.")
        return

    text = "📚 **Aapke Banaye Huye Quizzes:**\n\n"
    for r in rows:
        text += f"🔹 **ID {r[0]}:** {r[1]} -> /play_{r[0]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def play_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Command format: /play_123
    text = update.message.text
    if "_" in text:
        try:
            quiz_id = int(text.split("_")[1])
            await start_quiz_in_chat(update.effective_chat.id, quiz_id, context)
        except Exception as e:
            logger.error(f"Error: {e}")
            await update.message.reply_text("❌ Invalid Quiz ID.")

async def start_quiz_in_chat(chat_id, quiz_id, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("quizbot.db")
    c = conn.cursor()
    c.execute("SELECT title, timer FROM quizzes WHERE id = ?", (quiz_id,))
    quiz_data = c.fetchone()

    if not quiz_data:
        await context.bot.send_message(chat_id, "❌ Yeh Quiz exist nahi karta!")
        conn.close()
        return

    title, timer = quiz_data
    c.execute("SELECT question, options, correct_option_id, explanation FROM questions WHERE quiz_id = ?", (quiz_id,))
    questions = c.fetchall()
    conn.close()

    if not questions:
        await context.bot.send_message(chat_id, "❌ Is quiz me koi questions nahi hain.")
        return

    await context.bot.send_message(
        chat_id,
        f"🏁 **Quiz Shuru Hone Wala Hai!**\n\n"
        f"📖 **Title:** {title}\n"
        f"❓ **Total Questions:** {len(questions)}\n"
        f"⏱ **Time Per Question:** {timer}s\n\n"
        f"Ready ho jayein! Quiz agle 5 seconds me shuru hoga... 🔥",
        parse_mode=ParseMode.MARKDOWN
    )

    await asyncio.sleep(5)

    scores = {}  # {user_id: {"name": str, "score": int}}

    for idx, q in enumerate(questions, 1):
        q_text, opts_json, correct_id, explanation = q
        options = json.loads(opts_json)

        poll_msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"[{idx}/{len(questions)}] {q_text}",
            options=options,
            type=PollType.QUIZ,
            correct_option_id=correct_id,
            explanation=explanation,
            is_anonymous=False,
            open_period=timer
        )

        # Poll ID register karna score calculate karne ke liye
        context.bot_data[poll_msg.poll.id] = {
            "correct_id": correct_id,
            "scores": scores
        }

        await asyncio.sleep(timer + 1)

    # FINAL LEADERBOARD
    leaderboard = f"🏆 **QUIZ SAMAPT (RESULTS)!** 🏆\n\n📖 **Quiz:** {title}\n\n"
    if not scores:
        leaderboard += "Kisi ne bhi sahi jawab nahi diya ya kisi ne participate nahi kiya. 😴\n"
    else:
        sorted_scores = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
        medals = ["🥇", "🥈", "🥉"]
        for rank, user in enumerate(sorted_scores, 1):
            tag = medals[rank - 1] if rank <= 3 else f"{rank}."
            leaderboard += f"{tag} **{user['name']}** — {user['score']} pts\n"

    leaderboard += f"\nThank you for playing!{get_owner_banner()}"
    await context.bot.send_message(chat_id, leaderboard, parse_mode=ParseMode.MARKDOWN)

# Track who answered correctly
async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id

    if poll_id in context.bot_data:
        poll_info = context.bot_data[poll_id]
        if answer.option_ids and answer.option_ids[0] == poll_info["correct_id"]:
            user = answer.user
            uid = user.id
            scores = poll_info["scores"]
            if uid not in scores:
                scores[uid] = {"name": user.first_name, "score": 0}
            scores[uid]["score"] += 1

def main():
    if not BOT_TOKEN or BOT_TOKEN == "AAPKA_BOT_TOKEN_HERE":
        print("❌ Error: BOT_TOKEN sahi set nahi hai!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Quiz creation conversation
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("newquiz", newquiz_command)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)],
            DESC: [MessageHandler(filters.TEXT, receive_desc)],
            QUESTIONS_STATE: [
                MessageHandler(filters.POLL, receive_question_poll),
                CommandHandler("done", done_questions),
            ],
            TIMER: [CallbackQueryHandler(receive_timer, pattern="^t_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("myquizzes", myquizzes))
    app.add_handler(MessageHandler(filters.Regex(r"^/play_\d+"), play_command_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added))
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    print("✅ Official Telegram Quiz Bot is Live!")
    app.run_polling()

if __name__ == "__main__":
    from telegram.ext import CallbackQueryHandler
    main()
