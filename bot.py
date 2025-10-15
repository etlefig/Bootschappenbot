import os, sys
from pathlib import Path
from typing import List, Dict
import re
from tinydb import TinyDB, Query
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
print("🚀 Nieuwe versie geladen!")

# ====== Config ======
BASE = Path(__file__).parent
DB_PATH = BASE / "list.json"

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN or ":" not in TOKEN:
    print("ERROR: BOT_TOKEN ontbreekt of lijkt ongeldig.", file=sys.stderr)
    sys.exit(1)

# ====== Categorieën ======
CATEGORIES = [
    "Groente & Fruit", "Brood & Banket", "Zuivel & Eieren",
    "Vlees/Vis/Vega", "Droge Waren", "Toko",
    "Diepvries", "Drinken", "Huishoudelijk",
    "Drogist", "Overig",
]

KEYWORDS: Dict[str, List[str]] = {
    "Groente & Fruit": ["tomaten","komkommer","sla","ui","knoflook","wortels","paprika","appels","bananen","champignons", "kastanjechampignons", "citroen","limoen","spinazie","avocado","bosui","prei","courgette","broccoli","bloemkool","druiven","peer","peren", "aardbeien", "koriander", "peterselie", "munt", "basilicum"],
    "Brood & Banket": ["brood","pistolet","tortilla","wrap","bagel","croissant","bol","pita","naan"],
    "Zuivel & Eieren": ["melk","sojamelk","havermelk","yoghurt","kwark","room","slagroom","boter","kaas","parmezaan","eieren","ei"],
    "Vlees/Vis/Vega": ["kip","gehakt","rund","biefstuk","spek","tonijn","zalm","vis","vegetarisch","tofu","tempeh","falafel","vegaburger"],
    "Droge Waren": ["pasta","rijst","quinoa","couscous","bulgur","meel","bloem","havermout","suiker","zout","peper","panko","bouillon","kruiden","specerijen","olie","olijfolie","azijn","sojasaus","ketjap","tomatenpuree","bonen","kikkererwten"],
    "Diepvries": ["diepvries","ijs","diepvriesgroente","erwten","spinazie diepvries","pizza diepvries"],
    "Drinken": ["sap","fris","cola","limonade","bier","wijn","koffie","thee"],
    "Huishoudelijk": ["wc-papier","keukenrol","afwasmiddel","bleek","alcohol schoonmaak","schoonmaak","afvalzak","spons","wasmiddel","wasverzachter","vaatwastablet","wasparfum"],
    "Drogist": ["tandpasta","shampoo","zeep","douchegel","scheermes","crème","luiers","billendoekjes","deo"],
    "Overig": [],
    "Toko": ["sambal", "ketjap", "sojasaus", "kokosmelk", "rijstpapier", "rijstnoedels",
    "mirin", "miso", "gochujang", "nori", "tamarinde", "limoenblad",
    "laos", "gember", "sereh", "citroengras", "trassi", "tempeh",
    "sriracha", "chili", "chilipasta", "kroepoek", "rijst"
],
}

# ====== Helpers ======
def guess_category(text: str) -> str:
    t = text.lower()
    for cat, kws in KEYWORDS.items():
        for k in kws:
            if k in t:
                return cat
    return "Overig"

def title_for(list_name: str) -> str:
    if list_name == "weekmenu":
        return "Weekmenu"
    elif list_name == "toko":
        return "Toko"
    return "Boodschappen"

def group_by_category(items) -> Dict[str, List[dict]]:
    grouped: Dict[str, List[dict]] = {c: [] for c in CATEGORIES}
    for it in items:
        grouped.setdefault(it.get("cat","Overig"), []).append(it)
    return {c: grouped[c] for c in CATEGORIES if grouped.get(c)}

