import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from tinydb import TinyDB, Query

TOKEN = os.environ.get("BOT_TOKEN")  # zet je token in env var
db = TinyDB("list.json")
Items = Query()

def add_item(text, user):
    db.insert({"text": text.strip(), "who": user})

def remove_item(idx):
    items = db.all()
    if 1 <= idx <= len(items):
        db.remove(doc_ids=[items[idx-1].doc_id])
        return True
    return False

def list_items():
    items = db.all()
    if not items: return "📝 Lijst is leeg."
    return "\n".join(f"{i+1}. {it['text']} — {it['who']}" for i, it in enumerate(items))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ik hou je boodschappenlijst bij. /add /list /done /clear")

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Gebruik: /add melk, brood")
    text = " ".join(context.args)
    add_item(text, update.effective_user.first_name)
    await update.message.reply_text(f"Toegevoegd: {text}")

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        return await update.message.reply_text("Gebruik: /done 2  (verwijdert item 2)")
    ok = remove_item(int(context.args[0]))
    await update.message.reply_text("Gefikst." if ok else "Bestaat niet.")

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.truncate()
    await update.message.reply_text("Lijst geleegd.")

async def show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(list_items())

async def plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handig: gewoon typen voegt toe
    add_item(update.message.text, update.effective_user.first_name)
    await update.message.reply_text(f"Toegevoegd: {update.message.text}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("list", show))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text))
    app.run_polling()  # voor lokaal testen; op server kun je webhook gebruiken

if __name__ == "__main__":
    main()