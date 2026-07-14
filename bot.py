import logging
import os
import sqlite3
import json
import csv
import io
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, RetryAfter, TimedOut, NetworkError
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
# DRIP KETMA-KETLIGI — 14 kunlik, segmentli
# ═══════════════════════════════════════════════════════════════════════════════
# Qoidalar: 4-8 qisqa jumla | BITTA CTA | kam emoji | aniq raqam | har kuni yangi fikr
#
# segment: "all" | "seen" | "not_seen" | "no_answer" | "admin"
# type:    "text" | "text_button" | "admin_note"

GUIDE_1 = "https://t.me/orix_global_agency/634"   # TOP 10 talaba qo'llanmasi
GUIDE_2 = "https://t.me/orix_global_agency/622"   # Universitetlar qo'llanmasi
ADMIN_USERNAME = "@Orix_Global_admin"
CHANNEL = "https://t.me/orix_global_agency"

DRIP_SEQUENCE = [

    # ══════════════ 1-KUN ══════════════
    {"id": "d1m1", "day": 1, "hour": 8, "segment": "all", "type": "text_button",
     "text": (
        "Salom! Siz bizdan Koreya TOP universitetlariga kirish bo'yicha qo'llanma olgan edingiz.\n"
        "\n"
        "Ochiq gapiramiz: qo'llanmani olgan har 10 kishidan 7 tasi uni ochib ham ko'rmaydi. Keyin esa \"menda imkoniyat yo'q ekan\" deb xulosa qiladi.\n"
        "\n"
        "Ichida 10 ta talabamizning aniq yo'li bor — qanday GPA, qanday IELTS, qaysi universitet, qanday hujjat.\n"
        "\n"
        "Qo'llanmani ko'rib chiqdingizmi?"
     ),
     "buttons": [("Ha, ko'rdim", "guide_seen"), ("Hali ko'rmadim", "guide_not_seen")]},

    {"id": "d1m2", "day": 1, "hour": 19, "segment": "no_answer", "type": "text_button",
     "text": (
        "Bitta raqam aytamiz.\n"
        "\n"
        "TOP universitetga kirgan 10 ta talabamizning 7 tasida TOPIK sertifikati yo'q edi. Faqat IELTS bilan topshirdi. Eng pasti — 6.5.\n"
        "\n"
        "Ya'ni koreys tilini bilmasdan ham TOP universitetga kirish mumkin. Ko'pchilik buni bilmaydi.\n"
        "\n"
        "Qo'llanmani oching — har birining aniq ko'rsatkichi jadvalda."
     ),
     "buttons": [("Ko'rdim", "guide_seen"), ("Hali ko'rmadim", "guide_not_seen")]},

    # ══════════════ 2-KUN ══════════════
    {"id": "d2m1s", "day": 2, "hour": 9, "segment": "seen", "type": "text",
     "text": (
        "Qo'llanmani ko'rgan ekansiz. Endi savol.\n"
        "\n"
        "Jadvaldagi 10 ta talabaning hammasida GPA 4.2 dan yuqori edi. Eng pasti — Abdullayev Karamatillo, GPA 4.2, Hanyang University.\n"
        "\n"
        "Sizning GPA ingiz qancha?\n"
        "\n"
        "Agar 4.2 dan past bo'lsa — bu tugadi degani emas. Buni qoplashning yo'llari bor.\n"
        "\n"
        f"Holatingizni yozing: {ADMIN_USERNAME}"
     )},

    {"id": "d2m1n", "day": 2, "hour": 9, "segment": "not_seen", "type": "text",
     "text": (
        "Uch daqiqa vaqt ajrating.\n"
        "\n"
        "Qo'llanmadagi 10 ta talabaning 8 tasi olimpiada g'olibi emas. 7 tasida TOPIK yo'q. 6 tasi IELTS 7.5 dan past ball bilan topshirdi.\n"
        "\n"
        "Lekin 10 tasida ham kuchli motivatsion xat va to'g'ri universitet tanlovi bor edi.\n"
        "\n"
        "Gap ballaringizda emas — strategiyada.\n"
        "\n"
        f"Qo'llanmani oching: {GUIDE_1}"
     )},

    {"id": "d2m2", "day": 2, "hour": 19, "segment": "all", "type": "text",
     "text": (
        "Sungkyunkwan University — qo'llanmadagi 10 ta talabaning 4 tasi shu yerda o'qiydi.\n"
        "\n"
        "Nega aynan shu universitet?\n"
        "\n"
        "Chunki Sungkyunkwan Samsung bilan bevosita hamkorlikda. Koreyada bitiruvchilar ishga joylashish reytingida 1-o'rinda. Xalqaro reytingda esa TOP 87 — ya'ni birinchi o'rin emas.\n"
        "\n"
        "Universitetni reyting bo'yicha emas, maqsad bo'yicha tanlash kerak.\n"
        "\n"
        f"Qaysi universitet qaysi sohada kuchli — ikkinchi qo'llanmada: {GUIDE_2}"
     )},

    # ══════════════ 3-KUN ══════════════
    {"id": "d3m1", "day": 3, "hour": 10, "segment": "all", "type": "text_button",
     "text": (
        "Ikkinchi qo'llanmada Koreyaning TOP universitetlari va ularning kuchli yo'nalishlari bor.\n"
        "\n"
        "Nega bu muhim: KAIST sun'iy intellektda dunyoda TOP 10 da, lekin biznes yo'nalishida o'rtacha. Seoul National tibbiyotda kuchli, lekin IT da Sungkyunkwan undan oldinda.\n"
        "\n"
        "Noto'g'ri universitet tanlasangiz — grant ham, kelajak ham qo'ldan ketadi.\n"
        "\n"
        "Ikkinchi qo'llanmani ko'rdingizmi?"
     ),
     "buttons": [("Ko'rdim", "guide_seen"), ("Hali ko'rmadim", "guide_not_seen")]},

    {"id": "d3m2", "day": 3, "hour": 18, "segment": "all", "type": "text",
     "text": (
        "Mo'ydinova Sahlo — Sungkyunkwan University, Software Engineering.\n"
        "\n"
        "GPA 5.0. IELTS 8.5. SAT 1340. Olimpiada va kuchli motivatsion essay.\n"
        "\n"
        "Bu eng yuqori ko'rsatkichli talabamiz. Lekin diqqat qiling — u ham TOPIK topshirmagan.\n"
        "\n"
        "Uning yutgani tasodif emas: to'g'ri universitet, to'g'ri yo'nalish, to'g'ri tayyorgarlik.\n"
        "\n"
        f"O'z holatingizni baholab beramiz. Yozing: {ADMIN_USERNAME}"
     )},

    # ══════════════ 4-KUN ══════════════
    {"id": "d4m1s", "day": 4, "hour": 9, "segment": "seen", "type": "text",
     "text": (
        "Qo'llanmani ko'rdingiz. Endi nima?\n"
        "\n"
        "Ko'pchilik shu yerda to'xtaydi. Ma'lumot oladi, lekin harakat qilmaydi.\n"
        "\n"
        "Hozir aniq 3 ta narsa qiling:\n"
        "\n"
        "1. GPA ingizni hisoblang\n"
        "2. Yo'nalishni aniq tanlang\n"
        "3. O'sha yo'nalishda kuchli 3 ta universitetni yozing\n"
        "\n"
        "Shu 3 tasi bo'lsa — siz ko'pchilikdan oldindasiz.\n"
        "\n"
        f"Qaysi bosqichda qiynalyapsiz? Yozing: {ADMIN_USERNAME}"
     )},

    {"id": "d4m1n", "day": 4, "hour": 9, "segment": "not_seen", "type": "text_button",
     "text": (
        "Koreya universitetlariga hujjat topshirish 2 ta raundda bo'ladi. Birinchi raund sentyabrda boshlanadi.\n"
        "\n"
        "Ya'ni tayyorgarlik uchun 2 oy qoldi.\n"
        "\n"
        "Qo'llanma sizda bor, lekin hali ochmadingiz. Bu — yo'qotilayotgan vaqt.\n"
        "\n"
        f"5 daqiqa ajrating: {GUIDE_1}"
     ),
     "buttons": [("Endi ko'rdim", "guide_seen")]},

    {"id": "d4m2", "day": 4, "hour": 19, "segment": "all", "type": "text",
     "text": (
        "\"Menda TOPIK yo'q, imkoniyatim bormi?\"\n"
        "\n"
        "Eng ko'p beriladigan savol. Javob: ha.\n"
        "\n"
        "Rajabov Jo'rabek — Sejong University, Computer Science. IELTS 6.5. TOPIK yo'q. Faqat olimpiada.\n"
        "\n"
        "Abduvaliyeva Mehrangiz — Yonsei University (Koreya TOP 3). IELTS 7.5. TOPIK yo'q. Sertifikatlar va volontyorlik.\n"
        "\n"
        "Ikkalasi ham koreys tilisiz kirdi.\n"
        "\n"
        f"Sizning holatingizni ham baholab beramiz: {ADMIN_USERNAME}"
     )},

    # ══════════════ 5-KUN ══════════════
    {"id": "d5_admin", "day": 5, "hour": 8, "segment": "admin", "type": "admin_note",
     "text": (
        "ADMIN ESLATMA\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Bugun OVOZLI XABAR yuborish kuni.\n"
        "\n"
        "Tavsiya etilgan mavzu:\n"
        "\"Nega ko'pchilik grant yutolmaydi — 3 ta asosiy sabab\"\n"
        "\n"
        "Yuborish: ovozli xabarga reply qilib /broadcast_voice"
     )},

    {"id": "d5m1", "day": 5, "hour": 10, "segment": "all", "type": "text",
     "text": (
        "Motivatsion xat — grant yutishning eng kuchli quroli.\n"
        "\n"
        "Qo'llanmadagi 10 ta talabaning 10 tasida ham kuchli motivatsion xat bor edi. GPA turlicha, IELTS turlicha — lekin motivatsion xat hammada kuchli.\n"
        "\n"
        "Nega? Chunki GPA va IELTS — bu raqam. Professor sizni tanimaydi.\n"
        "\n"
        "Motivatsion xat esa — sizning ovozingiz. U orqali professor sizni ko'radi va grant beradi.\n"
        "\n"
        "Ko'pchilik buni oxirgi kunda shoshib yozadi. Va shu sababli yutqazadi."
     )},

    {"id": "d5m2", "day": 5, "hour": 19, "segment": "all", "type": "text",
     "text": (
        "Gulomjonova Malika — Konkuk University, Business Administration.\n"
        "\n"
        "GPA 4.4. IELTS yo'q. TOPIK 4. Motivatsion essay.\n"
        "\n"
        "Diqqat qiling: IELTS sertifikati umuman yo'q edi. Faqat TOPIK 4.\n"
        "\n"
        "Lekin u to'g'ri universitetni tanladi va kuchli motivatsion xat yozdi.\n"
        "\n"
        f"Sizda ham imkoniyat bor. Yozing, strategiya tuzamiz: {ADMIN_USERNAME}"
     )},

    # ══════════════ 6-KUN ══════════════
    {"id": "d6m1", "day": 6, "hour": 10, "segment": "all", "type": "text",
     "text": (
        "Grant turlari haqida.\n"
        "\n"
        "Koreyada 2 xil grant bor:\n"
        "\n"
        "1. GKS (davlat granti) — 100% o'qish + yashash + tibbiy sug'urta. Eng kuchli, lekin raqobat baland.\n"
        "\n"
        "2. Universitet ichki granti — 30% dan 100% gacha. Raqobat kamroq, imkoniyat ko'proq.\n"
        "\n"
        "Qo'llanmadagi 10 ta talabaning ko'pchiligi ikkinchi yo'l bilan yutdi.\n"
        "\n"
        "Ya'ni faqat GKS ga umid bog'lash — noto'g'ri strategiya."
     )},

    {"id": "d6m2", "day": 6, "hour": 18, "segment": "not_seen", "type": "text_button",
     "text": (
        "Qo'llanmani hali ochmadingiz.\n"
        "\n"
        "U bepul va ichida 10 ta talabaning aniq yo'li bor — GPA, IELTS, universitet, hujjat. Hammasi jadvalda.\n"
        "\n"
        f"Oching: {GUIDE_1}"
     ),
     "buttons": [("Ko'rdim", "guide_seen")]},

    # ══════════════ 7-KUN ══════════════
    {"id": "d7m1", "day": 7, "hour": 10, "segment": "all", "type": "text",
     "text": (
        "O'zingizni tekshiring. 5 ta savolga javob bering:\n"
        "\n"
        "1. Qaysi yo'nalishda o'qimoqchisiz?\n"
        "2. O'sha yo'nalishda qaysi 3 ta universitet kuchli?\n"
        "3. Ularning IELTS/TOPIK talabi qancha?\n"
        "4. Sizning GPA ingiz yetadimi?\n"
        "5. Motivatsion xatingiz tayyormi?\n"
        "\n"
        "Agar shu 5 taga aniq javob bera olmasangiz — hali tayyor emassiz.\n"
        "\n"
        f"Bepul konsultatsiya uchun yozing: {ADMIN_USERNAME}"
     )},

    {"id": "d7m2", "day": 7, "hour": 19, "segment": "all", "type": "text",
     "text": (
        "Iskandarov Bunyodbek — Sungkyunkwan University, Computer Science.\n"
        "\n"
        "GPA 5.0. IELTS 7.0. SAT 1450. Sertifikatlar.\n"
        "\n"
        "IELTS 7.0 — bu juda yuqori ball emas. Lekin u Koreyaning TOP 4 universitetiga kirdi.\n"
        "\n"
        "Chunki GPA 5.0 va SAT 1450 uning kuchli tomoni edi. U shuni to'g'ri ishlatdi.\n"
        "\n"
        "Har kimning kuchli tomoni bor. Muhimi — uni to'g'ri ko'rsatish."
     )},

    # ══════════════ 8-KUN ══════════════
    {"id": "d8_admin", "day": 8, "hour": 8, "segment": "admin", "type": "admin_note",
     "text": (
        "ADMIN ESLATMA\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Bugun YUMALOQ VIDEO yuborish kuni.\n"
        "\n"
        "Tavsiya etilgan mavzu:\n"
        "\"Vebinar e'loni — 24-26 iyul, nimalar bo'ladi\"\n"
        "\n"
        "Yuborish: yumaloq videoga reply qilib /broadcast_video"
     )},

    {"id": "d8m1", "day": 8, "hour": 10, "segment": "all", "type": "text",
     "text": (
        "24-26 iyul kunlari bepul vebinar o'tkazamiz.\n"
        "\n"
        "Mavzular:\n"
        "— Koreya TOP universitetlariga grant bilan kirish yo'li\n"
        "— Universitet tanlash formulasi\n"
        "— Motivatsion xat: professor nimani ko'radi\n"
        "— Hujjat topshirish: bosqichma-bosqich\n"
        "— Eng ko'p qilinadigan 7 ta xato\n"
        "\n"
        f"Kanalga o'ting va obuna bo'ling: {CHANNEL}"
     )},

    {"id": "d8m2", "day": 8, "hour": 19, "segment": "all", "type": "text",
     "text": (
        "Saydullayev Abduvosid — Sungkyunkwan University, Mechanical Engineering.\n"
        "\n"
        "GPA 4.8. IELTS 7.5. SAT 1530. Media loyihalar va kuchli motivatsion essay.\n"
        "\n"
        "Diqqat: u faqat baholarga tayanmadi. Media loyihalari bilan ajralib turdi.\n"
        "\n"
        "Universitet sizni raqam sifatida emas, inson sifatida ko'rishi kerak.\n"
        "\n"
        "Buni qanday qilish kerakligini vebinarda batafsil aytamiz."
     )},

    # ══════════════ 9-KUN ══════════════
    {"id": "d9m1", "day": 9, "hour": 10, "segment": "all", "type": "text",
     "text": (
        "\"O'zim topshira olamanmi?\"\n"
        "\n"
        "Halol javob: ha, topshira olasiz. Internetda ma'lumot bor.\n"
        "\n"
        "Lekin savol boshqa:\n"
        "\n"
        "Qaysi universitetga topshirish kerakligini bilasizmi? Qaysi raundda? Motivatsion xatda professor nimani ko'rishini bilasizmi?\n"
        "\n"
        "Hujjatda bitta xato — rad javobi degani.\n"
        "\n"
        "Ma'lumot boshqa, tajriba boshqa."
     )},

    {"id": "d9m2", "day": 9, "hour": 19, "segment": "all", "type": "text",
     "text": (
        "Vebinargacha 3 kun qoldi.\n"
        "\n"
        "Bu vebinar siz uchun, agar:\n"
        "— Koreyada o'qishni jiddiy rejalashtirsangiz\n"
        "— Grant yutmoqchi bo'lsangiz\n"
        "— Qayerdan boshlashni bilmasangiz\n"
        "\n"
        "24-26 iyul. Bepul.\n"
        "\n"
        f"Kanalda bo'ling: {CHANNEL}"
     )},

    # ══════════════ 10-KUN ══════════════
    {"id": "d10m1", "day": 10, "hour": 10, "segment": "all", "type": "text",
     "text": (
        "Koreyada hujjat topshirish 2 ta raundda bo'ladi.\n"
        "\n"
        "1-raund (sentyabr): grant imkoniyati yuqori, raqobat kamroq, joylar ko'p.\n"
        "\n"
        "2-raund (mart): joylar kam qoladi, grant imkoniyati past.\n"
        "\n"
        "Bizning talabalarimizning ko'pchiligi 1-raundda topshirdi.\n"
        "\n"
        "Ya'ni hozir tayyorgarlik boshlasangiz — 1-raundga ulgurasiz."
     )},

    {"id": "d10m2", "day": 10, "hour": 19, "segment": "all", "type": "text",
     "text": (
        "Bir savol.\n"
        "\n"
        "1 yildan keyin qayerda bo'lishni xohlaysiz?\n"
        "\n"
        "Variant A: hali ham \"qachondir Koreyaga boraman\" deb orzu qilib yurasiz.\n"
        "\n"
        "Variant B: Seoul da, universitet auditoriyasida o'tirasiz. Grant bilan.\n"
        "\n"
        "Qo'llanmadagi 10 ta talaba bir yil oldin xuddi shu joyda edi. Farqi — ular harakat qildi.\n"
        "\n"
        f"Vebinar 24-26 iyul: {CHANNEL}"
     )},

    # ══════════════ 11-KUN ══════════════
    {"id": "d11_admin", "day": 11, "hour": 8, "segment": "admin", "type": "admin_note",
     "text": (
        "ADMIN ESLATMA\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Bugun OVOZLI XABAR yoki YUMALOQ VIDEO yuborish kuni.\n"
        "\n"
        "Tavsiya etilgan mavzu:\n"
        "\"Ertaga vebinar — shaxsiy taklif\"\n"
        "\n"
        "/broadcast_voice yoki /broadcast_video"
     )},

    {"id": "d11m1", "day": 11, "hour": 10, "segment": "all", "type": "text",
     "text": (
        "Ertaga vebinar boshlanadi.\n"
        "\n"
        "Nima olasiz:\n"
        "— Aniq yo'l xaritasi: qayerdan boshlash\n"
        "— Universitet tanlash formulasi\n"
        "— Grant yutish strategiyasi\n"
        "— Savollaringizga javob\n"
        "\n"
        f"Kanalga obuna bo'ling va bildirishnomani yoqing: {CHANNEL}"
     )},

    {"id": "d11m2", "day": 11, "hour": 20, "segment": "all", "type": "text",
     "text": (
        "Vebinar davomida qatnashganlar uchun alohida imkoniyat e'lon qilamiz.\n"
        "\n"
        "Bu — faqat jonli qatnashganlar uchun. Keyin takrorlanmaydi.\n"
        "\n"
        "Ertaga boshlanadi.\n"
        "\n"
        f"Kanalga o'ting: {CHANNEL}"
     )},

    # ══════════════ 12-KUN ══════════════
    {"id": "d12m1", "day": 12, "hour": 9, "segment": "all", "type": "text",
     "text": (
        "Vebinar bugun boshlanadi.\n"
        "\n"
        "Koreya TOP universitetlariga grant bilan kirish — to'liq yo'l xaritasi.\n"
        "\n"
        f"Kanalga o'ting: {CHANNEL}"
     )},

    {"id": "d12m2", "day": 12, "hour": 18, "segment": "all", "type": "text",
     "text": (
        "Vebinar davom etmoqda.\n"
        "\n"
        "Agar o'tkazib yuborgan bo'lsangiz — hali kech emas.\n"
        "\n"
        f"Kanalga o'ting: {CHANNEL}"
     )},

    # ══════════════ 13-KUN ══════════════
    {"id": "d13m1", "day": 13, "hour": 9, "segment": "all", "type": "text",
     "text": (
        "Vebinar 2-kun.\n"
        "\n"
        "Bugungi mavzular:\n"
        "— Motivatsion xat: ishlaydigan formula\n"
        "— Grant yutish strategiyasi\n"
        "— Savol-javob\n"
        "\n"
        f"Kanalga o'ting: {CHANNEL}"
     )},

    {"id": "d13m2", "day": 13, "hour": 19, "segment": "all", "type": "text",
     "text": (
        "Vebinarda ko'rgan bo'lsangiz — endi harakat vaqti.\n"
        "\n"
        "Ma'lumot olish bir narsa. Uni qo'llash — butunlay boshqa.\n"
        "\n"
        "Agar yolg'iz qilishdan qo'rqsangiz yoki xato qilmaslikni istasangiz — biz bormiz.\n"
        "\n"
        f"Yozing: {ADMIN_USERNAME}"
     )},

    # ══════════════ 14-KUN ══════════════
    {"id": "d14m1", "day": 14, "hour": 10, "segment": "all", "type": "text",
     "text": (
        "Vebinar tugadi. Endi ikki yo'l bor.\n"
        "\n"
        "Birinchi: hech narsa qilmaslik. Yana bir yil orzu qilib yurish.\n"
        "\n"
        "Ikkinchi: bugun harakat qilish. Va keyingi yil Seoul da bo'lish.\n"
        "\n"
        "Qo'llanmadagi 10 ta talaba ikkinchisini tanladi.\n"
        "\n"
        f"Siz ham tanlasangiz — yozing: {ADMIN_USERNAME}"
     )},

    {"id": "d14m2", "day": 14, "hour": 19, "segment": "all", "type": "text",
     "text": (
        "Shu 2 hafta davomida biz siz bilan bo'ldik.\n"
        "\n"
        "Endi eng muhimi — harakat.\n"
        "\n"
        "Savollaringiz bo'lsa, biz doim shu yerdamiz.\n"
        "\n"
        f"{ADMIN_USERNAME}"
     )},
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
    # Qo'llanmani ko'rgan/ko'rmaganlar segmenti
    conn.execute("""
        CREATE TABLE IF NOT EXISTS guide_status (
            telegram_id INTEGER PRIMARY KEY,
            status TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
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


# ─── Professional broadcast tizimi ──────────────────────────────────────────────

# Bir vaqtda faqat bitta broadcast ishlashi uchun qulf
BROADCAST_LOCK = asyncio.Lock()


def mark_blocked(telegram_id):
    """Bot bloklagan foydalanuvchini bazadan o'chiradi (leads va starts dan)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM leads WHERE telegram_id = ?", (telegram_id,))
    conn.execute("DELETE FROM starts WHERE telegram_id = ?", (telegram_id,))
    conn.execute("UPDATE drip_users SET active = 0 WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()


async def safe_send(send_coro_func, telegram_id):
    """
    Bitta xabarni xavfsiz yuboradi.
    - Flood limitiga urilsa kutadi va qayta urinadi
    - Bloklangan bo'lsa bazadan o'chiradi
    Natija: "ok", "blocked", yoki "failed"
    """
    for attempt in range(2):
        try:
            await send_coro_func(telegram_id)
            return "ok"
        except RetryAfter as e:
            # Telegram "sekinroq" dedi — kutamiz va qayta urinamiz
            await asyncio.sleep(e.retry_after + 1)
            continue
        except Forbidden:
            # Bot bloklangan yoki foydalanuvchi o'chirilgan
            mark_blocked(telegram_id)
            return "blocked"
        except (TimedOut, NetworkError):
            await asyncio.sleep(1)
            continue
        except Exception as e:
            logger.warning(f"Yuborishda xatolik {telegram_id}: {e}")
            return "failed"
    return "failed"


async def run_broadcast(context, update, send_coro_func, label="Xabar"):
    """
    Barcha foydalanuvchilarga xabar yuboradi — professional tarzda.
    send_coro_func(telegram_id) — bitta odamga yuboruvchi funksiya.
    """
    # Qulf: agar broadcast allaqachon ketayotgan bo'lsa, to'xtatamiz
    if BROADCAST_LOCK.locked():
        await update.message.reply_text(
            "⏳ Hozir boshqa xabar tarqatilyapti. Iltimos, u tugaguncha kuting."
        )
        return

    async with BROADCAST_LOCK:
        user_ids = get_all_user_ids()
        if not user_ids:
            await update.message.reply_text("Hali hech qanday foydalanuvchi yo'q.")
            return

        total = len(user_ids)
        status = await update.message.reply_text(f"📤 {label} {total} ta odamga yuborilmoqda...\n\n0 / {total}")

        ok = blocked = failed = 0
        for i, uid in enumerate(user_ids, 1):
            result = await safe_send(send_coro_func, uid)
            if result == "ok":
                ok += 1
            elif result == "blocked":
                blocked += 1
            else:
                failed += 1

            # Telegram limiti: soniyasiga ~25 xabar
            await asyncio.sleep(0.04)

            # Har 25 tada progress yangilanadi
            if i % 25 == 0:
                try:
                    await status.edit_text(f"📤 {label} yuborilmoqda...\n\n{i} / {total}")
                except Exception:
                    pass

        await status.edit_text(
            f"✅ {label} yuborildi!\n\n"
            f"📨 Yetkazildi: {ok} ta\n"
            f"🚫 Bloklagan (o'chirildi): {blocked} ta\n"
            f"❌ Xato: {failed} ta"
        )


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


def set_guide_status(telegram_id, status):
    """status: 'seen' yoki 'not_seen'"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO guide_status (telegram_id, status) VALUES (?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            status = excluded.status,
            updated_at = datetime('now','localtime')
    """, (telegram_id, status))
    conn.commit()
    conn.close()


def get_guide_status(telegram_id):
    """Qaytaradi: 'seen', 'not_seen', yoki None (javob bermagan)"""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT status FROM guide_status WHERE telegram_id = ?", (telegram_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def get_guide_stats():
    """Segment statistikasi"""
    conn = sqlite3.connect(DB_PATH)
    seen = conn.execute("SELECT COUNT(*) FROM guide_status WHERE status='seen'").fetchone()[0]
    not_seen = conn.execute("SELECT COUNT(*) FROM guide_status WHERE status='not_seen'").fetchone()[0]
    total_drip = conn.execute("SELECT COUNT(*) FROM drip_users WHERE active=1").fetchone()[0]
    conn.close()
    no_answer = max(0, total_drip - seen - not_seen)
    return seen, not_seen, no_answer, total_drip


def drip_start_all_users():
    """
    BARCHA mavjud foydalanuvchilarni drip ga qo'shadi va BUGUNDAN boshlaydi.
    /drip_start buyrug'i bilan bir marta ishlatiladi.
    """
    conn = sqlite3.connect(DB_PATH)
    user_ids = conn.execute("""
        SELECT telegram_id FROM starts
        UNION
        SELECT telegram_id FROM leads
    """).fetchall()

    count = 0
    for (uid,) in user_ids:
        if not uid:
            continue
        conn.execute("""
            INSERT INTO drip_users (telegram_id, started_at, active)
            VALUES (?, datetime('now','localtime'), 1)
            ON CONFLICT(telegram_id) DO UPDATE SET
                started_at = datetime('now','localtime'),
                active = 1
        """, (uid,))
        count += 1

    # Eski yuborilgan drip yozuvlarini tozalaymiz (qaytadan boshlanadi)
    conn.execute("DELETE FROM drip_sent")
    conn.commit()
    conn.close()
    return count


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
        f"🆕 YANGI LEAD\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Ism: {name}\n"
        f"🔗 Telegram: {tg_link}\n"
        f"🎯 Segment: {lm_label}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📋 Javoblar:\n{answers_text}"
    )

    try:
        save_lead(user.id, user.username, name, answers, lead_magnet)
        drip_start_user(user.id)  # Drip ketma-ketligini boshlash
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg)
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

    # MUHIM: qator o'tishlarni saqlash uchun to'liq matnni olamiz
    full = update.message.text or ""
    parts = full.split(None, 1)  # birinchi bo'shliq/qator bo'yicha ajratamiz
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(
            "❗ Xabar matni kiriting.\n\nMisol:\n/broadcast Salom! Yangi vebinar bo'ladi..."
        )
        return

    text = parts[1]

    async def send(uid):
        await context.bot.send_message(chat_id=uid, text=text)

    await run_broadcast(context, update, send, label="Matn xabar")


