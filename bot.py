import logging
import os
import sqlite3
import json
import csv
import io
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])
CHANNEL_LINK = "https://t.me/orix_global_agency"
DB_PATH = "/data/leads.db"

(Q1, Q2, Q3, Q4, NAME) = range(5)

LEAD_MAGNETS = {
    "topuni":  {"label": "🎓 TOP Universitetlar Qo'llanmasi"},
    "snu":     {"label": "🏛 Seoul National University Qo'llanmasi"},
    "gks":     {"label": "📘 GKS Grant Qo'llanmasi"},
    "topik":   {"label": "📗 TOPIK Tayyorgarlik Qo'llanmasi"},
    "default": {"label": "📖 Bepul Qo'llanma"},
}

QUESTIONS = {
    Q1: {
        "text": "Koreya universitetiga kirishga tayyorgarlikda hozirda qayerdasiz?",
        "options": [
            ("🔹 Sertifikatga hali topshirmaganman", "q1_a"),
            ("🔹 TOPIK yoki IELTS bor, hujjat kerak", "q1_b"),
            ("🔹 Universitet tanlangan, viza/hujjat kerak", "q1_c"),
        ]
    },
    Q2: {
        "text": "Koreya universitetiga hujjat topshirishda sizni eng ko'p nima qiynayapti?",
        "options": [
            ("🔹 Grant yuta olishim mumkinmi?", "q2_a"),
            ("🔹 Hujjat va viza jarayonining to'g'riligi", "q2_b"),
            ("🔹 To'g'ri universitet va yo'nalish tanlash", "q2_c"),
            ("🔹 Til darajam yetarli ekanligini bilmaslik", "q2_d"),
        ]
    },
    Q3: {
        "text": "Koreyadagi o'qishingizdan qanday natijani ideal deb hisoblaysiz?",
        "options": [
            ("🔹 Nufuzli universitet + to'liq grant (GKS)", "q3_a"),
            ("🔹 Grant bo'lmasa ham SKY universitetlari", "q3_b"),
        ]
    },
    Q4: {
        "text": "Universitetni bitirgandan keyin asosiy rejaingiz nima?",
        "options": [
            ("🔹 Koreyada nufuzli kompaniyada ishlash", "q4_a"),
            ("🔹 O'zbekistonga qaytib biznes yoki karyera", "q4_b"),
            ("🔹 O'qish davomida qonuniy ravishda ishlash", "q4_c"),
        ]
    },
}

ANSWER_LABELS = {
    "q1_a": "Sertifikatga hali topshirmaganman",
    "q1_b": "TOPIK/IELTS bor, hujjat kerak",
    "q1_c": "Universitet tanlangan, viza/hujjat kerak",
    "q2_a": "Grant yuta olishim mumkinmi?",
    "q2_b": "Hujjat va viza kafolati",
    "q2_c": "To'g'ri universitet/yo'nalish tanlash",
    "q2_d": "Til darajam yetarliligini bilmaslik",
    "q3_a": "Nufuzli universitet + to'liq grant (GKS)",
    "q3_b": "Grant bo'lmasa ham SKY universitetlari",
    "q4_a": "Koreyada nufuzli kompaniyada ishlash",
    "q4_b": "O'zbekistonga qaytib biznes/karyera",
    "q4_c": "O'qish davomida qonuniy ishlash",
}


# ═══════════════════════════════════════════════════════════════════════════════
# DRIP KETMA-KETLIGI (14+ kunlik, har kishiga o'zi lead bo'lgan kundan boshlab)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Har bir xabar quyidagi ko'rinishda:
#   {"id": "d1m1", "day": 1, "hour": 8, "type": "text", "text": "..."}
#
#   id    — noyob belgi (takrorlanmasin), masalan d1m1 = 1-kun 1-xabar
#   day   — lead bo'lgandan keyin nechinchi kun (1 = birinchi kun)
#   hour  — soat (06–23 oralig'ida). Xabar shu soatdan keyin yuboriladi
#   type  — "text" (matn), "photo" (rasm), "video" (video), "voice" (ovoz), "video_note" (yumaloq)
#   text  — matn (text turida) yoki caption (media turida). Bo'sh bo'lsa "" qoldiring
#   file_id — media uchun Telegram file_id (media turlarida kerak)
#
# HOZIRCHA BO'SH — biz keyin birga to'ldiramiz.
# Namuna sifatida 1 ta xabar qo'yildi, uni o'zgartiring yoki o'chiring.

