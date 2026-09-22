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
    "1. Ты выбираешь режим: в защиту или без.\n"
    "2. Ты выбираешь, куда атаковать.\n"
    "3. Кошмар скрыто выбирает, куда защищаться.\n"
    "4. Ты выбираешь, куда блокировать.\n"
    "5. Кошмар скрыто выбирает, куда атаковать.\n"
    "6. Показывается итог хода.\n\n"
    "✅ Зоны совпали — блок, 0 урона.\n"
    "❌ Не совпали — урон.\n\n"
    "🛡️ <b>ЗАЩИТНАЯ СТОЙКА</b>\n\n"
    "В начале каждого хода ты выбираешь:\n"
    "встать в защиту или сражаться без неё.\n\n"
    "В защите:\n"
    "— ты наносишь 50% урона (10 вместо 20)\n"
    "— ты получаешь 50% урона (10 вместо 20)\n"
    "— блок по-прежнему даёт 0 урона\n\n"
    "Защита действует весь ход и на атаку, и на блок.\n"
    "Выйти из неё можно только в начале следующего хода.\n\n"
    "🔥 <b>СЕКРЕТНОЕ КОМБО</b>\n\n"
    "В каждой битве спрятано своё комбо из трёх\n"
    "ударов подряд. Угадаешь последовательность —\n"
    "Кошмар будет оглушён на 1 ход: он не сможет\n"
    "ни атаковать, ни защищаться, а ты нанесёшь\n"
    "гарантированный удар.\n\n"
    "Собери комбо — и в стане ты сам решаешь:\n"
    "выйти из защиты и ударить на 100%, или\n"
    "остаться и бить на 50%.\n\n"
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
        "hint_shown": False,
        "in_defense": False,
        "stun_turns": 0,  # сколько ходов стана осталось
        "phase": "choose_mode",  # choose_mode | attack | defense | stun
    }


def status(game):
    mode = "🛡️ Режим: защита" if game["in_defense"] else "⚔️ Режим: без защиты"
    return (
        "⚔️ <b>КРАЙТ ПРОТИВ КОШМАРА</b>\n\n"
        f"❤️ Крайт: <b>{game['krait_hp']} HP</b>\n"
        f"👹 Кошмар: <b>{game['nightmare_hp']} HP</b>\n"
        f"{mode}"
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


def mode_buttons(game):
    """Кнопка переключения режима — одна."""
    if game["in_defense"]:
        label = "⚔️ Выйти из защиты"
        cb = "mode:off"
    else:
        label = "🛡️ Встать в защиту"
        cb = "mode:on"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=cb)]])


def new_game_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Новая игра", callback_data="new_game")]
    ])


def intro_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Начать бой", callback_data="begin_battle")]
    ])


def combo_to_text(seq):
    return " → ".join(ZONES[z] for z in seq)


def update_combo(game, zone):
    """
    Скрытое комбо. Возвращает:
    - 0: прогресс не изменился (сброс или мимо)
    - 1: первый шаг правильный
    - 2: второй шаг правильный
    - 3: комбо собрано
    """
    progress = game["combo_progress"]
    seq = game["combo"]

    if progress < 3 and zone == seq[progress]:
        game["combo_progress"] += 1
        if game["combo_progress"] == 3:
            game["combo_progress"] = 0
            return 3
        return game["combo_progress"]

    # Сброс
    if zone == seq[0]:
        game["combo_progress"] = 1
        return 1
    else:
        game["combo_progress"] = 0
        return 0