def render_list(db, list_name: str = "default") -> str:
    Items = Query()
    items = db.search(Items.list == list_name)
    if not items:
        return f"{title_for(list_name)} is leeg."
    grouped = group_by_category(items)
    lines = [f"{title_for(list_name)}"]
    for cat, rows in grouped.items():
        lines.append(f"\n— {cat} —")
        open_rows = [it for it in rows if not it.get("done")]
        done_rows = [it for it in rows if it.get("done")]
        for it in open_rows:
            who = f" — {it['who']}" if it.get("who") else ""
            lines.append(f"- {it['text']}{who}")
        for it in done_rows:
            who = f" — {it['who']}" if it.get("who") else ""
            lines.append(f"- ✅ {it['text']}{who}")
    return "\n".join(lines)

# ====== Data ======
db = TinyDB(DB_PATH)
Items = Query()

def add_item(text: str, who: str, list_name: str = "default", category: str | None = None):
    text = text.strip()
    if not text:
        return
    cat = category or guess_category(text)
    db.insert({"text": text, "who": who, "list": list_name, "cat": cat, "done": False})

def clear_list(list_name: str = "default"):
    db.remove(Items.list == list_name)

def mark_done(query_text: str) -> str | None:
    """Markeer het eerste item dat query_text bevat als done=True over alle lijsten."""
    q = (query_text or "").lower().strip()
    if not q:
        return None
    for it in db.all():
        if q in (it.get("text", "").lower()):
            db.update({"done": True}, doc_ids=[it.doc_id])
            return f"Afgevinkt: {it['text']} ({title_for(it.get('list','default'))})"
    return None

def clear_done(list_name: str | None = None) -> int:
    """Verwijder done=True items. Als list_name gezet is, alleen die lijst."""
    if list_name:
        docs = db.search((Items.list == list_name) & (Items.done == True))
    else:
        docs = db.search(Items.done == True)
    count = len(docs)
    db.remove(doc_ids=[d.doc_id for d in docs])
    return count

# ====== Bot handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "Ik hou je boodschappenlijst bij. Er is een lijst voor Boodschappen, een lijst voor Toko en een lijst voor het Weekmenu.\n\n"
        "• Gewoon typen → naar Boodschappen (auto-categorie)\n"
        "• ‘menu: …’ → naar Weekmenu\n"
        "• ‘toko: …’ → naar Toko\n"

        "• ‘cat: <Categorie>’ zet je invoercategorie voor volgende items\n"
        "• ‘cat:’ zonder categorie wist de invoercategorie\n"
        "• ‘<item> cat: <Categorie>’ voeg <item> toe aan Boodschappen met <Categorie>\n"

        "• ‘done: <tekst>’ vink het eerste item met <tekst> af\n\n"

        "Commands:\n"
        "• /add <item> — voeg toe aan Boodschappen\n"
        "• /menuadd <item> — voeg toe aan Weekmenu\n"

        "• /list — toon Boodschappen\n"
        "• /list weekmenu — toon Weekmenu\n"
        "• /list toko — toon Toko\n"

        "• /clear — leeg Boodschappen\n"
        "• /clear weekmenu — leeg Weekmenu\n"
        "• /clear done — verwijder alle afgevinkte items\n"
        "• /clear done weekmenu — verwijder afgevinkte items uit Weekmenu\n"

        "Categorieën: " + ", ".join(CATEGORIES)
    )
    await update.message.reply_text(msg)
    context.user_data.setdefault("current_cat", None)

async def list_cmd(update, context):
    list_name = "default"
    if context.args:
        arg = context.args[0].lower()
        if arg in ["weekmenu", "toko"]:
            list_name = arg
    await update.message.reply_text(render_list(db, list_name))

async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /clear, /clear weekmenu, /clear toko, /clear done, /clear done weekmenu
    args = [a.lower() for a in (context.args or [])]
    if args and args[0] == "done":
        target = args[1] if len(args) > 1 and args[1] in ["weekmenu", "toko", "default"] else None
        removed = clear_done(target)
        label = title_for(target) if target else "alle lijsten"
        return await update.message.reply_text(f"Verwijderd (done) uit {label}: {removed} items.")
    list_name = "default"
    if args and args[0] in ["weekmenu", "toko"]:
        list_name = args[0]
    clear_list(list_name)
    await update.message.reply_text(f"{title_for(list_name)} geleegd.")