DRIP_SEQUENCE = [
    # ─── 1-KUN ───
    {"id": "d1m1", "day": 1, "hour": 8,  "type": "text",
     "text": "Assalomu alaykum! 👋 Orix Global jamoasiga xush kelibsiz. Keyingi kunlarda Koreyaga o'qishga kirish bo'yicha eng foydali maslahatlarni ulashamiz."},
    # {"id": "d1m2", "day": 1, "hour": 13, "type": "text", "text": "..."},
    # {"id": "d1m3", "day": 1, "hour": 19, "type": "text", "text": "..."},

    # ─── 2-KUN ───
    # {"id": "d2m1", "day": 2, "hour": 8,  "type": "text", "text": "..."},

    # ... 14 kungacha davom etadi (biz birga to'ldiramiz)
]


# ─── Database ──────────────────────────────────────────────────────────────────

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            name TEXT,
            answers TEXT,
            lead_magnet TEXT DEFAULT 'default',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS starts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            username TEXT,
            lead_magnet TEXT DEFAULT 'default',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    # Drip: har bir foydalanuvchiga qaysi xabar yuborilganini kuzatadi
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drip_sent (
            telegram_id INTEGER,
            step_id TEXT,
            sent_at TEXT DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (telegram_id, step_id)
        )
    """)
    # Drip boshlanish vaqti (lead bo'lgan payt)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drip_users (
            telegram_id INTEGER PRIMARY KEY,
            started_at TEXT DEFAULT (datetime('now','localtime')),
            active INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()


def record_start(telegram_id, username, lead_magnet):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO starts (telegram_id, username, lead_magnet) VALUES (?, ?, ?)",
        (telegram_id, username or "", lead_magnet)
    )
    conn.commit()
    conn.close()


def save_lead(telegram_id, username, name, answers, lead_magnet):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO leads (telegram_id, username, name, answers, lead_magnet)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username=excluded.username,
            name=excluded.name,
            answers=excluded.answers,
            lead_magnet=excluded.lead_magnet,
            created_at=datetime('now','localtime')
    """, (telegram_id, username or "", name, json.dumps(answers, ensure_ascii=False), lead_magnet))
    conn.commit()
    conn.close()


def get_incomplete_users():
    """
    /start bosgan, lekin so'rovnomani YAKUNLAMAGAN foydalanuvchilar.
    Ya'ni starts da bor, lekin leads da yo'q.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT DISTINCT telegram_id FROM starts
        WHERE telegram_id NOT IN (SELECT telegram_id FROM leads)
    """).fetchall()
    conn.close()
    return [row[0] for row in rows if row[0]]


def get_all_user_ids():
    """
    /start bosgan HAMMA foydalanuvchi (yarim yo'lda to'xtaganlar ham).
    starts va leads jadvallaridan telegram_id lar, takrorlanmasdan.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT telegram_id FROM starts
        UNION
        SELECT telegram_id FROM leads
    """).fetchall()
    conn.close()
    return [row[0] for row in rows if row[0]]


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    total_leads  = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    today_leads  = conn.execute(
        "SELECT COUNT(*) FROM leads WHERE DATE(created_at) = DATE('now','localtime')"
    ).fetchone()[0]
    total_starts = conn.execute("SELECT COUNT(*) FROM starts").fetchone()[0]
    today_starts = conn.execute(
        "SELECT COUNT(*) FROM starts WHERE DATE(created_at) = DATE('now','localtime')"
    ).fetchone()[0]
    by_magnet = conn.execute(
        "SELECT lead_magnet, COUNT(*) FROM starts GROUP BY lead_magnet ORDER BY COUNT(*) DESC"
    ).fetchall()
    by_magnet_leads = conn.execute(
        "SELECT lead_magnet, COUNT(*) FROM leads GROUP BY lead_magnet ORDER BY COUNT(*) DESC"
    ).fetchall()
    conversion = round(total_leads / total_starts * 100, 1) if total_starts > 0 else 0
    conn.close()
    return total_leads, today_leads, total_starts, today_starts, by_magnet, by_magnet_leads, conversion


