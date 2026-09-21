import os
import random
import logging
from threading import Thread

from flask import Flask

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

KRAIT_HP = 200
NIGHTMARE_HP = 300
DAMAGE = 20

ZONES = {
    "head": "🧠 Голова",
    "body": "🫀 Туловище",
    "legs": "🦵 Ноги",
}

games = {}

# --- Flask-заглушка для Render Web Service ---
web = Flask(__name__)


@web.route("/")
def home():
    return "Krait bot is alive"


def run_web():
    port = int(os.getenv("PORT", 10000))
    web.run(host="0.0.0.0", port=port)


# --- Игровая логика ---

def new_game():
    return {
        "krait_hp": KRAIT_HP,
        "nightmare_hp": NIGHTMARE_HP,
        "nightmare_zone": random.choice(list(ZONES.keys())),
        "combo_progress": 0,
        "stunned": False,
        "phase": "defense",
    }


def status(game):
    return (
        "⚔️ <b>КРАЙТ ПРОТИВ КОШМАРА</b>\n\n"
        f"❤️ Крайт: <b>{game['krait_hp']} HP</b>\n"
        f"👹 Кошмар: <b>{game['nightmare_hp']} HP</b>"
    )


def defense_buttons():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🧠 Голова", callback_data="head"),
            InlineKeyboardButton("🫀 Туловище", callback_data="body"),
        ],
        [
            InlineKeyboardButton("🦵 Ноги", callback_data="legs"),
        ],
    ])


def attack_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Атаковать", callback_data="attack")]
    ])


def stun_attack_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "⚔️ Ударить — Кошмар оглушён",
            callback_data="stun_attack"
        )]
    ])


def new_game_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Новая игра", callback_data="new_game")]
    ])


def update_combo(game, zone):
    """
    Скрытое комбо:
    Голова → Голова → Ноги

    Отдельные успешные элементы игроку не показываются.
    """

    progress = game["combo_progress"]

    if progress == 0:
        if zone == "head":
            game["combo_progress"] = 1
        else:
            game["combo_progress"] = 0

    elif progress == 1:
        if zone == "head":
            game["combo_progress"] = 2
        else:
            game["combo_progress"] = 0

    elif progress == 2:
        if zone == "legs":
            game["combo_progress"] = 0
            return True
        else:
            game["combo_progress"] = 0

    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    games[user_id] = new_game()

    game = games[user_id]

    await update.message.reply_text(
        status(game)
        + "\n\n👹 Кошмар готовится атаковать.\n"
          "Угадай, куда он ударит:",
        parse_mode="HTML",
        reply_markup=defense_buttons(),
    )


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 <b>ПРАВИЛА</b>\n\n"
        "❤️ Крайт — 200 HP\n"
        "👹 Кошмар — 300 HP\n"
        "⚔️ Оба наносят 20 урона.\n\n"
        "Кошмар каждый ход выбирает:\n"
        "🧠 голову\n"
        "🫀 туловище\n"
        "🦵 ноги\n\n"
        "Ты должен угадать его атаку.\n\n"
        "✅ Угадал — получаешь 0 урона.\n"
        "❌ Не угадал — получаешь 20 урона.\n\n"
        "🔥 Скрытое комбо:\n"
        "<b>Голова → Голова → Ноги</b>\n\n"
        "Игрок не видит отдельные элементы комбо.\n"
        "После полного комбо Кошмар получает стан.\n"
        "На следующем ходу он не атакует и не защищается.\n"
        "Крайт получает гарантированный удар на 20 урона.\n\n"
        "🏆 Побеждает тот, кто первым уничтожит противника.",
        parse_mode="HTML",
    )


