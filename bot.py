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
    MessageHandler,
    filters,
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


# --- Описание игры ---

GAME_DESCRIPTION = (
    "⚔️ <b>КРАЙТ ПРОТИВ КОШМАРА</b>\n\n"
    "<i>Лотос расцветает лишь в час битвы.</i>\n\n"
    "━━━━━━━━━━━━━━━\n"
    "📖 <b>ЛЕГЕНДА</b>\n\n"
    "Говорят, когда тьма сгущается настолько, что\n"
    "гасит даже звёзды, — приходит Крайт.\n\n"
    "Рыцарь с лотосом на груди. Воин, чей клинок\n"
    "помнит тысячу битв. Его путь — точность,\n"
    "терпение и скрытая техника, что раскрывается\n"
    "в решающий миг.\n\n"
    "Кошмар — не просто враг. Это тень, что пожирает\n"
    "свет. Он древен. Он голоден. И он не уйдёт,\n"
    "пока не поглотит последний луч.\n\n"
    "Этот бой решит, кто достоин стоять под солнцем.\n\n"
    "━━━━━━━━━━━━━━━\n"
    "⚔️ <b>БИТВА</b>\n\n"
    "❤️ Крайт: <b>200 HP</b>\n"
    "👹 Кошмар: <b>300 HP</b>\n"
    "⚔️ Оба наносят по <b>20 урона</b>\n\n"
    "📍 Зоны удара: 🧠 голова, 🫀 туловище, 🦵 ноги\n\n"
    "<b>Ход битвы:</b>\n"
    "1. Ты выбираешь режим: в защиту или без.\n"
    "2. Ты выбираешь, куда атаковать.\n"
    "3. Кошмар скрыто выбирает, куда защищаться.\n"
    "4. Ты выбираешь, куда блокировать.\n"
    "5. Кошмар скрыто выбирает, куда атаковать.\n"
    "6. Показывается итог хода.\n\n"
    "✅ Зоны совпали — блок, 0 урона.\n"
    "❌ Не совпали — урон.\n\n"
    "━━━━━━━━━━━━━━━\n"
    "🛡️ <b>ЗАЩИТНАЯ СТОЙКА</b>\n\n"
    "В начале каждого хода ты выбираешь:\n"
    "встать в защиту или сражаться без неё.\n\n"
    "<b>В защите:</b>\n"
    "— ты наносишь 50% урона (10 вместо 20)\n"
    "— ты получаешь 50% урона (10 вместо 20)\n"
    "— блок по-прежнему даёт 0 урона\n\n"
    "Защита действует весь ход — и на атаку, и на блок.\n"
    "Выйти из неё можно только в начале следующего хода.\n\n"
    "━━━━━━━━━━━━━━━\n"
    "🔥 <b>СЕКРЕТНОЕ КОМБО</b>\n\n"
    "В каждой битве спрятано своё комбо из трёх\n"
    "ударов подряд. Угадаешь последовательность —\n"
    "Кошмар будет оглушён на 1 ход: он не сможет\n"
    "ни атаковать, ни защищаться, а ты нанесёшь\n"
    "гарантированный удар.\n\n"
    "Любая ошибка — сброс. Начинай заново.\n"
    "Последовательность не подскажем — ищи сам.\n\n"
    "━━━━━━━━━━━━━━━\n"
    "🏆 <b>ИСХОД</b>\n\n"
    "🏆 Победа: Кошмар 0 HP.\n"
    "💀 Поражение: Крайт 0 HP.\n"
    "🤝 Если у обоих 0 HP — поражение Крайта.\n\n"
    "━━━━━━━━━━━━━━━\n"
    "📋 <b>КОМАНДЫ</b>\n\n"
    "/start — начать игру\n"
    "/new_game — новая игра\n"
    "/rules — правила\n\n"
    "Или просто напиши:\n"
    "• <b>новая игра</b> — начать заново\n"
    "• <b>правила</b> — показать правила\n"
    "• <b>старт</b> — начать бой"
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
        "hint_1_shown": False,
        "hint_2_shown": False,
        "in_defense": False,
        "stun_turns": 0,
        "phase": "attack",
    }


