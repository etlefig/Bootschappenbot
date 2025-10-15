import os, sys
from pathlib import Path
from typing import List, Dict
from tinydb import TinyDB, Query
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

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
    "Groente & Fruit": ["tomaat","komkommer","sla","ui","knoflook","wortel","paprika","appel","bananen","champignons", "citroen","limoen","spinazie","avocado","bosui","prei","courgette","broccoli","bloemkool","druif","peer","aardbei", "koriander", "peterselie", "munt", "basilicum"],
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
        for it in rows:
            who = f" — {it['who']}" if it.get("who") else ""
            lines.append(f"- {it['text']}{who}")
    return "\n".join(lines)

# ====== Data ======
db = TinyDB(DB_PATH)
Items = Query()

def add_item(text: str, who: str, list_name: str = "default", category: str | None = None):
    text = text.strip()
    if not text:
        return
    cat = category or guess_category(text)
    db.insert({"text": text, "who": who, "list": list_name, "cat": cat})

def clear_list(list_name: str = "default"):
    db.remove(Items.list == list_name)

# ====== Bot handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "Ik hou je lijsten met categorieën bij (zonder knoppen).\n\n"
        "• Gewoon typen → naar Boodschappen (auto-categorie)\n"
        "• ‘menu: …’ → naar Weekmenu\n"
        "• ‘cat: <Categorie>’ zet je invoercategorie voor volgende items\n"
        "• /list — toon Boodschappen\n"
        "• /list weekmenu — toon Weekmenu\n"
        "• /clear — leeg Boodschappen\n"
        "• /clear weekmenu — leeg Weekmenu\n"
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
    list_name = "default"
    if context.args:
        arg = context.args[0].lower()
        if arg in ["weekmenu", "toko"]:
            list_name = arg
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
    txt = (update.message.text or "").strip()
    who = update.effective_user.first_name
    if not txt:
        return

    # Invoercategorie instellen: "cat: <Categorie>"
    if txt.lower().startswith("cat:"):
        cat = txt.split(":",1)[1].strip()
        if cat in CATEGORIES:
            context.user_data["current_cat"] = cat
            return await update.message.reply_text(f"Invoercategorie gezet op: {cat}")
        else:
            return await update.message.reply_text(f"Onbekende categorie. Kies uit: {', '.join(CATEGORIES)}")

    # Weekmenu via prefix "menu: …"
    if txt.lower().startswith("menu:"):
        add_item(txt.split(":", 1)[1], who, "weekmenu")
        return await update.message.reply_text("Toegevoegd aan Weekmenu.")

    # Anders: Boodschappen (met evt. gekozen categorie)
    cur_cat = context.user_data.get("current_cat")
    add_item(txt, who, "default", cur_cat)
    await update.message.reply_text(f"Toegevoegd aan Boodschappen: {txt}")

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