def get_recent_leads(limit=20):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT name, username, lead_magnet, created_at FROM leads ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


def get_all_leads_csv():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, name, username, telegram_id, lead_magnet, answers, created_at FROM leads ORDER BY id DESC"
    ).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Ism", "Username", "TG ID", "Segment", "Javoblar", "Sana"])
    for row in rows:
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")


def get_usernames():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT username, name, lead_magnet, created_at FROM leads "
        "WHERE username IS NOT NULL AND username != '' ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return rows


def get_keyboard(options):
    return InlineKeyboardMarkup([[InlineKeyboardButton(l, callback_data=d)] for l, d in options])


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_CHAT_ID


# ─── Drip funksiyalari ──────────────────────────────────────────────────────────

def drip_start_user(telegram_id):
    """Foydalanuvchini drip ketma-ketligiga qo'shadi (lead bo'lganda chaqiriladi)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO drip_users (telegram_id) VALUES (?)",
        (telegram_id,)
    )
    conn.commit()
    conn.close()


def drip_get_active_users():
    """Drip faol bo'lgan foydalanuvchilar: (telegram_id, started_at)."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT telegram_id, started_at FROM drip_users WHERE active = 1"
    ).fetchall()
    conn.close()
    return rows


def drip_already_sent(telegram_id, step_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT 1 FROM drip_sent WHERE telegram_id = ? AND step_id = ?",
        (telegram_id, step_id)
    ).fetchone()
    conn.close()
    return row is not None


def drip_mark_sent(telegram_id, step_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO drip_sent (telegram_id, step_id) VALUES (?, ?)",
        (telegram_id, step_id)
    )
    conn.commit()
    conn.close()


def drip_stop_user(telegram_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE drip_users SET active = 0 WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()


# ─── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["answers"] = {}

    lead_magnet = "default"
    if context.args:
        slug = context.args[0].lower()
        if slug in LEAD_MAGNETS:
            lead_magnet = slug
    context.user_data["lead_magnet"] = lead_magnet

    user = update.effective_user
    record_start(user.id, user.username, lead_magnet)

    video_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "welcome.mp4")
    try:
        with open(video_path, "rb") as vf:
            await update.message.reply_video_note(video_note=vf)
    except Exception as e:
        logger.warning(f"Video yuborishda xatolik: {e}")
        await update.message.reply_text(
            "🇰🇷 Xush kelibsiz!\n\nBir necha savol — 1 daqiqa vaqt oladi. Boshlaylik! 👇"
        )

    q = QUESTIONS[Q1]
    await update.message.reply_text(q["text"], reply_markup=get_keyboard(q["options"]))
    return Q1


async def resume_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Eslatma tugmasi bosilganda so'rovnomani boshlaydi."""
    query = update.callback_query
    await query.answer()

    context.user_data.clear()
    context.user_data["answers"] = {}
    context.user_data["lead_magnet"] = "default"

    user = update.effective_user
    record_start(user.id, user.username, "default")

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    q = QUESTIONS[Q1]
    await query.message.reply_text("Zo'r! Boshlaymiz 👇")
    await query.message.reply_text(q["text"], reply_markup=get_keyboard(q["options"]))
    return Q1


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, next_state, next_q_key=None):
    query = update.callback_query
    await query.answer()
    context.user_data["answers"][query.data.split("_")[0]] = query.data

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if next_q_key is not None:
        q = QUESTIONS[next_q_key]
        await query.message.reply_text(q["text"], reply_markup=get_keyboard(q["options"]))
        return next_state

    await query.message.reply_text("Zo'r! Oxirgi savol — ismingizni kiriting ✍️")
    return NAME


