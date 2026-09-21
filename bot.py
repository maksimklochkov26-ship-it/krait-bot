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

def create_game():
    return {
        "krait_hp": KRAIT_HP,
        "nightmare_hp": NIGHTMARE_HP,
        # скрытая защита Кошмара (на фазу атаки игрока)
        "nightmare_defense": random.choice(list(ZONES.keys())),
        # скрытая атака Кошмара (на фазу защиты игрока)
        "nightmare_attack": random.choice(list(ZONES.keys())),
        # что игрок выбрал в текущем ходу
        "krait_attack": None,
        "krait_defense": None,
        # комбо
        "combo_progress": 0,
        # стан
        "stunned": False,
        # фаза: "attack" | "defense" | "stun_attack" | "finished"
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


def update_combo(game, zone):
    """
    Скрытое комбо: голова → голова → ноги (по зонам атаки).

    Любое отклонение → сброс в 0 (новая попытка с нуля).
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


def format_attack_result(game):
    """Результат атаки Крайта по Кошмару."""
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
    """Результат атаки Кошмара по Крайту."""
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
    """Применяем урон, возвращаем тексты результатов."""
    attack_text = format_attack_result(game)
    defense_text = format_defense_result(game)

    # урон по Кошмару
    if game["krait_attack"] != game["nightmare_defense"]:
        game["nightmare_hp"] -= DAMAGE

    # урон по Крайту
    if game["krait_defense"] != game["nightmare_attack"]:
        game["krait_hp"] -= DAMAGE

    if game["krait_hp"] < 0:
        game["krait_hp"] = 0
    if game["nightmare_hp"] < 0:
        game["nightmare_hp"] = 0

    return attack_text, defense_text


def next_turn(game):
    """Готовим новый обычный ход."""
    game["nightmare_defense"] = random.choice(list(ZONES.keys()))
    game["nightmare_attack"] = random.choice(list(ZONES.keys()))
    game["krait_attack"] = None
    game["krait_defense"] = None
    game["phase"] = "attack"
    game["stunned"] = False


def check_end(game):
    """Возвращает True, если игра закончена (и выставляет phase)."""
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
    games[user_id] = create_game()
    game = games[user_id]

    await update.message.reply_text(
        status(game)
        + "\n\n⚔️ <b>Твой ход!</b>\n"
          "Выбери, куда атаковать Кошмара:",
        parse_mode="HTML",
        reply_markup=zone_buttons("attack"),
    )


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 <b>ПРАВИЛА</b>\n\n"
        "❤️ Крайт — 200 HP\n"
        "👹 Кошмар — 300 HP\n"
        "⚔️ Оба наносят 20 урона.\n\n"
        "📍 Зоны: 🧠 голова, 🫀 туловище, 🦵 ноги.\n\n"
        "<b>Ход:</b>\n"
        "1. Ты выбираешь, куда атаковать.\n"
        "2. Кошмар скрыто выбирает, куда защищаться.\n"
        "3. Ты выбираешь, куда блокировать.\n"
        "4. Кошмар скрыто выбирает, куда атаковать.\n"
        "5. Показывается итог хода.\n\n"
        "✅ Если зоны совпали — блок, 0 урона.\n"
        "❌ Если не совпали — 20 урона.\n\n"
        "🔥 <b>Скрытое комбо:</b>\n"
        "<b>Голова → Голова → Ноги</b> (по зонам атаки)\n\n"
        "Комбо копится, даже если Кошмар блокирует.\n"
        "Любая ошибка — сброс.\n"
        "После комбо Кошмар оглушён на следующий ход:\n"
        "он не атакует и не защищается, а Крайт наносит\n"
        "гарантированный удар на 20 урона.\n\n"
        "🏆 Победа: Кошмар 0 HP.\n"
        "💀 Поражение: Крайт 0 HP.\n"
        "🤝 Если у обоих 0 HP — поражение Крайта.",
        parse_mode="HTML",
    )


async def attack_phase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Игрок выбрал зону атаки."""
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

    # Комбо копится здесь (скрыто от игрока)
    combo = update_combo(game, zone)

    if combo:
        game["stunned"] = True

    game["phase"] = "defense"

    # Показываем фазу защиты — без результата атаки
    await query.edit_message_text(
        status(game)
        + "\n\n🛡️ Теперь выбери, куда блокировать удар Кошмара:",
        parse_mode="HTML",
        reply_markup=zone_buttons("defense"),
    )


async def defense_phase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Игрок выбрал зону блока → показываем итог хода."""
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

    # Применяем результаты хода
    attack_text, defense_text = apply_results(game)

    # Формируем итоговое сообщение
    text = status(game) + "\n\n" + attack_text + "\n" + defense_text

    # Проверка конца игры
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

    # Если комбо собралось — стан-ход
    if game["stunned"]:
        text += (
            "\n\n🔥 <b>КОМБО ВЫПОЛНЕНО!</b>\n"
            "👹 Кошмар оглушён на следующий ход.\n"
            "Он не атакует и не защищается.\n\n"
            "⚔️ Нанеси гарантированный удар:"
        )
        game["phase"] = "stun_attack"
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=zone_buttons("stun_attack")
        )
        return

    # Обычный следующий ход
    next_turn(game)
    text += "\n\n⚔️ <b>Твой ход!</b>\nВыбери, куда атаковать Кошмара:"
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=zone_buttons("attack")
    )


async def stun_attack_phase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Гарантированный удар по оглушённому Кошмару."""
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

    # Стан закончился — новый обычный ход
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

    app.add_handler(CallbackQueryHandler(attack_phase, pattern=r"^attack:"))
    app.add_handler(CallbackQueryHandler(defense_phase, pattern=r"^defense:"))
    app.add_handler(CallbackQueryHandler(stun_attack_phase, pattern=r"^stun_attack:"))
    app.add_handler(CallbackQueryHandler(new_game, pattern=r"^new_game$"))

    print("Крайт против Кошмара запущен!")

    app.run_polling()


if __name__ == "__main__":
    main()
