import os, sys
from pathlib import Path
from typing import List, Dict
from tinydb import TinyDB, Query
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ====== Config & setup ======
BASE = Path(__file__).parent
DB_PATH = BASE / "list.json"

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN or ":" not in TOKEN:
    print("ERROR: BOT_TOKEN ontbreekt of lijkt ongeldig.", file=sys.stderr)
    sys.exit(1)

ALLOWED_CHAT_ID = None  # zet hier je groeps-id (bv. -100xxxxxxxxxx) om te locken

# ---- Categorieën & keyword mapping (pas aan naar smaak)
CATEGORIES = [
    "Groente & Fruit", "Brood & Banket", "Zuivel & Eieren",
    "Vlees/Vis/Vega", "Droge Waren", "Diepvries",
    "Drinken", "Huishoudelijk", "Badkamer", "Overig"
]

KEYWORDS: Dict[str, List[str]] = {
    "Groente & Fruit": ["tomaat","komkommer","sla","ui","knoflook","wortel","paprika","appel","banaan","citroen","limoen","spinazie","avocado","bosui","prei","courgette","broccoli","bloemkool","druif","peer","aardbei"],
    "Brood & Banket": ["brood","pistolet","tortilla","wrap","bagel","croissant","bol","pita","naan"],
    "Zuivel & Eieren": ["melk","sojamelk","havermelk","yoghurt","kwark","room","slagroom","boter","kaas","parmezaan","eieren","ei"],
    "Vlees/Vis/Vega": ["kip","gehakt","rund","bief","spek","tonijn","zalm","vis","vegetarisch","tofu","tempeh","falafel","vegaburger"],
    "Droge Waren": ["pasta","rijst","quinoa","couscous","bulgur","meel","bloem","havermout","suiker","zout","peper","panko","bouillon","kruiden","specerijen","olie","olijfolie","azijn","sojasaus","ketjap","tomatenpuree","bonen","kikkererwten"],
    "Diepvries": ["diepvries","ijs","diepvriesgroente","erwten","spinazie diepvries","pizza diepvries"],
    "Drinken": ["sap","fris","cola","limonade","bier","wijn","koffie","thee"],
    "Huishoudelijk": ["wc-papier","keukenrol","afwasmiddel","bleek","alcohol schoonmaak","schoonmaak","afvalzak","spons","wasmiddel","wasverzachter","vaatwastablet","wasparfum"],
    "Badkamer": ["tandpasta","shampoo","zeep","douchegel","scheermes","crème","luiers","billendoekjes","deo"],
    "Overig": []
}

def guess_category(text: str) -> str:
    t = text.lower()
    for cat, kws in KEYWORDS.items():
        for k in kws:
            if k in t:
                return cat
    return "Overig"

# ====== Data ======
db = TinyDB(DB_PATH)
Items = Query()

def add_item(text: str, who: str, list_name: str = "default", category: str | None = None):
    text = text.strip()
    if not text:
        return
    cat = category or guess_category(text)
    db.insert({"text": text, "who": who, "list": list_name, "cat": cat})

def remove_item_by_id(doc_id: int):
    db.remove(doc_ids=[doc_id])

def get_items(list_name: str = "default"):
    return db.search(Items.list == list_name)

def clear_list(list_name: str = "default"):
    db.remove(Items.list == list_name)

def title_for(list_name: str) -> str:
    return "Weekmenu" if list_name == "weekmenu" else "Boodschappen"

def group_by_category(items) -> Dict[str, List[dict]]:
    grouped: Dict[str, List[dict]] = {c: [] for c in CATEGORIES}
    for it in items:
        grouped.setdefault(it.get("cat","Overig"), []).append(it)
    # verwijder lege categorieën uit de weergave
    return {c: grouped[c] for c in CATEGORIES if grouped.get(c)}

def render_list(list_name: str = "default") -> str:
    items = get_items(list_name)
    if not items:
        return f"{title_for(list_name)} is leeg."
    grouped = group_by_category(items)
    lines = [f"{title_for(list_name)}"]
    n = 1
    for cat, rows in grouped.items():
        lines.append(f"\n— {cat} —")
        for it in rows:
            lines.append(f"{n}. {it['text']} — {it.get('who','')}")
            n += 1
    return "\n".join(lines)

# ====== Keyboards ======
def build_done_keyboard(list_name: str = "default") -> InlineKeyboardMarkup | None:
    items = get_items(list_name)
    if not items:
        return None
    # toon knoppen in de volgorde van render (per item-index)
    rows: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for idx, it in enumerate(items, start=1):
        row.append(InlineKeyboardButton(f"✓ {idx}", callback_data=f"done:{list_name}:{it.doc_id}"))
        if len(row) == 3:
            rows.append(row); row=[]
    if row: rows.append(row)
    return InlineKeyboardMarkup(rows)