async def q1_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_answer(update, context, Q2, Q2)

async def q2_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_answer(update, context, Q3, Q3)

async def q3_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_answer(update, context, Q4, Q4)

async def q4_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_answer(update, context, NAME, None)


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("❗ To'liq ismingizni kiriting, iltimos.")
        return NAME
    context.user_data["name"] = name

    user = update.effective_user
    data = context.user_data
    lead_magnet = data.get("lead_magnet", "default")
    answers = data.get("answers", {})

    answers_text = ""
    for q_key, ans_key in sorted(answers.items()):
        label = ANSWER_LABELS.get(ans_key, ans_key)
        answers_text += f"  {q_key.upper()}: {label}\n"

    tg_link = f"@{user.username}" if user.username else f"ID: {user.id}"
    lm_label = LEAD_MAGNETS.get(lead_magnet, LEAD_MAGNETS["default"])["label"]

    admin_msg = (
        f"🆕 *YANGI LEAD*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Ism:* {name}\n"
        f"🔗 *Telegram:* {tg_link}\n"
        f"🎯 *Segment:* {lm_label}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📋 *Javoblar:*\n{answers_text}"
    )

    try:
        save_lead(user.id, user.username, name, answers, lead_magnet)
        drip_start_user(user.id)  # Drip ketma-ketligini boshlash
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg, parse_mode="Markdown")
        logger.info(f"Lead saqlandi: {name} / {tg_link} / {lead_magnet}")
    except Exception as e:
        logger.error(f"Lead saqlashda xatolik: {e}")

    final_msg = (
        f"🎉 Rahmat, {name}!\n\n"
        "So'rovnomani muvaffaqiyatli yakunladingiz.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📌 Va'da qilingan qo'llanma kanalimizda PIN xabarda joylashtirilgan.\n\n"
        f"👉 Kanalga o'tish va qo'llanmani olish: {CHANNEL_LINK}\n\n"
        "Kanalda siz uchun:\n"
        "• 📖 Bepul qo'llanma — PIN xabarda\n"
        "• 🎓 O'zbek talabalar tajribalari\n"
        "• 💰 GKS grant yangiliklari\n"
        "• 📋 Hujjat topshirish bo'yicha bepul materiallar"
    )
    await update.message.reply_text(final_msg)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("So'rovnoma to'xtatildi. Qayta boshlash uchun /start ni bosing.")
    return ConversationHandler.END


# ─── Admin ─────────────────────────────────────────────────────────────────────

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text(
            "❗ Xabar matni kiriting.\n\nMisol:\n/broadcast Salom! Yangi vebinar bo'ladi..."
        )
        return

    text = " ".join(context.args)
    user_ids = get_all_user_ids()

    if not user_ids:
        await update.message.reply_text("Hali hech qanday foydalanuvchi yo'q.")
        return

    status_msg = await update.message.reply_text(f"📤 {len(user_ids)} ta foydalanuvchiga yuborilmoqda...")

    success = 0
    failed = 0
    for user_id in user_ids:
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.warning(f"Xabar yuborilmadi {user_id}: {e}")

    await status_msg.edit_text(
        f"✅ Broadcast tugadi!\n\n"
        f"📨 Yuborildi: {success} ta\n"
        f"❌ Yuborilmadi: {failed} ta"
    )