def status(game):
    mode = "🛡️ Режим: защита" if game["in_defense"] else "⚔️ Режим: без защиты"
    return (
        "⚔️ <b>КРАЙТ ПРОТИВ КОШМАРА</b>\n\n"
        f"❤️ Крайт: <b>{game['krait_hp']} HP</b>\n"
        f"👹 Кошмар: <b>{game['nightmare_hp']} HP</b>\n"
        f"{mode}"
    )


def attack_screen_buttons(game, prefix="attack"):
    """Кнопки экрана атаки: переключатель режима + зоны."""
    if game["in_defense"]:
        mode_label = "⚔️ Выйти из защиты"
        mode_cb = f"{prefix}_mode:off"
    else:
        mode_label = "🛡️ Встать в защиту"
        mode_cb = f"{prefix}_mode:on"

    mode_row = [InlineKeyboardButton(mode_label, callback_data=mode_cb)]
    zone_row1 = [
        InlineKeyboardButton("🧠 Голова", callback_data=f"{prefix}:head"),
        InlineKeyboardButton("🫀 Туловище", callback_data=f"{prefix}:body"),
    ]
    zone_row2 = [
        InlineKeyboardButton("🦵 Ноги", callback_data=f"{prefix}:legs"),
    ]
    return InlineKeyboardMarkup([mode_row, zone_row1, zone_row2])