def build_quick_add_keyboard() -> ReplyKeyboardMarkup:
    # Snelle knoppen: pas gerust aan
    r1 = ["Brood", "Melk", "Bananen"]
    r2 = ["Pasta", "Rijst", "WC-papier"]
    r3 = ["menu: Soep", "menu: Curry", "menu: Lasagne"]
    r4 = ["cat: Groente & Fruit", "cat: Zuivel & Eieren", "cat: Huishoudelijk"]
    layout = [
        [KeyboardButton(x) for x in r1],
        [KeyboardButton(x) for x in r2],
        [KeyboardButton(x) for x in r3],
        [KeyboardButton(x) for x in r4],
    ]
    return ReplyKeyboardMarkup(layout, resize_keyboard=True)

# ====== Helpers ======
def chat_allowed(update: Update) -> bool:
    if ALLOWED_CHAT_ID is None:
        return True
    cid = update.effective_chat.id if update.effective_chat else None
    return cid == ALLOWED_CHAT_ID

def parse_setcat_args(args: List[str]) -> tuple[int | None, str | None]:
    # /setcat 3 "Groente & Fruit"
    if not args or len(args) < 2:
        return None, None
    try:
        idx = int(args[0])
    except ValueError:
        return None, None
    cat = " ".join(args[1:]).strip('"')
    return idx, cat

# ====== Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update):
        return
    text = (
        "Ik hou je lijsten en categorieën bij.\n"
        "• Gewoon typen → Boodschappen (auto-categorie)\n"
        "• ‘menu: …’ → naar Weekmenu\n"
        "• ‘cat: <Categorie>’ zet je invoercategorie (voor volgende items)\n"
        "• /list (/list weekmenu) toont gegroepeerd per categorie + ✓-knoppen\n"
        "• /setcat <nummer> <Categorie> zet categorie van een bestaand item\n"
        "• /clear (/clear weekmenu) leegt de lijst"
    )
    await update.message.reply_text(text, reply_markup=build_quick_add_keyboard())
    context.user_data.setdefault("current_cat", None)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update): return
    if not context.args: return await update.message.reply_text("Gebruik: /add melk")
    who = update.effective_user.first_name
    cur_cat = context.user_data.get("current_cat")
    add_item(" ".join(context.args), who, "default", cur_cat)
    await update.message.reply_text("Toegevoegd aan Boodschappen.")

async def menu_add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update): return
    if not context.args: return await update.message.reply_text("Gebruik: /menuadd lasagne")
    who = update.effective_user.first_name
    add_item(" ".join(context.args), who, "weekmenu")
    await update.message.reply_text("Toegevoegd aan Weekmenu.")

async def setcat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /setcat 3 Groente & Fruit  — zet categorie van item #3 (in huidige /list) """
    if not chat_allowed(update): return
    idx, cat = parse_setcat_args(context.args)
    if idx is None or not cat or cat not in CATEGORIES:
        return await update.message.reply_text(f"Gebruik: /setcat <nummer> <Categorie>\nCategorieën: {', '.join(CATEGORIES)}")
    # vind item nummer idx in de "default" lijst (eenvoudig: op huidige data-volgorde)
    items = get_items("default")
    if not (1 <= idx <= len(items)):
        return await update.message.reply_text("Nummer bestaat niet.")
    it = items[idx-1]
    db.update({"cat": cat}, doc_ids=[it.doc_id])
    await update.message.reply_text(f"Categorie van '{it['text']}' → {cat}")

async def show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update): return
    list_name = "default"
    if context.args and context.args[0].lower() == "weekmenu":
        list_name = "weekmenu"
    await update.message.reply_text(
        render_list(list_name),
        reply_markup=build_done_keyboard(list_name),
    )

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update): return
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
    if not chat_allowed(update): return
    txt = (update.message.text or "").strip()
    who = update.effective_user.first_name
    if not txt: return

    # Snel categorie instellen voor volgende items via "cat: <Categorie>"
    if txt.lower().startswith("cat:"):
        cat = txt.split(":",1)[1].strip()
        if cat in CATEGORIES:
            context.user_data["current_cat"] = cat
            return await update.message.reply_text(f"Invoercategorie gezet op: {cat}")
        else:
            return await update.message.reply_text(f"Onbekende categorie. Kies uit: {', '.join(CATEGORIES)}")

    # Weekmenu via prefix
    if txt.lower().startswith("menu:"):
        add_item(txt.split(":", 1)[1], who, "weekmenu")
        return await update.message.reply_text("Toegevoegd aan Weekmenu.", reply_markup=build_quick_add_keyboard())

    # Normale toevoeging (boodschappen) met huidige gekozen categorie (indien gezet)
    cur_cat = context.user_data.get("current_cat")
    add_item(txt, who, "default", cur_cat)
    await update.message.reply_text(f"Toegevoegd: {txt}", reply_markup=build_quick_add_keyboard())

# ====== Main ======
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("menuadd", menu_add_cmd))
    app.add_handler(CommandHandler("setcat", setcat_cmd))
    app.add_handler(CommandHandler("list", show))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text))
    app.run_polling(allowed_updates=["message","callback_query"])

if __name__ == "__main__":
    main()