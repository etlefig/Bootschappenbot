import os
import sys
from pathlib import Path
from typing import List

from tinydb import TinyDB, Query
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ====== Config ======
BASE = Path(__file__).parent
DB_PATH = BASE / "list.json"

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN or ":" not in TOKEN:
    print("ERROR: BOT_TOKEN ontbreekt of lijkt ongeldig.", file=sys.stderr)
    sys.exit(1)

# Optioneel: beperk de bot tot één chat (vul een chat_id in als je wilt locken)
ALLOWED_CHAT_ID = None  # bijv. -1001234567890 voor een groep

# ====== Data ======
db = TinyDB(DB_PATH)
Items = Query()

def add_item(text: str, who: str, list_name: str = "default"):
    text = text.strip()
    if not text:
        return
    db.insert({"text": text, "who": who, "list": list_name})

def remove_item_by_id(doc_id: int):
    db.remove(doc_ids=[doc_id])

def get_items(list_name: str = "default"):
    return db.search(Items.list == list_name)

def clear_list(list_name: str = "default"):
    db.remove(Items.list == list_name)

def title_for(list_name: str) -> str:
    return "Weekmenu" if list_name == "weekmenu" else "Boodschappen"

def render_list(list_name: str = "default") -> str:
    items = get_items(list_name)
    if not items:
        return f"{title_for(list_name)} is leeg."
    lines = [f"{i+1}. {it['text']} — {it.get('who','')}" for i, it in enumerate(items)]
    return f"{title_for(list_name)}\n" + "\n".join(lines)

# ====== Keyboards ======
def build_done_keyboard(list_name: str = "default") -> InlineKeyboardMarkup | None:
    items = get_items(list_name)
    if not items:
        return None
    rows: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for idx, it in enumerate(items, start=1):
        label = f"✓ {idx}"
        row.append(InlineKeyboardButton(label, callback_data=f"done:{list_name}:{it.doc_id}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)

def build_quick_add_keyboard() -> ReplyKeyboardMarkup:
    # Snelkeuze knoppen (pas aan naar eigen smaak)
    boodschappen = ["Melk", "Brood", "Bananen", "Pasta", "Rijst", "WC-papier"]
    weekmenu = ["menu: Soep", "menu: Curry", "menu: Lasagne"]
    layout = [
        [KeyboardButton(x) for x in boodschappen[:3]],
        [KeyboardButton(x) for x in boodschappen[3:]],
        [KeyboardButton(x) for x in weekmenu],
    ]
    return ReplyKeyboardMarkup(layout, resize_keyboard=True)

# ====== Guards ======
def chat_allowed(update: Update) -> bool:
    if ALLOWED_CHAT_ID is None:
        return True
    cid = update.effective_chat.id if update.effective_chat else None
    return cid == ALLOWED_CHAT_ID

# ====== Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update):
        return
    text = (
        "Ik hou je lijsten bij.\n"
        "- Gewoon typen = naar Boodschappen\n"
        "- Voor weekmenu: begin met 'menu: '\n"
        "- /list of /list weekmenu om te bekijken\n"
        "- Tik op ✓ knoppen om te verwijderen\n"
        "- /clear of /clear weekmenu om te legen"
    )
    await update.message.reply_text(text, reply_markup=build_quick_add_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update):
        return
    await start(update, context)

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update):
        return
    if not context.args:
        return await update.message.reply_text("Gebruik: /add melk")
    add_item(" ".join(context.args), update.effective_user.first_name, "default")
    await update.message.reply_text("Toegevoegd aan Boodschappen.")

async def menu_add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update):
        return
    if not context.args:
        return await update.message.reply_text("Gebruik: /menuadd lasagne")
    add_item(" ".join(context.args), update.effective_user.first_name, "weekmenu")
    await update.message.reply_text("Toegevoegd aan Weekmenu.")

async def show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update):
        return
    list_name = "default"
    if context.args and context.args[0].lower() == "weekmenu":
        list_name = "weekmenu"
    await update.message.reply_text(
        render_list(list_name),
        reply_markup=build_done_keyboard(list_name),
    )

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update):
        return
    list_name = "default"
    if context.args and context.args[0].lower() == "weekmenu":
        list_name = "weekmenu"
    clear_list(list_name)
    await update.message.reply_text(f"{title_for(list_name)} geleegd.")

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        action, list_name, doc_id = query.data.split(":")
        if action == "done":
            remove_item_by_id(int(doc_id))
            await query.edit_message_text(
                render_list(list_name),
                reply_markup=build_done_keyboard(list_name),
            )
    except Exception as e:
        await query.edit_message_text(f"Er ging iets mis: {e}")

async def plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update):
        return
    txt = (update.message.text or "").strip()
    who = update.effective_user.first_name
    if not txt:
        return
    if txt.lower().startswith("menu:"):
        add_item(txt.split(":", 1)[1], who, "weekmenu")
        await update.message.reply_text("Toegevoegd aan Weekmenu.", reply_markup=build_quick_add_keyboard())
    else:
        add_item(txt, who, "default")
        await update.message.reply_text(f"Toegevoegd: {txt}", reply_markup=build_quick_add_keyboard())

# ====== Main ======
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("menuadd", menu_add_cmd))
    app.add_handler(CommandHandler("list", show))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text))

    # Polling is prima voor Railway/Render
    app.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()