async def cmd_broadcast_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Rasmga reply qilib /broadcast_photo — rasm + matn birga yuboriladi.
    Matn rasmning caption (izoh) qismidan olinadi.
    """
    if not is_admin(update.effective_user.id):
        return

    reply = update.message.reply_to_message
    if not reply or not reply.photo:
        await update.message.reply_text(
            "❗ Rasmga REPLY qilib /broadcast_photo yozing.\n\n"
            "Ya'ni: avval rasmni matn (izoh) bilan botga yuboring, "
            "keyin o'sha rasmga reply qilib bu buyruqni yozing.\n\n"
            "Eslatma: rasm izohi 1024 belgidan oshmasligi kerak."
        )
        return

    # Eng katta o'lchamdagi rasmni olamiz
    file_id = reply.photo[-1].file_id
    caption = reply.caption or ""

    if len(caption) > 1024:
        await update.message.reply_text(
            f"❗ Matn juda uzun: {len(caption)} belgi.\n\n"
            f"Telegram rasm izohi uchun maksimum 1024 belgi ruxsat beradi.\n"
            f"{len(caption) - 1024} ta belgini qisqartiring."
        )
        return

    async def send(uid):
        await context.bot.send_photo(chat_id=uid, photo=file_id, caption=caption)

    await run_broadcast(context, update, send, label="Rasm + matn")


async def cmd_drip_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    BARCHA mavjud foydalanuvchilarni drip ga qo'shadi va BUGUNDAN boshlaydi.
    Bir marta ishlatiladi — drip kampaniyasini ishga tushirish uchun.
    """
    if not is_admin(update.effective_user.id):
        return

    count = drip_start_all_users()
    await update.message.reply_text(
        f"✅ Drip kampaniya boshlandi!\n"
        f"\n"
        f"👥 {count} ta foydalanuvchi qo'shildi\n"
        f"📅 Boshlanish: bugundan (1-kun)\n"
        f"⏰ Xabarlar 06:00–23:00 oralig'ida yuboriladi\n"
        f"\n"
        f"Birinchi xabar bir necha daqiqada boradi."
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

    async def send(uid):
        await context.bot.send_video_note(chat_id=uid, video_note=file_id)

    await run_broadcast(context, update, send, label="Yumaloq video")


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

    async def send(uid):
        await context.bot.send_voice(chat_id=uid, voice=file_id)

    await run_broadcast(context, update, send, label="Ovozli xabar")


async def drip_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Har 5 daqiqada ishlaydi.
    Foydalanuvchiga TO'G'RIDAN-TO'G'RI yubormaydi!
    O'rniga ADMINGA eslatma yuboradi: "Shu xabarni yuborish vaqti keldi" + tugma.
    Admin tugmani bosса — bot o'sha segmentga yuboradi.
    """
    now = datetime.now()
    if now.hour < 6 or now.hour >= 23:
        return

    if not DRIP_SEQUENCE:
        return

    users = drip_get_active_users()
    if not users:
        return

    # Drip boshlangan sana (birinchi foydalanuvchi bo'yicha)
    try:
        started = datetime.strptime(users[0][1], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return

    elapsed_days = (now.date() - started.date()).days + 1

    for step in DRIP_SEQUENCE:
        if step["day"] != elapsed_days:
            continue
        if now.hour < step["hour"]:
            continue
        if drip_already_sent(ADMIN_CHAT_ID, step["id"]):
            continue

        seg = step.get("segment", "all")
        t = step.get("type", "text")

        # Admin eslatmasi (voice/video haqida) — shunchaki yuboriladi
        if t == "admin_note":
            try:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=step["text"])
                drip_mark_sent(ADMIN_CHAT_ID, step["id"])
            except Exception as e:
                logger.warning(f"Admin eslatma yuborilmadi: {e}")
            continue

        # Oddiy xabar — adminga TASDIQLASH uchun yuboriladi
        seg_names = {
            "all": "HAMMAGA",
            "seen": "Qo'llanmani KO'RGANLARGA",
            "not_seen": "Qo'llanmani KO'RMAGANLARGA",
            "no_answer": "JAVOB BERMAGANLARGA",
            "q1_a": "SERTIFIKAT YO'Q (sovuq)",
            "q1_b": "SERTIFIKAT BOR (issiq)",
            "q1_c": "UNIVERSITET TANLANGAN (eng issiq)",
        }
        seg_label = seg_names.get(seg, seg)

        # Nechta odamga boradi?
        target_count = len(get_segment_users(seg))

        has_buttons = (t == "text_button")
        btn_note = "\n\n📎 Bu xabarda TUGMA bor (Ko'rdim / Ko'rmadim)" if has_buttons else ""

        notice = (
            f"⏰ XABAR YUBORISH VAQTI KELDI\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📅 {elapsed_days}-kun, soat {step['hour']}:00\n"
            f"🎯 Kimga: {seg_label}\n"
            f"👥 Nechta: {target_count} ta odam{btn_note}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"XABAR MATNI:\n"
            f"\n"
            f"{step['text']}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yuborish", callback_data=f"dsend:{step['id']}")],
            [InlineKeyboardButton("⏭ O'tkazib yuborish", callback_data=f"dskip:{step['id']}")],
        ])

        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID, text=notice, reply_markup=keyboard
            )
            # Eslatma yuborildi deb belgilaymiz (qayta yubormaslik uchun)
            drip_mark_sent(ADMIN_CHAT_ID, step["id"])
        except Exception as e:
            logger.warning(f"Drip eslatma yuborilmadi: {e}")


def get_segment_users(segment):
    """Segment bo'yicha foydalanuvchilar ro'yxati."""
    conn = sqlite3.connect(DB_PATH)

    if segment == "all":
        rows = conn.execute("SELECT telegram_id FROM drip_users WHERE active = 1").fetchall()
    elif segment == "seen":
        rows = conn.execute("""
            SELECT d.telegram_id FROM drip_users d
            JOIN guide_status g ON d.telegram_id = g.telegram_id
            WHERE d.active = 1 AND g.status = 'seen'
        """).fetchall()
    elif segment == "not_seen":
        rows = conn.execute("""
            SELECT d.telegram_id FROM drip_users d
            JOIN guide_status g ON d.telegram_id = g.telegram_id
            WHERE d.active = 1 AND g.status = 'not_seen'
        """).fetchall()
    elif segment == "no_answer":
        rows = conn.execute("""
            SELECT telegram_id FROM drip_users
            WHERE active = 1
              AND telegram_id NOT IN (SELECT telegram_id FROM guide_status)
        """).fetchall()
    # ─── Q1 bo'yicha segmentlar (tayyorgarlik bosqichi) ───
    elif segment in ("q1_a", "q1_b", "q1_c"):
        # answers JSON ichida "q1": "q1_a" ko'rinishida saqlangan
        pattern = f'%"q1": "{segment}"%'
        rows = conn.execute("""
            SELECT d.telegram_id FROM drip_users d
            JOIN leads l ON d.telegram_id = l.telegram_id
            WHERE d.active = 1 AND l.answers LIKE ?
        """, (pattern,)).fetchall()
    else:
        rows = []

    conn.close()
    return [r[0] for r in rows if r[0]]


async def drip_admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin 'Yuborish' yoki 'O'tkazib yuborish' tugmasini bosganda."""
    query = update.callback_query
    await query.answer()

    if not is_admin(update.effective_user.id):
        return

    data = query.data  # "dsend:d1m1" yoki "dskip:d1m1"
    action, step_id = data.split(":", 1)

    # Step ni topamiz
    step = next((s for s in DRIP_SEQUENCE if s["id"] == step_id), None)
    if not step:
        await query.edit_message_text("❌ Xabar topilmadi.")
        return

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if action == "dskip":
        await query.message.reply_text("⏭ O'tkazib yuborildi.")
        return

    # Yuborish
    if BROADCAST_LOCK.locked():
        await query.message.reply_text("⏳ Hozir boshqa xabar tarqatilyapti. Biroz kuting va qayta urinib ko'ring.")
        return

    seg = step.get("segment", "all")
    user_ids = get_segment_users(seg)

    if not user_ids:
        await query.message.reply_text("Bu segmentda hech kim yo'q.")
        return

    text = step["text"]
    t = step.get("type", "text")

    if t == "text_button":
        btns = step.get("buttons", [])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(label, callback_data=cb)] for label, cb in btns
        ])
        async def send(uid):
            await context.bot.send_message(chat_id=uid, text=text, reply_markup=kb)
    else:
        async def send(uid):
            await context.bot.send_message(chat_id=uid, text=text)

    async with BROADCAST_LOCK:
        total = len(user_ids)
        status = await query.message.reply_text(f"📤 Yuborilmoqda...\n\n0 / {total}")
        ok = blocked = failed = 0
        for i, uid in enumerate(user_ids, 1):
            result = await safe_send(send, uid)
            if result == "ok":
                ok += 1
            elif result == "blocked":
                blocked += 1
            else:
                failed += 1
            await asyncio.sleep(0.04)
            if i % 25 == 0:
                try:
                    await status.edit_text(f"📤 Yuborilmoqda...\n\n{i} / {total}")
                except Exception:
                    pass

        await status.edit_text(
            f"✅ Yuborildi!\n"
            f"\n"
            f"📨 Yetkazildi: {ok} ta\n"
            f"🚫 Bloklagan: {blocked} ta\n"
            f"❌ Xato: {failed} ta"
        )