async def cmd_broadcast_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yumaloq videoga reply qilib /broadcast_video — hammaga yuboradi."""
    if not is_admin(update.effective_user.id):
        return
    reply = update.message.reply_to_message
    if not reply or not reply.video_note:
        await update.message.reply_text(
            "❗ Yumaloq videoga REPLY qilib /broadcast_video yozing.\n\n"
            "Ya'ni: avval yumaloq videoni botga yuboring, keyin o'sha videoga "
            "reply qilib bu buyruqni yozing."
        )
        return

    file_id = reply.video_note.file_id
    user_ids = get_all_user_ids()
    if not user_ids:
        await update.message.reply_text("Hali hech qanday foydalanuvchi yo'q.")
        return

    status = await update.message.reply_text(f"📤 Yumaloq video {len(user_ids)} ta odamga yuborilmoqda...")
    success = failed = 0
    for uid in user_ids:
        try:
            await context.bot.send_video_note(chat_id=uid, video_note=file_id)
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.warning(f"Video yuborilmadi {uid}: {e}")
    await status.edit_text(f"✅ Video yuborildi!\n\n📨 Yuborildi: {success} ta\n❌ Yuborilmadi: {failed} ta")


async def cmd_broadcast_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ovozli xabarga reply qilib /broadcast_voice — hammaga yuboradi."""
    if not is_admin(update.effective_user.id):
        return
    reply = update.message.reply_to_message
    if not reply or not reply.voice:
        await update.message.reply_text(
            "❗ Ovozli xabarga REPLY qilib /broadcast_voice yozing.\n\n"
            "Ya'ni: avval ovozli xabarni botga yuboring, keyin o'sha xabarga "
            "reply qilib bu buyruqni yozing."
        )
        return

    file_id = reply.voice.file_id
    user_ids = get_all_user_ids()
    if not user_ids:
        await update.message.reply_text("Hali hech qanday foydalanuvchi yo'q.")
        return

    status = await update.message.reply_text(f"📤 Ovozli xabar {len(user_ids)} ta odamga yuborilmoqda...")
    success = failed = 0
    for uid in user_ids:
        try:
            await context.bot.send_voice(chat_id=uid, voice=file_id)
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.warning(f"Ovoz yuborilmadi {uid}: {e}")
    await status.edit_text(f"✅ Ovozli xabar yuborildi!\n\n📨 Yuborildi: {success} ta\n❌ Yuborilmadi: {failed} ta")


async def drip_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Har 15 daqiqada ishlaydi. Har bir faol drip foydalanuvchisi uchun
    vaqti kelgan (lekin hali yuborilmagan) xabarlarni yuboradi.
    Faqat 06:00–23:00 oralig'ida yuboradi.
    """
    now = datetime.now()
    if now.hour < 6 or now.hour >= 23:
        return  # tungi vaqtda yubormaymiz

    if not DRIP_SEQUENCE:
        return

    users = drip_get_active_users()
    for telegram_id, started_at in users:
        try:
            started = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue

        elapsed_days = (now.date() - started.date()).days + 1  # 1-kun = lead bo'lgan kun

        for step in DRIP_SEQUENCE:
            if step["day"] != elapsed_days:
                continue
            if now.hour < step["hour"]:
                continue  # hali vaqti kelmagan
            if drip_already_sent(telegram_id, step["id"]):
                continue

            try:
                t = step.get("type", "text")
                if t == "text":
                    await context.bot.send_message(chat_id=telegram_id, text=step["text"])
                elif t == "photo":
                    await context.bot.send_photo(chat_id=telegram_id, photo=step["file_id"], caption=step.get("text", ""))
                elif t == "video":
                    await context.bot.send_video(chat_id=telegram_id, video=step["file_id"], caption=step.get("text", ""))
                elif t == "voice":
                    await context.bot.send_voice(chat_id=telegram_id, voice=step["file_id"])
                elif t == "video_note":
                    await context.bot.send_video_note(chat_id=telegram_id, video_note=step["file_id"])

                drip_mark_sent(telegram_id, step["id"])
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"Drip yuborilmadi {telegram_id} / {step['id']}: {e}")
                # Bot bloklangan bo'lsa, keyingi urinishlarni to'xtatish
                if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                    drip_stop_user(telegram_id)
                    break


async def cmd_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Yarim yo'lda to'xtaganlarga (start bosgan, lekin yakunlamagan) tugmali eslatma yuboradi.
    """
    if not is_admin(update.effective_user.id):
        return

    user_ids = get_incomplete_users()
    if not user_ids:
        await update.message.reply_text("Yarim yo'lda to'xtagan foydalanuvchi yo'q.")
        return

    text = (
        "📢 Qo'llanmangizni olishga bir qadam qoldi!\n\n"
        "Bepul qo'llanmani olish uchun atigi 4 ta savolga javob berishingiz kerak. "
        "Bu 1 daqiqa vaqt oladi.\n\n"
        "Hoziroq yakunlang 👇"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Savollarga javob berish", callback_data="resume_survey")
    ]])

    status = await update.message.reply_text(f"📤 Eslatma {len(user_ids)} ta odamga yuborilmoqda...")
    success = failed = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=text, reply_markup=keyboard)
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.warning(f"Eslatma yuborilmadi {uid}: {e}")
    await status.edit_text(f"✅ Eslatma yuborildi!\n\n📨 Yuborildi: {success} ta\n❌ Yuborilmadi: {failed} ta")


