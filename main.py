import asyncio
import asyncpg
import logging
import os
import openpyxl
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import FSInputFile

# --- 1. SOZLAMALAR ---
TOKEN = "8689624670:AAEsKwQCdyIozvw2-RbY_Y-58cZmBg4K_R8" 
ADMIN_ID = 1805830760 

# 🚨 DIQQAT: MANA SHU YERGA NEON BAZANGIZ SSILKASINI QUYING! 🚨
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@ep-nomi.eu-central-1.aws.neon.tech/neondb?sslmode=require")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- XOTIRA HOLATLARI (STATES) ---
class PostStates(StatesGroup):
    waiting_title = State() 
    waiting_uz_media = State()
    waiting_uz_text = State()
    waiting_ru_media = State()
    waiting_ru_text = State()
    waiting_en_media = State()
    waiting_en_text = State()

class ContactStates(StatesGroup):
    waiting_for_message = State()

class AdminReplyStates(StatesGroup):
    waiting_for_reply = State()

# --- 2. BAZA (NEON POSTGRESQL) ---
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""CREATE TABLE IF NOT EXISTS users 
                          (user_id BIGINT PRIMARY KEY, full_name TEXT, username TEXT)""")
    try:
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name TEXT")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT")
    except: pass

    await conn.execute("""CREATE TABLE IF NOT EXISTS all_posts 
                          (id SERIAL PRIMARY KEY, title TEXT, 
                           uz_text TEXT, uz_file TEXT, uz_type TEXT,
                           ru_text TEXT, ru_file TEXT, ru_type TEXT,
                           en_text TEXT, en_file TEXT, en_type TEXT)""")
    await conn.execute("CREATE TABLE IF NOT EXISTS sent_messages (post_id INTEGER, user_id BIGINT, msg_id BIGINT)")
    await conn.close()

# --- 3. TUGMALAR ---
def main_menu(user_id=None):
    b = ReplyKeyboardBuilder()
    b.button(text="🗝 J'IER — g'azna")
    b.button(text="xato topsangiz, yozing")
    b.button(text="🚀 nima qilolamiz?")
    if user_id == ADMIN_ID:
        b.button(text="📊 Statistika")
    return b.adjust(1, 2, 1).as_markup(resize_keyboard=True)

def cancel_menu():
    b = ReplyKeyboardBuilder()
    b.button(text="🔙 bekor qilish")
    return b.as_markup(resize_keyboard=True)

async def get_available_langs(p_id):
    conn = await asyncpg.connect(DATABASE_URL)
    r = await conn.fetchrow("SELECT uz_text, uz_file, ru_text, ru_file, en_text, en_file FROM all_posts WHERE id = $1", p_id)
    await conn.close()
    if not r: return []
    langs = []
    if r['uz_text'] or r['uz_file']: langs.append("uz")
    if r['ru_text'] or r['ru_file']: langs.append("ru")
    if r['en_text'] or r['en_file']: langs.append("en")
    return langs

def get_post_keyboard(p_id, available_langs, is_expanded=False, is_admin=False, show_read=False):
    kb = InlineKeyboardBuilder()
    prefix = "v" if show_read else "l"
    if not is_expanded and len(available_langs) > 1:
        kb.button(text="🌍 boshqa tilda o‘qimoqchimisiz?", callback_data=f"expand_{prefix}_{p_id}")
    elif is_expanded:
        for lang in available_langs:
            label = {"uz": "🇺🇿 UZ", "ru": "🇷🇺 RU", "en": "🇺🇸 EN"}[lang]
            kb.button(text=label, callback_data=f"{prefix}_{p_id}_{lang}")
        kb.button(text="🔙 orqaga", callback_data=f"collapse_{prefix}_{p_id}")
    if show_read: kb.button(text="o'qib bo'ldim! ✅", callback_data="del_msg")
    if is_admin: kb.button(text="🗑 Global o'chirish", callback_data=f"global_{p_id}")
    return kb.adjust(3 if is_expanded else 1, 1).as_markup()

async def send_specific_media(chat_id, text, file_id, media_type, kb):
    try:
        if media_type == "photo": return await bot.send_photo(chat_id, file_id, caption=text, reply_markup=kb)
        elif media_type == "video": return await bot.send_video(chat_id, file_id, caption=text, reply_markup=kb)
        elif media_type == "document": return await bot.send_document(chat_id, file_id, caption=text, reply_markup=kb)
        else: return await bot.send_message(chat_id, text, reply_markup=kb)
    except: return None

# --- 4. ADMINGA YOZISH VA JAVOB ---
@dp.message(F.text == "xato topsangiz, yozing")
async def contact_admin_start(message: types.Message, state: FSMContext):
    await message.answer("✍🏻 Xato topdingizmi yoki taklifingiz bormi? Bemalol yozing.\n\nAdmin'Jon albatta ko‘rib chiqadi va javob beradi.", reply_markup=cancel_menu())
    await state.set_state(ContactStates.waiting_for_message)

@dp.message(ContactStates.waiting_for_message)
async def forward_to_admin(message: types.Message, state: FSMContext):
    if message.text == "🔙 bekor qilish":
        await message.answer("❌ Adminga yozish bekor qilindi.", reply_markup=main_menu(message.from_user.id))
        await state.clear(); return
    kb = InlineKeyboardBuilder(); kb.button(text="✍️ Javob berish", callback_data=f"reply_{message.from_user.id}")
    user_link = f"<a href='tg://user?id={message.from_user.id}'>{message.from_user.full_name}</a>"
    await bot.send_message(ADMIN_ID, f"📨 **Yangi xabar!**\n👤 Kimdan: {user_link}", parse_mode="HTML")
    await message.copy_to(ADMIN_ID, reply_markup=kb.as_markup())
    await message.answer("📨 Xabaringiz yetkazildi! \n\nAdmin'Jon ko‘rib chiqmoqda va tez orada javob beradi 👀.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data.startswith("reply_"))
async def admin_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    user_id = int(callback.data.split("_")[1]); await state.update_data(target_user=user_id)
    await callback.message.answer("✍️ Foydalanuvchiga javobingizni yozing:", reply_markup=cancel_menu())
    await state.set_state(AdminReplyStates.waiting_for_reply); await callback.answer()

@dp.message(AdminReplyStates.waiting_for_reply)
async def send_admin_reply(message: types.Message, state: FSMContext):
    if message.text == "🔙 bekor qilish":
        await message.answer("❌ Javob berish bekor qilindi.", reply_markup=main_menu(message.from_user.id))
        await state.clear(); return
    target_user = (await state.get_data()).get("target_user")
    try:
        await bot.send_message(target_user, "Admin'Jondan javob keldi ⚡️.")
        await message.copy_to(target_user)
        await message.answer("✅ Javobingiz foydalanuvchiga yuborildi!", reply_markup=main_menu(message.from_user.id))
    except: await message.answer(f"❌ Xatolik! Foydalanuvchi botni bloklagan bo'lishi mumkin.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- 5. INFO VA EXCEL STATISTIKA ---
@dp.message(F.text == "🚀 nima qilolamiz?")
async def bot_info(message: types.Message):
    info_text = (
    "<b>J'IER — Eng sara insholar va maqolalar jamlanmasi!</b> 💎\n\n"
    "Admin tomonidan siz uchun noyob va chuqur ma'noli bilimlarni bitta joyga jamladik.\n\n"
    "<b>🧠 J'IER orqali nimalarga ega bo'lasiz?</b>\n"
    "🔹 <b>Premium tahlillar:</b> Falsafa, iqtisodiyot, adabiyot va boshqa sohalardagi maqolalar.\n"
    "🔹 <b>Sokin mutolaa:</b> Hech qanday reklamasiz, o'qish uchun eng qulay va sokin muhit.\n\n"
    "<i>💡 O'z ustingizda ishlashdan to'xtamang. Fikr yoki takliflaringiz bo'lsa, pastdagi tugma orqali biz bilan bog'laning!</i>"
    )
    await message.answer(info_text, parse_mode="HTML")

@dp.message(F.text == "📊 Statistika")
async def admin_statistics(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = await asyncpg.connect(DATABASE_URL)
    users_list = await conn.fetch("SELECT user_id, full_name, username FROM users ORDER BY user_id DESC")
    await conn.close()
            
    total_users = len(users_list)
    stat_text = f"📊 <b>Platforma statistikasi:</b>\n\n👥 Faol a'zolar: <b>{total_users}</b> ta\n\n📋 <b>Foydalanuvchilar (Oxirgi 30 ta):</b>\n"
    
    for i, u in enumerate(users_list[:30], 1):
        uid, fname, uname = u['user_id'], u['full_name'], u['username']
        fname_safe = fname if fname else "Noma'lum"
        uname_text = f" | @{uname}" if uname else ""
        stat_text += f"{i}. <a href='tg://user?id={uid}'>{fname_safe}</a> (<code>{uid}</code>){uname_text}\n"

    if total_users > 30:
        stat_text += f"\n... va yana {total_users - 30} ta foydalanuvchi.\n(To'liq ro'yxatni Excel faylida ko'rishingiz mumkin 👇)"

    kb = InlineKeyboardBuilder()
    kb.button(text="📥 Excel (XLSX) yuklab olish", callback_data="export_excel")
    await message.answer(stat_text, parse_mode="HTML", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "export_excel")
async def export_users_excel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    await callback.message.answer("⏳ Excel fayl tayyorlanmoqda...")
    conn = await asyncpg.connect(DATABASE_URL)
    users = await conn.fetch("SELECT user_id, full_name, username FROM users ORDER BY user_id DESC")
    await conn.close()
            
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Foydalanuvchilar"
    ws.append(["Tartib", "Telegram ID", "Ism-familiya", "Username"])
    
    for i, u in enumerate(users, 1):
        ws.append([i, u['user_id'], u['full_name'] or "Noma'lum", f"@{u['username']}" if u['username'] else "Yo'q"])
        
    file_name = "JIER_foydalanuvchilar.xlsx"
    wb.save(file_name)
    document = FSInputFile(file_name)
    await bot.send_document(callback.message.chat.id, document, caption="📊 J'IER botining barcha a'zolari ro'yxati.")
    os.remove(file_name)
    await callback.answer()

# --- 6. ARXIV VA GLOBAL O'CHIRISH ---
@dp.callback_query(F.data.startswith("send_"))
async def broadcast_handler(callback: types.CallbackQuery):
    p_id = int(callback.data.split("_")[1]); langs = await get_available_langs(p_id)
    if not langs: return
    first = langs[0]
    
    conn = await asyncpg.connect(DATABASE_URL)
    post = await conn.fetchrow(f"SELECT {first}_text, {first}_file, {first}_type FROM all_posts WHERE id = $1", p_id)
    users = await conn.fetch("SELECT user_id FROM users")
    
    for row in users:
        sent = await send_specific_media(row['user_id'], post[0], post[1], post[2], get_post_keyboard(p_id, langs))
        if sent: 
            await conn.execute("INSERT INTO sent_messages (post_id, user_id, msg_id) VALUES ($1, $2, $3)", p_id, row['user_id'], sent.message_id)
            
    await conn.close()
    await callback.message.answer("🚀 Barcha foydalanuvchilarga yuborildi!"); await callback.answer()

@dp.callback_query(F.data.startswith("global_"))
async def global_delete_handler(callback: types.CallbackQuery):
    p_id = int(callback.data.split("_")[1])
    if callback.from_user.id != ADMIN_ID: return
    
    conn = await asyncpg.connect(DATABASE_URL)
    messages = await conn.fetch("SELECT user_id, msg_id FROM sent_messages WHERE post_id = $1", p_id)
    for row in messages:
        try: await bot.delete_message(row['user_id'], row['msg_id'])
        except: pass
    await conn.execute("DELETE FROM all_posts WHERE id = $1", p_id)
    await conn.execute("DELETE FROM sent_messages WHERE post_id = $1", p_id)
    await conn.close()
    await callback.message.edit_text("🗑 Post barcha chatlardan va bazadan o'chirildi."); await callback.answer()

@dp.message(F.text == "🗝 J'IER — g'azna")
async def list_p(message: types.Message):
    try: await message.delete() 
    except: pass
    conn = await asyncpg.connect(DATABASE_URL)
    posts = await conn.fetch("SELECT id, title FROM all_posts ORDER BY id DESC")
    await conn.close()
    
    if not posts: await message.answer("Hozircha g'azna bo'sh."); return
    kb = InlineKeyboardBuilder()
    for row in posts: kb.button(text=f"📄 {row['title']}", callback_data=f"show_{row['id']}")
    await message.answer("Kerakli faylni tanlang:", reply_markup=kb.adjust(1).as_markup())

@dp.callback_query(F.data.startswith("show_"))
async def show_p(callback: types.CallbackQuery):
    try: await callback.message.delete()
    except: pass
    p_id = int(callback.data.split("_")[1]); langs = await get_available_langs(p_id)
    conn = await asyncpg.connect(DATABASE_URL)
    p = await conn.fetchrow(f"SELECT {langs[0]}_text, {langs[0]}_file, {langs[0]}_type FROM all_posts WHERE id = $1", p_id)
    await conn.close()
    await send_specific_media(callback.from_user.id, p[0], p[1], p[2], get_post_keyboard(p_id, langs, False, callback.from_user.id == ADMIN_ID, True))
    await callback.answer()

@dp.callback_query(F.data.startswith(("expand_", "collapse_")))
async def toggle_menu(callback: types.CallbackQuery):
    parts = callback.data.split("_"); action, prefix, p_id = parts[0], parts[1], int(parts[2])
    langs = await get_available_langs(p_id)
    await callback.message.edit_reply_markup(reply_markup=get_post_keyboard(p_id, langs, is_expanded=(action == "expand"), is_admin=(callback.from_user.id == ADMIN_ID), show_read=(prefix == "v")))
    await callback.answer()

@dp.callback_query(F.data.startswith(("v_", "l_")))
async def switch_lang(callback: types.CallbackQuery):
    parts = callback.data.split("_"); mode, p_id, lang = parts[0], int(parts[1]), parts[2]
    langs = await get_available_langs(p_id)
    
    conn = await asyncpg.connect(DATABASE_URL)
    r = await conn.fetchrow(f"SELECT {lang}_text, {lang}_file, {lang}_type FROM all_posts WHERE id = $1", p_id)
    await conn.close()
    
    if r:
        kb = get_post_keyboard(p_id, langs, is_expanded=True, is_admin=(callback.from_user.id == ADMIN_ID), show_read=(mode == "v"))
        try:
            if r[2] != "text":
                media = types.InputMediaPhoto(media=r[1], caption=r[0]) if r[2] == "photo" else types.InputMediaVideo(media=r[1], caption=r[0])
                await callback.message.edit_media(media=media, reply_markup=kb)
            else: await callback.message.edit_text(r[0], reply_markup=kb)
        except: pass
    await callback.answer()

# --- 7. ADMIN: POST YARATISH ---
@dp.message(Command("yangi_post"))
async def start_new_post(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer("📌 Sarlavha yozing:"); await state.set_state(PostStates.waiting_title)

@dp.message(PostStates.waiting_title)
async def get_title_step(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text); await message.answer("🇺🇿 **UZ** Media (/skip):"); await state.set_state(PostStates.waiting_uz_media)

@dp.message(PostStates.waiting_uz_media)
async def get_uz_media_step(message: types.Message, state: FSMContext):
    f, t = (message.photo[-1].file_id, "photo") if message.photo else (message.video.file_id, "video") if message.video else (None, "text")
    await state.update_data(uz_file=f, uz_type=t); await message.answer("🇺🇿 **UZ** Matn (/skip):"); await state.set_state(PostStates.waiting_uz_text)

@dp.message(PostStates.waiting_uz_text)
async def get_uz_text_step(message: types.Message, state: FSMContext):
    await state.update_data(uz_text=None if message.text == "/skip" else message.text); await message.answer("🇷🇺 **RU** Media (/skip):"); await state.set_state(PostStates.waiting_ru_media)

@dp.message(PostStates.waiting_ru_media)
async def get_ru_media_step(message: types.Message, state: FSMContext):
    f, t = (message.photo[-1].file_id, "photo") if message.photo else (message.video.file_id, "video") if message.video else (None, "text")
    await state.update_data(ru_file=f, ru_type=t); await message.answer("🇷🇺 **RU** Matn (/skip):"); await state.set_state(PostStates.waiting_ru_text)

@dp.message(PostStates.waiting_ru_text)
async def get_ru_text_step(message: types.Message, state: FSMContext):
    await state.update_data(ru_text=None if message.text == "/skip" else message.text); await message.answer("🇺🇸 **EN** Media (/skip):"); await state.set_state(PostStates.waiting_en_media)

@dp.message(PostStates.waiting_en_media)
async def get_en_media_step(message: types.Message, state: FSMContext):
    f, t = (message.photo[-1].file_id, "photo") if message.photo else (message.video.file_id, "video") if message.video else (None, "text")
    await state.update_data(en_file=f, en_type=t); await message.answer("🇺🇸 **EN** Matn (/skip):"); await state.set_state(PostStates.waiting_en_text)

@dp.message(PostStates.waiting_en_text)
async def get_en_text_step(message: types.Message, state: FSMContext):
    data = await state.get_data(); en_text_data = None if message.text == "/skip" else message.text
    
    conn = await asyncpg.connect(DATABASE_URL)
    p_id = await conn.fetchval("""INSERT INTO all_posts (title, uz_text, uz_file, uz_type, ru_text, ru_file, ru_type, en_text, en_file, en_type) 
                                  VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id""", 
                                  data['title'], data.get('uz_text'), data.get('uz_file'), data.get('uz_type'), 
                                  data.get('ru_text'), data.get('ru_file'), data.get('ru_type'), en_text_data, data.get('en_file'), data.get('en_type'))
    await conn.close()
    
    kb = InlineKeyboardBuilder(); kb.button(text="🚀 Hammaga yuborish", callback_data=f"send_{p_id}")
    await message.answer(f"✅ '{data['title']}' tayyor.", reply_markup=kb.as_markup()); await state.clear()

# --- 8. START VA XABARNI O'CHIRISH ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""INSERT INTO users (user_id, full_name, username) 
                          VALUES ($1, $2, $3) 
                          ON CONFLICT (user_id) DO UPDATE SET full_name = EXCLUDED.full_name, username = EXCLUDED.username""", 
                          message.from_user.id, message.from_user.full_name, message.from_user.username)
    await conn.close()
    await message.answer("Assalomu alaykum! \nYaxshimisiz? \n\nXush kelibsiz! Quyidagi menyudan foydalaning yoki kuzatib boring: \nrahmat!", reply_markup=main_menu(message.from_user.id))

@dp.callback_query(F.data == "del_msg")
async def delete_my_msg(callback: types.CallbackQuery):
    try: await callback.message.delete()
    except: pass

# --- 9. RENDER UCHUN UYG'OTGICH SERVER VA ASOSIY FUNKSIYA ---
async def handle_ping(request):
    return web.Response(text="J'IER Bot mukammal ishlamoqda!")

async def main():
    await init_db()
    logging.basicConfig(level=logging.INFO)
    print("✅ Bot va Neon Baza barqaror ulandi...")
    
    # 🧹 Eskirib qolgan (navbatda turgan) xabarlarni o'chirib tashlash:
    await bot.delete_webhook(drop_pending_updates=True)
    
    # 1. Telegram botni orqa fonda ishga tushirish
    asyncio.create_task(dp.start_polling(bot))

    # 2. Render uxlab qolmasligi uchun "Mitti Web-server" yasash
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"🚀 Mitti qorovul-server {port}-portda yondi! Bot endi o'chmaydi.")
    await asyncio.Event().wait() # Dastur yopilib qolmasligi uchun kutish

if __name__ == "__main__": 
    asyncio.run(main())