async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Gebruik: /add melk")
    who = update.effective_user.first_name
    cur_cat = context.user_data.get("current_cat")
    add_item(" ".join(context.args), who, "default", cur_cat)
    await update.message.reply_text("Toegevoegd aan Boodschappen.")

async def menu_add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Gebruik: /menuadd lasagne")
    who = update.effective_user.first_name
    add_item(" ".join(context.args), who, "weekmenu")
    await update.message.reply_text("Toegevoegd aan Weekmenu.")

async def plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt_raw = (update.message.text or "")
    who = update.effective_user.first_name
    # Normaliseer whitespace
    txt_norm = re.sub(r"\s+", " ", txt_raw).strip()
    low = txt_norm.lower()

    # Done: markeer item op basis van tekst
    m = re.match(r"^\s*done\s*[:：]\s*(.+)$", low)
    if m:
        original = re.match(r"^\s*done\s*[:：]\s*(.+)$", txt_norm, flags=re.IGNORECASE).group(1).strip()
        msg = mark_done(original)
        if msg:
            return await update.message.reply_text(msg)
        else:
            return await update.message.reply_text(f"Geen match gevonden voor: {original}")

    # 0) Item + directe categorie, bijv. "melk cat: Zuivel & Eieren"
    m_direct = re.match(r"^(.*?)\s+cat\s*[:：]\s*(.+)$", txt_norm, flags=re.IGNORECASE)
    if m_direct:
        item_text = m_direct.group(1).strip()
        cat_name = m_direct.group(2).strip()
        if cat_name in CATEGORIES and item_text:
            # standaard naar boodschappenlijst (default)
            add_item(item_text, who, "default", cat_name)
            return await update.message.reply_text(f"Toegevoegd aan Boodschappen ({cat_name}): {item_text}")
        else:
            return await update.message.reply_text(f"Onbekende categorie of leeg item. Kies uit: {', '.join(CATEGORIES)}")

    # 1) Invoercategorie via "cat: <Categorie>"
    m = re.match(r"^\s*cat\s*[:：]\s*(.+)$", low)
    if m:
        cat_original = re.match(r"^\s*cat\s*[:：]\s*(.+)$", txt_norm, flags=re.IGNORECASE).group(1).strip()
        cat_clean = cat_original.strip()
        if cat_clean in CATEGORIES:
            context.user_data["current_cat"] = cat_clean
            return await update.message.reply_text(f"Invoercategorie gezet op: {cat_clean}")
        else:
            return await update.message.reply_text(f"Onbekende categorie. Kies uit: {', '.join(CATEGORIES)}")

    # 2) Weekmenu via "menu: ..." (tolerant voor spaties en alternatieve dubbelepunt)
    m = re.match(r"^\s*menu\s*[:：]\s*(.+)$", low)
    if m:
        payload = re.match(r"^\s*menu\s*[:：]\s*(.+)$", txt_norm, flags=re.IGNORECASE).group(1).strip()
        add_item(payload, who, "weekmenu")
        return await update.message.reply_text("Toegevoegd aan Weekmenu.")

    # 3) Toko via "toko: ..." (tolerant)
    m = re.match(r"^\s*toko\s*[:：]\s*(.+)$", low)
    if m:
        payload = re.match(r"^\s*toko\s*[:：]\s*(.+)$", txt_norm, flags=re.IGNORECASE).group(1).strip()
        add_item(payload, who, "toko")
        return await update.message.reply_text("Toegevoegd aan Toko.")

    # 4) Anders: Boodschappen (met evt. gekozen categorie)
    cur_cat = context.user_data.get("current_cat")
    add_item(txt_norm, who, "default", cur_cat)
    await update.message.reply_text(f"Toegevoegd aan Boodschappen: {txt_norm}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("menuadd", menu_add_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text))
    app.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()