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


# --- Описание игры (общее для /start и /rules) ---

GAME_DESCRIPTION = (
    "⚔️ <b>КРАЙТ ПРОТИВ КОШМАРА</b>\n\n"
    "Ты — Крайт. Твой противник — Кошмар.\n"
    "Бой пошаговый. Побеждает тот, кто первым\n"
    "отправит противника на 0 HP.\n\n"
    "❤️ У тебя <b>200 HP</b>\n"
    "👹 У Кошмара <b>300 HP</b>\n"
    "⚔️ Оба наносят по <b>20 урона</b>\n\n"
    "📍 Зоны удара: 🧠 голова, 🫀 туловище, 🦵 ноги\n\n"
    "<b>КАК ИДЁТ ХОД:</b>\n"
    "1. Ты выбираешь, куда атаковать.\n"
    "2. Кошмар скрыто выбирает, куда защищаться.\n"
    "3. Ты выбираешь, куда блокировать.\n"
    "4. Кошмар скрыто выбирает, куда атаковать.\n"
    "5. Показывается итог хода.\n\n"
    "✅ Зоны совпали — блок, 0 урона.\n"
    "❌ Не совпали — 20 урона.\n\n"
    "🔥 <b>СЕКРЕТНОЕ КОМБО</b>\n\n"
    "В каждой битве спрятано своё комбо из трёх\n"
    "ударов подряд. Угадаешь последовательность —\n"
    "Кошмар будет оглушён на следующий ход: он не\n"
    "сможет ни атаковать, ни защищаться, а ты\n"
    "нанесёшь гарантированный удар.\n\n"
    "Любая ошибка — сброс, начинай заново.\n"
    "Последовательность не подскажем — ищи сам.\n\n"
    "🏆 Победа: Кошмар 0 HP.\n"
    "💀 Поражение: Крайт 0 HP.\n"
    "🤝 Если у обоих 0 HP — поражение Крайта."
)


# --- Игровая логика ---

def generate_combo():
    """Случайная последовательность из 3 зон, кроме трёх одинаковых."""
    zones = list(ZONES.keys())
    while True:
        seq = [random.choice(zones) for _ in range(3)]
        if not (seq[0] == seq[1] == seq[2]):
            return seq


def create_game():
    return {
        "krait_hp": KRAIT_HP,
        "nightmare_hp": NIGHTMARE_HP,
        "nightmare_defense": random.choice(list(ZONES.keys())),
        "nightmare_attack": random.choice(list(ZONES.keys())),
        "krait_attack": None,
        "krait_defense": None,
        "combo": generate_combo(),
        "combo_progress": 0,
        "combo_revealed": False,
        "stunned": False,
        "phase": "attack",
    }


def status(game):
    return (
        "⚔️ <b>КРАЙТ ПРОТИВ КОШМАРА</b>\n\n"
        f"❤️ Крайт: <b>{game['krait_hp']} HP</b>\n"
        f"👹 Кошмар: <b>{game['nightmare_hp']} HP</b>"
    )


def zone_buttons(callback_prefix):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🧠 Голова", callback_data=f"{callback_prefix}:head"),
            InlineKeyboardButton("🫀 Туловище", callback_data=f"{callback_prefix}:body"),
        ],
        [
            InlineKeyboardButton("🦵 Ноги", callback_data=f"{callback_prefix}:legs"),
        ],
    ])


def new_game_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Новая игра", callback_data="new_game")]
    ])


def intro_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Начать бой", callback_data="begin_battle")]
    ])


def combo_to_text(seq):
    """Превращает последовательность зон в читаемый текст."""
    return " → ".join(ZONES[z] for z in seq)


def update_combo(game, zone):
    """
    Скрытое комбо. Последовательность — game["combo"].
    Любое отклонение → сброс в 0 (новая попытка с нуля).
    """
    progress = game["combo_progress"]
    seq = game["combo"]

    if progress < 3 and zone == seq[progress]:
        game["combo_progress"] += 1
        if game["combo_progress"] == 3:
            game["combo_progress"] = 0
            return True
    else:
        # Сброс. Если первый элемент последовательности совпал —
        # начинаем новую попытку с 1.
        if zone == seq[0]:
            game["combo_progress"] = 1
        else:
            game["combo_progress"] = 0

    return False


def format_attack_result(game):
    krait_zone = game["krait_attack"]
    nightmare_def = game["nightmare_defense"]

    if krait_zone == nightmare_def:
        return (
            f"⚔️ Крайт ударил в {ZONES[krait_zone]} — "
            f"👹 Кошмар заблокировал (0 урона)."
        )
    else:
        return (
            f"⚔️ Крайт ударил в {ZONES[krait_zone]} — попал! "
            f"👹 Кошмар получил {DAMAGE} урона."
        )


def format_defense_result(game):
    nightmare_atk = game["nightmare_attack"]
    krait_zone = game["krait_defense"]

    if krait_zone == nightmare_atk:
        return (
            f"👹 Кошмар ударил в {ZONES[nightmare_atk]} — "
            f"🛡️ Крайт заблокировал (0 урона)."
        )
    else:
        return (
            f"👹 Кошмар ударил в {ZONES[nightmare_atk]} — попал! "
            f"❤️ Крайт получил {DAMAGE} урона."
        )


def apply_results(game):
    attack_text = format_attack_result(game)
    defense_text = format_defense_result(game)

    if game["krait_attack"] != game["nightmare_defense"]:
        game["nightmare_hp"] -= DAMAGE

    if game["krait_defense"] != game["nightmare_attack"]:
        game["krait_hp"] -= DAMAGE

    if game["krait_hp"] < 0:
        game["krait_hp"] = 0
    if game["nightmare_hp"] < 0:
        game["nightmare_hp"] = 0

    return attack_text, defense_text