def defense_zone_buttons():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🧠 Голова", callback_data="defense:head"),
            InlineKeyboardButton("🫀 Туловище", callback_data="defense:body"),
        ],
        [
            InlineKeyboardButton("🦵 Ноги", callback_data="defense:legs"),
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
    return " → ".join(ZONES[z] for z in seq)


def update_combo(game, zone):
    """Скрытое комбо. Возвращает 0/1/2/3 (3 = комбо собрано)."""
    progress = game["combo_progress"]
    seq = game["combo"]

    if progress < 3 and zone == seq[progress]:
        game["combo_progress"] += 1
        if game["combo_progress"] == 3:
            game["combo_progress"] = 0
            return 3
        return game["combo_progress"]

    if zone == seq[0]:
        game["combo_progress"] = 1
        return 1
    else:
        game["combo_progress"] = 0
        return 0


def format_attack_result(game):
    krait_zone = game["krait_attack"]
    nightmare_def = game["nightmare_defense"]

    if krait_zone == nightmare_def:
        return (
            f"⚔️ Крайт ударил в {ZONES[krait_zone]} — "
            f"👹 Кошмар заблокировал (0 урона)."
        )
    else:
        dmg = DAMAGE // 2 if game["in_defense"] else DAMAGE
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
        dmg = DAMAGE // 2 if game["in_defense"] else DAMAGE
        return (
            f"👹 Кошмар ударил в {ZONES[nightmare_atk]} — попал! "
            f"❤️ Крайт получил {dmg} урона."
        )


def apply_results(game):
    attack_text = format_attack_result(game)
    defense_text = format_defense_result(game)

    if game["krait_attack"] != game["nightmare_defense"]:
        if game["in_defense"]:
            game["nightmare_hp"] -= DAMAGE // 2
        else:
            game["nightmare_hp"] -= DAMAGE

    if game["krait_defense"] != game["nightmare_attack"]:
        if game["in_defense"]:
            game["krait_hp"] -= DAMAGE // 2
        else:
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
    if step == 1:
        return "\n\n✨ <i>Крайт чувствует: что-то дрогнуло во тьме...</i>"
    elif step == 2:
        return "\n\n✨✨ <i>Лотос почти раскрылся. Ещё удар — и он расцветёт.</i>"
    return ""


async def remove_buttons(query):
    """Убираем кнопки у старого сообщения."""
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass


# --- Хэндлеры ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in games and games[user_id]["phase"] != "finished":
        games[user_id] = create_game()
        game = games[user_id]
        await update.message.reply_text(
            status(game)
            + "\n\n⚔️ <b>Твой ход!</b>\nВыбери действие:",
            parse_mode="HTML",
            reply_markup=attack_screen_buttons(game, prefix="attack"),
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

    await remove_buttons(query)

    await query.message.reply_text(
        status(game)
        + "\n\n⚔️ <b>Твой ход!</b>\nВыбери действие:",
        parse_mode="HTML",
        reply_markup=attack_screen_buttons(game, prefix="attack"),
    )


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(GAME_DESCRIPTION, parse_mode="HTML")


async def toggle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.message.reply_text("Нажми /start.")
        return

    if game["phase"] != "attack":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    choice = query.data.split(":")[1]
    game["in_defense"] = (choice == "on")

    await remove_buttons(query)

    await query.message.reply_text(
        status(game)
        + "\n\n⚔️ <b>Твой ход!</b>\nВыбери действие:",
        parse_mode="HTML",
        reply_markup=attack_screen_buttons(game, prefix="attack"),
    )


async def attack_phase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.message.reply_text("Нажми /start.")
        return

    if game["phase"] != "attack":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    zone = query.data.split(":")[1]
    game["krait_attack"] = zone

    step = update_combo(game, zone)
    if step == 3:
        game["stun_turns"] = 1

    game["phase"] = "defense"

    await remove_buttons(query)

    await query.message.reply_text(
        status(game)
        + "\n\n🛡️ Теперь выбери, куда блокировать удар Кошмара:",
        parse_mode="HTML",
        reply_markup=defense_zone_buttons(),
    )


async def defense_phase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.message.reply_text("Нажми /start.")
        return

    if game["phase"] != "defense":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    zone = query.data.split(":")[1]
    game["krait_defense"] = zone

    attack_text, defense_text = apply_results(game)

    text = status(game) + "\n\n" + attack_text + "\n" + defense_text

    # Намёки на комбо — по одному разу на каждый уровень
    combo_step = game["combo_progress"]
    if combo_step == 1 and not game["hint_1_shown"]:
        text += hint_text(1)
        game["hint_1_shown"] = True
    elif combo_step == 2 and not game["hint_2_shown"]:
        text += hint_text(2)
        game["hint_2_shown"] = True

    end = check_end(game)
    if end == "win":
        text += (
            "\n\n🏆 <b>КРАЙТ ПОБЕДИЛ!</b>\n\n"
            "Лотос расцвёл. Кошмар развеян.\n"
            "Тьма отступила перед твоим клинком.\n\n"
            "<i>Но Кошмар не умирает. Он ждёт нового рассвета...</i>"
        )
        await remove_buttons(query)
        await query.message.reply_text(
            text, parse_mode="HTML", reply_markup=new_game_button()
        )
        return
    elif end == "lose":
        text += (
            "\n\n💀 <b>КРАЙТ ПАЛ...</b>\n\n"
            "Кошмар поглотил свет.\n"
            "Лотос увял во тьме.\n\n"
            "<i>Но лотос не умирает — он ждёт нового рассвета.</i>"
        )
        await remove_buttons(query)
        await query.message.reply_text(
            text, parse_mode="HTML", reply_markup=new_game_button()
        )
        return

    if game["stun_turns"] > 0:
        combo_text = "\n\n🔥 <b>КОМБО ВЫПОЛНЕНО!</b>"
        if not game["combo_revealed"]:
            combo_text += (
                f"\nПоследовательность: <b>{combo_to_text(game['combo'])}</b>"
            )
            game["combo_revealed"] = True
        combo_text += (
            "\n\n👹 Кошмар оглушён на 1 ход.\n"
            "Он не атакует и не защищается.\n\n"
            "⚔️ Выбери действие:"
        )
        text += combo_text
        game["phase"] = "stun_attack"
        await remove_buttons(query)
        await query.message.reply_text(
            text, parse_mode="HTML",
            reply_markup=attack_screen_buttons(game, prefix="stun_attack")
        )
        return

    next_turn(game)
    text += "\n\n⚔️ <b>Твой ход!</b>\nВыбери действие:"
    await remove_buttons(query)
    await query.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=attack_screen_buttons(game, prefix="attack")
    )


async def stun_toggle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.message.reply_text("Нажми /start.")
        return

    if game["phase"] != "stun_attack":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    choice = query.data.split(":")[1]
    game["in_defense"] = (choice == "on")

    await remove_buttons(query)

    await query.message.reply_text(
        status(game)
        + f"\n\n🔥 Кошмар оглушён. Осталось ходов стана: {game['stun_turns']}\n"
          "⚔️ Выбери действие:",
        parse_mode="HTML",
        reply_markup=attack_screen_buttons(game, prefix="stun_attack"),
    )


async def stun_attack_phase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.message.reply_text("Нажми /start.")
        return

    if game["phase"] != "stun_attack":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    zone = query.data.split(":")[1]

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

    update_combo(game, zone)

    end = check_end(game)
    if end == "win":
        text += (
            "\n\n🏆 <b>КРАЙТ ПОБЕДИЛ!</b>\n\n"
            "Лотос расцвёл. Кошмар развеян.\n"
            "Тьма отступила перед твоим клинком.\n\n"
            "<i>Но Кошмар не умирает. Он ждёт нового рассвета...</i>"
        )
        await remove_buttons(query)
        await query.message.reply_text(
            text, parse_mode="HTML", reply_markup=new_game_button()
        )
        return

    game["stun_turns"] -= 1

    if game["stun_turns"] > 0:
        text += (
            f"\n\n🔥 Кошмар всё ещё оглушён. Осталось ходов стана: {game['stun_turns']}\n"
            "⚔️ Выбери действие:"
        )
        game["phase"] = "stun_attack"
        await remove_buttons(query)
        await query.message.reply_text(
            text, parse_mode="HTML",
            reply_markup=attack_screen_buttons(game, prefix="stun_attack")
        )
        return

    next_turn(game)
    text += "\n\n🔥 Стан закончился.\n⚔️ <b>Твой ход!</b>\nВыбери действие:"
    await remove_buttons(query)
    await query.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=attack_screen_buttons(game, prefix="attack")
    )