async def guide_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'llanma tugmasi bosilganda: Ko'rdim / Hali ko'rmadim"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if data == "guide_seen":
        set_guide_status(user_id, "seen")
        await query.message.reply_text(
            "Zo'r! 👏\n"
            "\n"
            "Endi savollaringiz bo'lsa — bemalol yozing. Qo'llanmadagi biror joy tushunarsiz bo'lsa "
            "yoki o'z holatingizni baholashda yordam kerak bo'lsa, biz shu yerdamiz.\n"
            "\n"
            "📩 @Orix_Global_admin"
        )
    elif data == "guide_not_seen":
        set_guide_status(user_id, "not_seen")
        await query.message.reply_text(
            "Tushunarli 😊\n"
            "\n"
            "Vaqt topganingizda albatta ko'ring — bu sizning yo'lingizni ancha qisqartiradi.\n"
            "\n"
            "📖 https://t.me/orix_global_agency/634\n"
            "\n"
            "Savollaringiz bo'lsa: @Orix_Global_admin"
        )


async def cmd_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Yarim yo'lda to'xtaganlarga (start bosgan, lekin yakunlamagan) tugmali eslatma yuboradi.
    """
    if not is_admin(update.effective_user.id):
        return

    if BROADCAST_LOCK.locked():
        await update.message.reply_text(
            "⏳ Hozir boshqa xabar tarqatilyapti. Iltimos, u tugaguncha kuting."
        )
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

    async def send(uid):
        await context.bot.send_message(chat_id=uid, text=text, reply_markup=keyboard)

    async with BROADCAST_LOCK:
        total = len(user_ids)
        status = await update.message.reply_text(f"📤 Eslatma {total} ta odamga yuborilmoqda...\n\n0 / {total}")
        ok = blocked = failed = 0
        for i, uid in enumerate(user_ids, 1):
            result = await safe_send(send, uid)
            if result == "ok":
                ok += 1
            elif result == "blocked":
                blocked += 1
            else:
                failed += 1
            await asyncio.sleep(0.04)
            if i % 25 == 0:
                try:
                    await status.edit_text(f"📤 Eslatma yuborilmoqda...\n\n{i} / {total}")
                except Exception:
                    pass
        await status.edit_text(
            f"✅ Eslatma yuborildi!\n\n"
            f"📨 Yetkazildi: {ok} ta\n"
            f"🚫 Bloklagan (o'chirildi): {blocked} ta\n"
            f"❌ Xato: {failed} ta"
        )


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
        f"  • {LEAD_MAGNETS.get(m, LEAD_MAGNETS['default'])['label']}: {c} ta\n"
        for m, c in by_magnet
    )
    lead_lines = "".join(
        f"  • {LEAD_MAGNETS.get(m, LEAD_MAGNETS['default'])['label']}: {c} ta\n"
        for m, c in by_magnet_leads
    )
    empty = "  Hali yo'q"
    seen, not_seen, no_answer, total_drip = get_guide_stats()
    q1a = len(get_segment_users("q1_a"))
    q1b = len(get_segment_users("q1_b"))
    q1c = len(get_segment_users("q1_c"))
    msg = (
        f"📊 Statistika\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👆 /start bosildi: {total_starts} ta (bugun: {today_starts})\n"
        f"📥 Leadlar: {total_leads} ta (bugun: {today_leads})\n"
        f"📈 Konversiya: {conversion}%\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📬 DRIP KAMPANIYA\n"
        f"  Faol: {total_drip} ta\n"
        f"  ✅ Qo'llanmani ko'rgan: {seen} ta\n"
        f"  ❌ Ko'rmagan: {not_seen} ta\n"
        f"  ⏳ Javob bermagan: {no_answer} ta\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎯 TAYYORGARLIK SEGMENTI\n"
        f"  A. Sertifikat yo'q: {q1a} ta\n"
        f"  B. Sertifikat bor: {q1b} ta\n"
        f"  C. Universitet tanlangan: {q1c} ta\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 Lead manbai:\n{lead_lines or empty}"
    )
    await update.message.reply_text(msg)


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
        "🛠 Admin panel:\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "/stats — Statistika\n"
        "/leads — So'nggi 20 lead\n"
        "/export — CSV yuklab olish\n"
        "/broadcast [matn] — Hammaga matn\n"
        "/broadcast_video — Yumaloq video (reply)\n"
        "/broadcast_voice — Ovozli xabar (reply)\n"
        "/broadcast_photo — Rasm + matn (reply)\n"
        "/reminder — Yarim yo'lda to'xtaganlarga eslatma\n"
        "/import_leads — CSV dan lead tiklash (reply)\n"
        "/drip_start — DRIP kampaniyani boshlash (1 marta!)\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Deep linklar:\n\n"
        f"🎓 TOP Universitetlar:\n{base}topuni\n\n"
        f"🏛 Seoul National:\n{base}snu\n\n"
        f"📘 GKS Grant:\n{base}gks\n\n"
        f"📗 TOPIK:\n{base}topik"
    )
    await update.message.reply_text(msg)


# ─── Global xato ushlagich ──────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Har qanday kutilmagan xatoni ushlaydi — bot qulab tushmaydi."""
    err = context.error
    # Bloklangan foydalanuvchilar uchun log shart emas
    if isinstance(err, (Forbidden, TimedOut, NetworkError, RetryAfter)):
        return
    logger.error(f"Xatolik yuz berdi: {err}", exc_info=err)


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
    app.add_handler(CommandHandler("broadcast_photo", cmd_broadcast_photo))
    app.add_handler(CommandHandler("import_leads",    cmd_import_leads))
    app.add_handler(CommandHandler("reminder",        cmd_reminder))
    app.add_handler(CommandHandler("drip_start",      cmd_drip_start))

    # Qo'llanma tugmalari (Ko'rdim / Hali ko'rmadim)
    app.add_handler(CallbackQueryHandler(guide_button_handler, pattern="^guide_(seen|not_seen)$"))

    # Drip admin tugmalari (Yuborish / O'tkazib yuborish)
    app.add_handler(CallbackQueryHandler(drip_admin_button, pattern="^(dsend|dskip):"))

    # Global xato ushlagich
    app.add_error_handler(error_handler)

    # Drip: har 5 daqiqada tekshirib, vaqti kelgan xabarlarni yuboradi
    app.job_queue.run_repeating(drip_job, interval=300, first=20)

    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