def next_turn(game):
    game["nightmare_defense"] = random.choice(list(ZONES.keys()))
    game["nightmare_attack"] = random.choice(list(ZONES.keys()))
    game["krait_attack"] = None
    game["krait_defense"] = None
    game["phase"] = "attack"
    game["stunned"] = False


def check_end(game):
    if game["krait_hp"] <= 0 and game["nightmare_hp"] <= 0:
        game["phase"] = "finished"
        return "lose"
    if game["krait_hp"] <= 0:
        game["phase"] = "finished"
        return "lose"
    if game["nightmare_hp"] <= 0:
        game["phase"] = "finished"
        return "win"
    return None


# --- Хэндлеры ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in games and games[user_id]["phase"] != "finished":
        games[user_id] = create_game()
        game = games[user_id]
        await update.message.reply_text(
            status(game)
            + "\n\n⚔️ <b>Твой ход!</b>\n"
              "Выбери, куда атаковать Кошмара:",
            parse_mode="HTML",
            reply_markup=zone_buttons("attack"),
        )
        return

    await update.message.reply_text(
        GAME_DESCRIPTION,
        parse_mode="HTML",
        reply_markup=intro_button(),
    )


async def begin_battle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    games[user_id] = create_game()
    game = games[user_id]

    await query.edit_message_text(
        status(game)
        + "\n\n⚔️ <b>Твой ход!</b>\n"
          "Выбери, куда атаковать Кошмара:",
        parse_mode="HTML",
        reply_markup=zone_buttons("attack"),
    )


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        GAME_DESCRIPTION,
        parse_mode="HTML",
    )


async def attack_phase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.edit_message_text("Нажми /start, чтобы начать игру.")
        return

    if game["phase"] != "attack":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    zone = query.data.split(":")[1]
    game["krait_attack"] = zone

    combo = update_combo(game, zone)
    if combo:
        game["stunned"] = True

    game["phase"] = "defense"

    await query.edit_message_text(
        status(game)
        + "\n\n🛡️ Теперь выбери, куда блокировать удар Кошмара:",
        parse_mode="HTML",
        reply_markup=zone_buttons("defense"),
    )


async def defense_phase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.edit_message_text("Нажми /start.")
        return

    if game["phase"] != "defense":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    zone = query.data.split(":")[1]
    game["krait_defense"] = zone

    attack_text, defense_text = apply_results(game)

    text = status(game) + "\n\n" + attack_text + "\n" + defense_text

    end = check_end(game)
    if end == "win":
        text += "\n\n🏆 <b>КРАЙТ ПОБЕДИЛ!</b>"
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=new_game_button()
        )
        return
    elif end == "lose":
        text += "\n\n💀 <b>КРАЙТ ПРОИГРАЛ!</b>"
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=new_game_button()
        )
        return

    if game["stunned"]:
        combo_text = "\n\n🔥 <b>КОМБО ВЫПОЛНЕНО!</b>"
        if not game["combo_revealed"]:
            combo_text += (
                f"\nПоследовательность: <b>{combo_to_text(game['combo'])}</b>"
            )
            game["combo_revealed"] = True
        combo_text += (
            "\n\n👹 Кошмар оглушён на следующий ход.\n"
            "Он не атакует и не защищается.\n\n"
            "⚔️ Нанеси гарантированный удар:"
        )
        text += combo_text
        game["phase"] = "stun_attack"
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=zone_buttons("stun_attack")
        )
        return

    next_turn(game)
    text += "\n\n⚔️ <b>Твой ход!</b>\nВыбери, куда атаковать Кошмара:"
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=zone_buttons("attack")
    )


async def stun_attack_phase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.edit_message_text("Нажми /start.")
        return

    if game["phase"] != "stun_attack":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    zone = query.data.split(":")[1]

    game["nightmare_hp"] -= DAMAGE
    if game["nightmare_hp"] < 0:
        game["nightmare_hp"] = 0

    text = (
        status(game)
        + f"\n\n⚔️ Крайт ударил в {ZONES[zone]} — "
          f"Кошмар оглушён и не защищался.\n"
          f"<b>{DAMAGE} урона!</b>"
    )

    end = check_end(game)
    if end == "win":
        text += "\n\n🏆 <b>КРАЙТ ПОБЕДИЛ!</b>"
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=new_game_button()
        )
        return

    game["stunned"] = False
    next_turn(game)

    text += "\n\n🔥 Стан закончился.\n⚔️ <b>Твой ход!</b>\nВыбери, куда атаковать Кошмара:"
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=zone_buttons("attack")
    )


async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    games[user_id] = create_game()
    game = games[user_id]

    await query.edit_message_text(
        status(game)
        + "\n\n👹 <b>НОВАЯ БИТВА!</b>\n"
          "⚔️ Выбери, куда атаковать Кошмара:",
        parse_mode="HTML",
        reply_markup=zone_buttons("attack"),
    )


def main():
    if not TOKEN:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Добавь токен в переменные окружения."
        )

    Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rules", rules))

    app.add_handler(CallbackQueryHandler(begin_battle, pattern=r"^begin_battle$"))
    app.add_handler(CallbackQueryHandler(attack_phase, pattern=r"^attack:"))
    app.add_handler(CallbackQueryHandler(defense_phase, pattern=r"^defense:"))
    app.add_handler(CallbackQueryHandler(stun_attack_phase, pattern=r"^stun_attack:"))
    app.add_handler(CallbackQueryHandler(new_game, pattern=r"^new_game$"))

    print("Крайт против Кошмара запущен!")

    app.run_polling()


if __name__ == "__main__":
    main()