async def new_game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback-кнопка «🔄 Новая игра» — показать описание."""
    query = update.callback_query
    await query.answer()

    await remove_buttons(query)
    await query.message.reply_text(
        GAME_DESCRIPTION,
        parse_mode="HTML",
        reply_markup=intro_button(),
    )


async def new_game_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /new_game — показать описание."""
    await update.message.reply_text(
        GAME_DESCRIPTION,
        parse_mode="HTML",
        reply_markup=intro_button(),
    )


async def text_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Текстовые команды на русском."""
    text = update.message.text.strip().lower()

    if text in ("новая игра", "новая", "заново", "new game"):
        await update.message.reply_text(
            GAME_DESCRIPTION,
            parse_mode="HTML",
            reply_markup=intro_button(),
        )
        return

    if text in ("правила", "правила игры", "помощь", "help"):
        await update.message.reply_text(GAME_DESCRIPTION, parse_mode="HTML")
        return

    if text in ("старт", "начать", "играть", "start"):
        user_id = update.effective_user.id
        if user_id in games and games[user_id]["phase"] != "finished":
            games[user_id] = create_game()
            game = games[user_id]
            await update.message.reply_text(
                status(game)
                + "\n\n⚔️ <b>Твой ход!</b>\nВыбери действие:",
                parse_mode="HTML",
                reply_markup=attack_screen_buttons(game, prefix="attack"),
            )
        else:
            await update.message.reply_text(
                GAME_DESCRIPTION,
                parse_mode="HTML",
                reply_markup=intro_button(),
            )
        return

    await update.message.reply_text(
        "Не понял команду. Попробуй:\n"
        "• <b>новая игра</b>\n"
        "• <b>правила</b>\n"
        "• <b>старт</b>",
        parse_mode="HTML",
    )


def main():
    if not TOKEN:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Добавь токен в переменные окружения."
        )

    Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new_game", new_game_cmd))
    app.add_handler(CommandHandler("rules", rules))

    # Callback-кнопки
    app.add_handler(CallbackQueryHandler(begin_battle, pattern=r"^begin_battle$"))
    app.add_handler(CallbackQueryHandler(toggle_mode, pattern=r"^attack_mode:(on|off)$"))
    app.add_handler(CallbackQueryHandler(attack_phase, pattern=r"^attack:(head|body|legs)$"))
    app.add_handler(CallbackQueryHandler(defense_phase, pattern=r"^defense:"))
    app.add_handler(CallbackQueryHandler(stun_toggle_mode, pattern=r"^stun_attack_mode:(on|off)$"))
    app.add_handler(CallbackQueryHandler(stun_attack_phase, pattern=r"^stun_attack:(head|body|legs)$"))
    app.add_handler(CallbackQueryHandler(new_game_cb, pattern=r"^new_game$"))

    # Текстовые команды
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_command))

    print("Крайт против Кошмара запущен!")

    app.run_polling()


if __name__ == "__main__":
    main()