async def defense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.edit_message_text("Нажми /start, чтобы начать игру.")
        return

    if game["phase"] != "defense":
        await query.answer(
            "Сейчас это действие недоступно.",
            show_alert=True
        )
        return

    chosen = query.data
    nightmare = game["nightmare_zone"]

    if chosen == nightmare:
        result = (
            f"🛡️ <b>БЛОК!</b>\n"
            f"Кошмар бил в {ZONES[nightmare]}.\n"
            "Крайт угадал и не получил урон."
        )
    else:
        game["krait_hp"] -= DAMAGE

        result = (
            f"💥 <b>ПОПАДАНИЕ!</b>\n"
            f"Кошмар бил в {ZONES[nightmare]}.\n"
            f"Крайт выбрал {ZONES[chosen]}.\n"
            f"Крайт получает <b>{DAMAGE} урона</b>."
        )

    if game["krait_hp"] <= 0:
        game["krait_hp"] = 0
        game["phase"] = "finished"

        await query.edit_message_text(
            status(game)
            + "\n\n"
            + result
            + "\n\n💀 <b>КРАЙТ ПРОИГРАЛ!</b>",
            parse_mode="HTML",
            reply_markup=new_game_button(),
        )
        return

    combo = update_combo(game, chosen)

    if combo:
        game["stunned"] = True

        result += (
            "\n\n🔥 <b>КОМБО ВЫПОЛНЕНО!</b>\n"
            "👹 Кошмар оглушён.\n"
            "На следующем ходу он не сможет атаковать или защищаться."
        )

    game["phase"] = "attack"

    await query.edit_message_text(
        status(game)
        + "\n\n"
        + result
        + "\n\n⚔️ Теперь атакуй Кошмара.",
        parse_mode="HTML",
        reply_markup=attack_button(),
    )


async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.edit_message_text("Нажми /start.")
        return

    if game["phase"] != "attack":
        await query.answer(
            "Сейчас это действие недоступно.",
            show_alert=True
        )
        return

    game["nightmare_hp"] -= DAMAGE

    if game["nightmare_hp"] <= 0:
        game["nightmare_hp"] = 0
        game["phase"] = "finished"

        await query.edit_message_text(
            status(game)
            + "\n\n⚔️ Крайт наносит 20 урона.\n"
              "🏆 <b>КРАЙТ ПОБЕДИЛ!</b>",
            parse_mode="HTML",
            reply_markup=new_game_button(),
        )
        return

    if game["stunned"]:
        game["phase"] = "stun_attack"

        await query.edit_message_text(
            status(game)
            + "\n\n⚔️ Крайт наносит <b>20 урона</b>.\n\n"
              "🔥 <b>КОШМАР ОГЛУШЁН!</b>\n"
              "Он не атакует и не защищается.\n\n"
              "⚔️ Нанеси ему гарантированный удар:",
            parse_mode="HTML",
            reply_markup=stun_attack_button(),
        )
        return

    next_turn(game)

    await query.edit_message_text(
        status(game)
        + "\n\n👹 Кошмар готовится атаковать.\n"
          "Угадай, куда он ударит:",
        parse_mode="HTML",
        reply_markup=defense_buttons(),
    )


async def stun_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.edit_message_text("Нажми /start.")
        return

    if game["phase"] != "stun_attack":
        await query.answer(
            "Сейчас это действие недоступно.",
            show_alert=True
        )
        return

    game["nightmare_hp"] -= DAMAGE
    game["stunned"] = False

    if game["nightmare_hp"] <= 0:
        game["nightmare_hp"] = 0
        game["phase"] = "finished"

        await query.edit_message_text(
            status(game)
            + "\n\n⚔️ Гарантированный удар: <b>20 урона</b>.\n"
              "🏆 <b>КРАЙТ ПОБЕДИЛ!</b>",
            parse_mode="HTML",
            reply_markup=new_game_button(),
        )
        return

    next_turn(game)

    await query.edit_message_text(
        status(game)
        + "\n\n🔥 Стан закончился.\n"
          "👹 Кошмар снова атакует.\n"
          "Угадай, куда он ударит:",
        parse_mode="HTML",
        reply_markup=defense_buttons(),
    )


def next_turn(game):
    game["nightmare_zone"] = random.choice(list(ZONES.keys()))
    game["phase"] = "defense"


async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    games[user_id] = new_game()

    game = games[user_id]

    await query.edit_message_text(
        status(game)
        + "\n\n👹 <b>НОВАЯ БИТВА!</b>\n"
          "Угадай, куда ударит Кошмар:",
        parse_mode="HTML",
        reply_markup=defense_buttons(),
    )


def main():
    if not TOKEN:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Добавь токен в переменные окружения."
        )

    # Запускаем Flask-заглушку в отдельном потоке,
    # чтобы Render Web Service видел открытый порт.
    Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rules", rules))

    app.add_handler(
        CallbackQueryHandler(
            defense,
            pattern="^(head|body|legs)$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            attack,
            pattern="^attack$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            stun_attack,
            pattern="^stun_attack$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            new_game,
            pattern="^new_game$"
        )
    )

    print("Крайт против Кошмара запущен!")

    app.run_polling()


if __name__ == "__main__":
    main()