def format_attack_result(game, out_of_defense):
    krait_zone = game["krait_attack"]
    nightmare_def = game["nightmare_defense"]

    if krait_zone == nightmare_def:
        return (
            f"⚔️ Крайт ударил в {ZONES[krait_zone]} — "
            f"👹 Кошмар заблокировал (0 урона)."
        )
    else:
        dmg = DAMAGE if out_of_defense else DAMAGE // 2
        return (
            f"⚔️ Крайт ударил в {ZONES[krait_zone]} — попал! "
            f"👹 Кошмар получил {dmg} урона."
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
        dmg = DAMAGE if not game["in_defense"] else DAMAGE // 2
        return (
            f"👹 Кошмар ударил в {ZONES[nightmare_atk]} — попал! "
            f"❤️ Крайт получил {dmg} урона."
        )


def apply_results(game):
    """Применяем результаты хода. Возвращаем тексты."""
    # Урон Крайта по Кошмару
    if game["krait_attack"] != game["nightmare_defense"]:
        if game["in_defense"]:
            game["nightmare_hp"] -= DAMAGE // 2
        else:
            game["nightmare_hp"] -= DAMAGE

    # Урон Кошмара по Крайту
    if game["krait_defense"] != game["nightmare_attack"]:
        if game["in_defense"]:
            game["krait_hp"] -= DAMAGE // 2
        else:
            game["krait_hp"] -= DAMAGE

    if game["krait_hp"] < 0:
        game["krait_hp"] = 0
    if game["nightmare_hp"] < 0:
        game["nightmare_hp"] = 0

    attack_text = format_attack_result(game, out_of_defense=not game["in_defense"])
    defense_text = format_defense_result(game)
    return attack_text, defense_text


def next_turn(game):
    """Готовим новый обычный ход."""
    game["nightmare_defense"] = random.choice(list(ZONES.keys()))
    game["nightmare_attack"] = random.choice(list(ZONES.keys()))
    game["krait_attack"] = None
    game["krait_defense"] = None
    game["phase"] = "choose_mode"


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


def hint_text(step):
    """Тексты намёков на комбо."""
    if step == 1:
        return "\n\n✨ <i>Ты нащупал что-то... Кажется, ты на верном пути.</i>"
    elif step == 2:
        return "\n\n✨✨ <i>Почти получилось! Ещё немного — и что-то случится.</i>"
    return ""


def mode_prompt(game):
    """Текст и кнопки для фазы выбора режима."""
    text = (
        status(game)
        + "\n\n🛡️ <b>Выбери режим на этот ход:</b>"
    )
    return text, mode_buttons(game)


# --- Хэндлеры ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in games and games[user_id]["phase"] != "finished":
        games[user_id] = create_game()
        game = games[user_id]
        text, kb = mode_prompt(game)
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
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

    text, kb = mode_prompt(game)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(GAME_DESCRIPTION, parse_mode="HTML")


async def mode_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Игрок выбрал режим — переходим к фазе атаки."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.edit_message_text("Нажми /start.")
        return

    if game["phase"] != "choose_mode":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    choice = query.data.split(":")[1]
    game["in_defense"] = (choice == "on")

    game["phase"] = "attack"

    await query.edit_message_text(
        status(game)
        + "\n\n⚔️ Выбери, куда атаковать Кошмара:",
        parse_mode="HTML",
        reply_markup=zone_buttons("attack"),
    )


async def attack_phase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.edit_message_text("Нажми /start.")
        return

    if game["phase"] != "attack":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    zone = query.data.split(":")[1]
    game["krait_attack"] = zone

    step = update_combo(game, zone)
    if step == 3:
        game["stun_turns"] = 1  # стан 1 ход

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

    # Намёки на комбо (если ещё не показывали)
    combo_step = game["combo_progress"]
    if not game["hint_shown"] and combo_step in (1, 2):
        text += hint_text(combo_step)
        game["hint_shown"] = True

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

    # Если собрано комбо — стан
    if game["stun_turns"] > 0:
        combo_text = "\n\n🔥 <b>КОМБО ВЫПОЛНЕНО!</b>"
        if not game["combo_revealed"]:
            combo_text += (
                f"\nПоследовательность: <b>{combo_to_text(game['combo'])}</b>"
            )
            game["combo_revealed"] = True
        combo_text += (
            "\n\n👹 Кошмар оглушён на 1 ход.\n"
            "Он не атакует и не защищается.\n"
            "Ты сам решаешь: выйти из защиты или остаться.\n\n"
            "⚔️ Выбери режим и ударь:"
        )
        text += combo_text
        game["phase"] = "stun_mode"
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=mode_buttons(game)
        )
        return

    next_turn(game)
    text += "\n\n🛡️ <b>Новый ход. Выбери режим:</b>"
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=mode_buttons(game)
    )


async def stun_mode_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """В стане игрок выбрал режим — переходим к удару."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.edit_message_text("Нажми /start.")
        return

    if game["phase"] != "stun_mode":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    choice = query.data.split(":")[1]
    game["in_defense"] = (choice == "on")

    game["phase"] = "stun_attack"

    await query.edit_message_text(
        status(game)
        + f"\n\n🔥 Кошмар оглушён. Осталось ходов стана: {game['stun_turns']}\n"
          "⚔️ Выбери, куда бить:",
        parse_mode="HTML",
        reply_markup=zone_buttons("stun_attack"),
    )


async def stun_attack_phase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удар в стане — Кошмар не защищается."""
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

    # Урон
    if game["in_defense"]:
        dmg = DAMAGE // 2
    else:
        dmg = DAMAGE

    game["nightmare_hp"] -= dmg
    if game["nightmare_hp"] < 0:
        game["nightmare_hp"] = 0

    text = (
        status(game)
        + f"\n\n⚔️ Крайт ударил в {ZONES[zone]} — "
          f"Кошмар оглушён и не защищался.\n"
          f"<b>{dmg} урона!</b>"
    )

    # Комбо копится и в стане
    step = update_combo(game, zone)

    end = check_end(game)
    if end == "win":
        text += "\n\n🏆 <b>КРАЙТ ПОБЕДИЛ!</b>"
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=new_game_button()
        )
        return

    # Уменьшаем счётчик стана
    game["stun_turns"] -= 1

    if game["stun_turns"] > 0:
        # Ещё есть стан
        text += (
            f"\n\n🔥 Кошмар всё ещё оглушён. Осталось ходов стана: {game['stun_turns']}\n"
            "⚔️ Выбери режим и бей снова:"
        )
        game["phase"] = "stun_mode"
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=mode_buttons(game)
        )
        return

    # Стан закончился — новый обычный ход
    next_turn(game)
    text += "\n\n🔥 Стан закончился.\n🛡️ <b>Новый ход. Выбери режим:</b>"
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=mode_buttons(game)
    )


async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    games[user_id] = create_game()
    game = games[user_id]

    text = (
        status(game)
        + "\n\n👹 <b>НОВАЯ БИТВА!</b>\n"
          "🛡️ Выбери режим:"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=mode_buttons(game))


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
    app.add_handler(CallbackQueryHandler(mode_choice, pattern=r"^mode:(on|off)$"))
    app.add_handler(CallbackQueryHandler(attack_phase, pattern=r"^attack:"))
    app.add_handler(CallbackQueryHandler(defense_phase, pattern=r"^defense:"))
    app.add_handler(CallbackQueryHandler(stun_mode_choice, pattern=r"^mode:(on|off)$"))
    app.add_handler(CallbackQueryHandler(stun_attack_phase, pattern=r"^stun_attack:"))
    app.add_handler(CallbackQueryHandler(new_game, pattern=r"^new_game$"))

    print("Крайт против Кошмара запущен!")

    app.run_polling()


if __name__ == "__main__":
    main()