async def cmd_import_leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Eski leadlarni CSV dan tiklaydi.
    Ishlatilishi: CSV faylni botga yuboring, keyin unga reply qilib /import_leads yozing.
    CSV formati: ID, Ism, Username, TG ID, Segment, Javoblar, Sana
    """
    if not is_admin(update.effective_user.id):
        return

    reply = update.message.reply_to_message
    if not reply or not reply.document:
        await update.message.reply_text(
            "❗ CSV faylga REPLY qilib /import_leads yozing.\n\n"
            "Ya'ni: avval CSV faylni botga yuboring, keyin o'sha faylga "
            "reply qilib bu buyruqni yozing."
        )
        return

    status = await update.message.reply_text("📥 CSV yuklab olinmoqda...")

    try:
        tg_file = await reply.document.get_file()
        file_bytes = await tg_file.download_as_bytearray()
        text = file_bytes.decode("utf-8-sig")
    except Exception as e:
        await status.edit_text(f"❌ Faylni o'qishda xatolik: {e}")
        return

    added = 0
    skipped = 0
    conn = sqlite3.connect(DB_PATH)
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        tg = (row.get("TG ID") or "").strip()
        if not tg.isdigit():
            skipped += 1
            continue
        telegram_id = int(tg)
        name = (row.get("Ism") or "").strip()
        username = (row.get("Username") or "").strip()
        answers = (row.get("Javoblar") or "{}").strip()
        segment = (row.get("Segment") or "default").strip()
        created = (row.get("Sana") or "").strip()

        try:
            # Lead qo'shish (bor bo'lsa tegilmaydi)
            conn.execute("""
                INSERT OR IGNORE INTO leads (telegram_id, username, name, answers, lead_magnet, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (telegram_id, username, name, answers, segment, created or None))
            # Drip ga ham qo'shish (eski leadlar drip olmasin uchun active=0)
            conn.execute("""
                INSERT OR IGNORE INTO drip_users (telegram_id, active) VALUES (?, 0)
            """, (telegram_id,))
            added += 1
        except Exception as e:
            logger.warning(f"Import xatolik {telegram_id}: {e}")
            skipped += 1

    conn.commit()
    conn.close()

    await status.edit_text(
        f"✅ Import tugadi!\n\n"
        f"📥 Qo'shildi: {added} ta\n"
        f"⏭ O'tkazib yuborildi: {skipped} ta\n\n"
        f"Endi /broadcast bilan hammaga xabar yubora olasiz."
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    total_leads, today_leads, total_starts, today_starts, by_magnet, by_magnet_leads, conversion = get_stats()
    start_lines = "".join(
        f"  • {LEAD_MAGNETS.get(m, LEAD_MAGNETS['default'])['label']}: *{c}* ta\n"
        for m, c in by_magnet
    )
    lead_lines = "".join(
        f"  • {LEAD_MAGNETS.get(m, LEAD_MAGNETS['default'])['label']}: *{c}* ta\n"
        for m, c in by_magnet_leads
    )
    empty = "  Hali yo'q"
    msg = (
        f"📊 *Statistika*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👆 /start bosildi: *{total_starts}* ta _(bugun: {today_starts})_\n"
        f"📥 Leadlar: *{total_leads}* ta _(bugun: {today_leads})_\n"
        f"📈 Konversiya: *{conversion}%*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 *Segment bo'yicha (start):*\n{start_lines or empty}\n"
        f"📥 *Segment bo'yicha (lead):*\n{lead_lines or empty}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    rows = get_recent_leads(20)
    if not rows:
        await update.message.reply_text("Hali hech qanday lead yo'q.")
        return
    lines = []
    for i, (name, username, lead_magnet, created_at) in enumerate(rows, 1):
        tg = f"@{username}" if username else "—"
        date = created_at[:10] if created_at else "—"
        seg = LEAD_MAGNETS.get(lead_magnet, LEAD_MAGNETS["default"])["label"].split()[1]
        lines.append(f"{i}. {name} | {tg} | {seg} | {date}")
    await update.message.reply_text("📋 So'nggi 20 lead:\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines))


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    csv_bytes = get_all_leads_csv()
    now = datetime.now().strftime("%Y%m%d_%H%M")
    await update.message.reply_document(
        document=csv_bytes,
        filename=f"leads_{now}.csv",
        caption=f"📂 Barcha leadlar — {now}"
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    me = await context.bot.get_me()
    base = f"https://t.me/{me.username}?start="
    msg = (
        "🛠 *Admin panel:*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "/stats — Statistika\n"
        "/leads — So'nggi 20 lead\n"
        "/export — CSV yuklab olish\n"
        "/broadcast [matn] — Hammaga matn\n"
        "/broadcast_video — Yumaloq video (reply)\n"
        "/broadcast_voice — Ovozli xabar (reply)\n"
        "/reminder — Yarim yo'lda to'xtaganlarga eslatma\n"
        "/import_leads — CSV dan lead tiklash (reply)\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "*Deep linklar:*\n\n"
        f"🎓 TOP Universitetlar:\n`{base}topuni`\n\n"
        f"🏛 Seoul National:\n`{base}snu`\n\n"
        f"📘 GKS Grant:\n`{base}gks`\n\n"
        f"📗 TOPIK:\n`{base}topik`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(resume_survey, pattern="^resume_survey$"),
        ],
        states={
            Q1:   [CallbackQueryHandler(q1_handler, pattern="^q1_")],
            Q2:   [CallbackQueryHandler(q2_handler, pattern="^q2_")],
            Q3:   [CallbackQueryHandler(q3_handler, pattern="^q3_")],
            Q4:   [CallbackQueryHandler(q4_handler, pattern="^q4_")],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("admin",           cmd_admin))
    app.add_handler(CommandHandler("stats",           cmd_stats))
    app.add_handler(CommandHandler("leads",           cmd_leads))
    app.add_handler(CommandHandler("export",          cmd_export))
    app.add_handler(CommandHandler("broadcast",       cmd_broadcast))
    app.add_handler(CommandHandler("broadcast_video", cmd_broadcast_video))
    app.add_handler(CommandHandler("broadcast_voice", cmd_broadcast_voice))
    app.add_handler(CommandHandler("import_leads",    cmd_import_leads))
    app.add_handler(CommandHandler("reminder",        cmd_reminder))

    # Drip: har 15 daqiqada tekshirib, vaqti kelgan xabarlarni yuboradi
    app.job_queue.run_repeating(drip_job, interval=900, first=30)

    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
