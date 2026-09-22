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

NIGHTMARE_HP = 300
NIGHTMARE_DAMAGE = 20

ZONES = {
    "head": "🧠 Голова",
    "body": "🫀 Туловище",
    "legs": "🦵 Ноги",
}

CLASSES = {
    "tank": {
        "name": "🛡️ Танк",
        "hp": 200,
        "damage": 20,
        "desc": "Терпение и сталь. Комбо даёт стан.",
    },
    "crit": {
        "name": "💥 Крит",
        "hp": 180,
        "damage": 20,
        "desc": "Ярость и точность. Комбо даёт крит.",
    },
    "dodge": {
        "name": "⚡ Уворот",
        "hp": 160,
        "damage": 20,
        "desc": "Скорость и ветер. Комбо даёт 2 удара и уклонение.",
    },
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
    "🎭 <b>КЛАССЫ</b>\n\n"
    "🛡️ <b>Танк</b> — 200 HP.\n"
    "   Комбо: стан. Кошмар пропускает ход.\n\n"
    "💥 <b>Крит</b> — 180 HP.\n"
    "   Комбо: крит. Пробивает блок (50/25).\n\n"
    "⚡ <b>Уворот</b> — 160 HP.\n"
    "   Комбо: 2 удара + уклонение. Кошмар не бьёт.\n\n"
    "━━━━━━━━━━━━━━━\n"
    "⚔️ <b>БИТВА</b>\n\n"
    "👹 Кошмар: <b>300 HP</b>, <b>20 урона</b>\n"
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
    "━━━━━━━━━━━━━━━\n"
    "🔥 <b>СЕКРЕТНОЕ КОМБО</b>\n\n"
    "В каждой битве спрятано своё комбо из трёх\n"
    "ударов подряд. Угадаешь последовательность —\n"
    "получишь особый эффект в зависимости от класса.\n\n"
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


def create_game(class_key):
    cls = CLASSES[class_key]
    return {
        "class": class_key,
        "krait_hp": cls["hp"],
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
        "stun_effect": None,
        "dodge_zone_1": None,
        "phase": "attack",
    }


def status(game):
    cls = CLASSES[game["class"]]
    mode = "🛡️ Режим: защита" if game["in_defense"] else "⚔️ Режим: без защиты"
    return (
        "⚔️ <b>КРАЙТ ПРОТИВ КОШМАРА</b>\n\n"
        f"{cls['name']}\n"
        f"❤️ Крайт: <b>{game['krait_hp']} HP</b>\n"
        f"👹 Кошмар: <b>{game['nightmare_hp']} HP</b>\n"
        f"{mode}"
    )


def class_buttons():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛡️ Танк", callback_data="class:tank"),
            InlineKeyboardButton("⚡ Уворот", callback_data="class:dodge"),
        ],
        [
            InlineKeyboardButton("💥 Крит", callback_data="class:crit"),
        ],
    ])


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
    """Обычное комбо. Возвращает 0/1/2/3 (3 = собрано)."""
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


def end_screen_text(end):
    if end == "win":
        return (
            "\n\n🏆 <b>КРАЙТ ПОБЕДИЛ!</b>\n\n"
            "Лотос расцвёл. Кошмар развеян.\n"
            "Тьма отступила перед твоим клинком.\n\n"
            "<i>Но Кошмар не умирает. Он ждёт нового рассвета...</i>"
        )
    else:
        return (
            "\n\n💀 <b>КРАЙТ ПАЛ...</b>\n\n"
            "Кошмар поглотил свет.\n"
            "Лотос увял во тьме.\n\n"
            "<i>Но лотос не умирает — он ждёт нового рассвета.</i>"
        )


async def remove_buttons(query):
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass


# --- Боевые резолверы ---

def resolve_normal_round(game):
    """Обычный ход: Крайт бьёт, Кошмар защищается; потом Кошмар бьёт, Крайт защищается."""
    cls = CLASSES[game["class"]]

    krait_zone = game["krait_attack"]
    if krait_zone == game["nightmare_defense"]:
        attack_text = (
            f"⚔️ Крайт ударил в {ZONES[krait_zone]} — "
            f"👹 Кошмар заблокировал (0 урона)."
        )
    else:
        dmg = cls["damage"] // 2 if game["in_defense"] else cls["damage"]
        game["nightmare_hp"] -= dmg
        attack_text = (
            f"⚔️ Крайт ударил в {ZONES[krait_zone]} — попал! "
            f"👹 Кошмар получил {dmg} урона."
        )

    nightmare_atk = game["nightmare_attack"]
    if game["krait_defense"] == nightmare_atk:
        defense_text = (
            f"👹 Кошмар ударил в {ZONES[nightmare_atk]} — "
            f"🛡️ Крайт заблокировал (0 урона)."
        )
    else:
        dmg = NIGHTMARE_DAMAGE // 2 if game["in_defense"] else NIGHTMARE_DAMAGE
        game["krait_hp"] -= dmg
        defense_text = (
            f"👹 Кошмар ударил в {ZONES[nightmare_atk]} — попал! "
            f"❤️ Крайт получил {dmg} урона."
        )

    return attack_text, defense_text


def resolve_tank_stun(game):
    """Танк в стане: Кошмар не бьёт и не защищается."""
    cls = CLASSES[game["class"]]
    krait_zone = game["krait_attack"]
    dmg = cls["damage"] // 2 if game["in_defense"] else cls["damage"]
    game["nightmare_hp"] -= dmg

    attack_text = (
        f"⚔️ Крайт ударил в {ZONES[krait_zone]} — "
        f"👹 Кошмар оглушён и не защищался.\n"
        f"<b>{dmg} урона!</b>"
    )
    defense_text = "🔥 Кошмар пропускает ход."
    return attack_text, defense_text


def resolve_crit_stun(game):
    """Крит: гарантированный крит-удар. Кошмар бьёт в ответ."""
    krait_zone = game["krait_attack"]
    nightmare_def = game["nightmare_defense"]

    if game["in_defense"]:
        if krait_zone == nightmare_def:
            dmg = 15
        else:
            dmg = 25
    else:
        if krait_zone == nightmare_def:
            dmg = 25
        else:
            dmg = 50

    game["nightmare_hp"] -= dmg

    if krait_zone == nightmare_def:
        attack_text = (
            f"⚔️ Крайт обрушил крит в {ZONES[krait_zone]} — "
            f"👹 Кошмар в блоке, но крит <b>пробил</b>!\n"
            f"<b>{dmg} урона!</b>"
        )
    else:
        attack_text = (
            f"⚔️ Крайт обрушил крит в {ZONES[krait_zone]} — "
            f"💥 <b>КРИТ!</b> 👹 Кошмар получил {dmg} урона."
        )

    nightmare_atk = game["nightmare_attack"]
    if game["krait_defense"] == nightmare_atk:
        defense_text = (
            f"👹 Кошмар ударил в {ZONES[nightmare_atk]} — "
            f"🛡️ Крайт заблокировал (0 урона)."
        )
    else:
        dmg_taken = NIGHTMARE_DAMAGE // 2 if game["in_defense"] else NIGHTMARE_DAMAGE
        game["krait_hp"] -= dmg_taken
        defense_text = (
            f"👹 Кошмар ударил в {ZONES[nightmare_atk]} — попал! "
            f"❤️ Крайт получил {dmg_taken} урона."
        )

    return attack_text, defense_text


def resolve_dodge_stun(game):
    """Уворот: два удара по двум зонам, Кошмар промахивается."""
    cls = CLASSES[game["class"]]
    zone1 = game["krait_attack"]
    zone2 = game["dodge_zone_1"]
    nightmare_def = game["nightmare_defense"]

    dmg_each = cls["damage"] // 2 if game["in_defense"] else cls["damage"]

    texts = []

    if zone1 == nightmare_def:
        texts.append(
            f"⚔️ Удар 1: Крайт ударил в {ZONES[zone1]} — "
            f"👹 Кошмар заблокировал (0 урона)."
        )
    else:
        game["nightmare_hp"] -= dmg_each
        texts.append(
            f"⚔️ Удар 1: Крайт ударил в {ZONES[zone1]} — попал! "
            f"👹 Кошмар получил {dmg_each} урона."
        )

    if zone2 == nightmare_def:
        texts.append(
            f"⚡ Удар 2: Крайт ударил в {ZONES[zone2]} — "
            f"👹 Кошмар заблокировал (0 урона)."
        )
    else:
        game["nightmare_hp"] -= dmg_each
        texts.append(
            f"⚡ Удар 2: Крайт ударил в {ZONES[zone2]} — попал! "
            f"👹 Кошмар получил {dmg_each} урона."
        )

    attack_text = "\n".join(texts)
    defense_text = "💨 Кошмар попытался ударить — Крайт уклонился! (0 урона)"

    return attack_text, defense_text


# --- Хэндлеры ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in games and games[user_id]["phase"] != "finished":
        await update.message.reply_text(
            "У тебя уже идёт бой. Напиши <b>новая игра</b> или /new_game,\n"
            "чтобы начать заново.",
            parse_mode="HTML",
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

    await remove_buttons(query)

    await query.message.reply_text(
        "⚔️ <b>ВЫБЕРИ СВОЙ ПУТЬ</b>\n\n"
        "🛡️ <b>Танк</b> — 200 HP.\n"
        "   Комбо: стан. Кошмар пропускает ход.\n\n"
        "💥 <b>Крит</b> — 180 HP.\n"
        "   Комбо: крит. Пробивает блок (50/25).\n\n"
        "⚡ <b>Уворот</b> — 160 HP.\n"
        "   Комбо: 2 удара + уклонение. Кошмар не бьёт.\n\n"
        "Кем ты войдёшь в этот бой?",
        parse_mode="HTML",
        reply_markup=class_buttons(),
    )


async def choose_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    class_key = query.data.split(":")[1]

    if class_key not in CLASSES:
        await query.answer("Неизвестный класс.", show_alert=True)
        return

    games[user_id] = create_game(class_key)
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
        cls_key = game["class"]
        game["stun_effect"] = cls_key

        if cls_key == "dodge":
            game["phase"] = "dodge_attack_1"
            await remove_buttons(query)
            await query.message.reply_text(
                status(game)
                + "\n\n⚡ <b>УВОРОТ АКТИВИРОВАН</b>\n\n"
                "Крайт входит в поток. Следующие два удара —\n"
                "быстрые, неуловимые. Кошмар не успеет ответить.\n\n"
                "⚠️ <i>Удары в этом ходу не идут в счёт комбо.</i>\n\n"
                "⚔️ Выбери <b>первую</b> зону атаки:",
                parse_mode="HTML",
                reply_markup=attack_screen_buttons(game, prefix="dodge_attack_1"),
            )
            return

        if cls_key == "tank":
            game["phase"] = "tank_stun"
            await remove_buttons(query)
            await query.message.reply_text(
                status(game)
                + "\n\n🔥 <b>КОМБО! КОШМАР ОГЛУШЁН</b>\n\n"
                "Кошмар пропускает ход. Он не атакует\n"
                "и не защищается.\n\n"
                "⚔️ Выбери действие и ударь:",
                parse_mode="HTML",
                reply_markup=attack_screen_buttons(game, prefix="tank_stun"),
            )
            return

        if cls_key == "crit":
            game["phase"] = "crit_stun_attack"
            await remove_buttons(query)
            await query.message.reply_text(
                status(game)
                + "\n\n💥 <b>КОМБО! КРИТ АКТИВИРОВАН</b>\n\n"
                "Следующий удар Крайта — критический.\n"
                "Кошмар не защитится полностью,\n"
                "но ударит в ответ.\n\n"
                "⚔️ Выбери действие и ударь:",
                parse_mode="HTML",
                reply_markup=attack_screen_buttons(game, prefix="crit_stun_attack"),
            )
            return

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

    attack_text, defense_text = resolve_normal_round(game)

    text = status(game) + "\n\n" + attack_text + "\n" + defense_text

    combo_step = game["combo_progress"]
    if combo_step == 1 and not game["hint_1_shown"]:
        text += hint_text(1)
        game["hint_1_shown"] = True
    elif combo_step == 2 and not game["hint_2_shown"]:
        text += hint_text(2)
        game["hint_2_shown"] = True

    end = check_end(game)
    if end:
        text += end_screen_text(end)
        await remove_buttons(query)
        await query.message.reply_text(
            text, parse_mode="HTML", reply_markup=new_game_button()
        )
        return

    next_turn(game)
    text += "\n\n⚔️ <b>Твой ход!</b>\nВыбери действие:"
    await remove_buttons(query)
    await query.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=attack_screen_buttons(game, prefix="attack")
    )


async def tank_stun_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.message.reply_text("Нажми /start.")
        return

    if game["phase"] != "tank_stun":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    choice = query.data.split(":")[1]
    game["in_defense"] = (choice == "on")

    await remove_buttons(query)
    await query.message.reply_text(
        status(game)
        + "\n\n🔥 <b>КОШМАР ОГЛУШЁН</b>\n\n"
        "Он не атакует и не защищается.\n\n"
        "⚔️ Выбери действие и ударь:",
        parse_mode="HTML",
        reply_markup=attack_screen_buttons(game, prefix="tank_stun"),
    )


async def tank_stun_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.message.reply_text("Нажми /start.")
        return

    if game["phase"] != "tank_stun":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    zone = query.data.split(":")[1]
    game["krait_attack"] = zone

    update_combo(game, zone)

    attack_text, defense_text = resolve_tank_stun(game)

    text = status(game) + "\n\n" + attack_text + "\n" + defense_text

    end = check_end(game)
    if end:
        text += end_screen_text(end)
        await remove_buttons(query)
        await query.message.reply_text(
            text, parse_mode="HTML", reply_markup=new_game_button()
        )
        return

    next_turn(game)
    text += "\n\n⚔️ <b>Твой ход!</b>\nВыбери действие:"
    await remove_buttons(query)
    await query.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=attack_screen_buttons(game, prefix="attack")
    )


async def crit_stun_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.message.reply_text("Нажми /start.")
        return

    if game["phase"] != "crit_stun_attack":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    choice = query.data.split(":")[1]
    game["in_defense"] = (choice == "on")

    await remove_buttons(query)
    await query.message.reply_text(
        status(game)
        + "\n\n💥 <b>КРИТ АКТИВИРОВАН</b>\n\n"
        "Следующий удар — критический.\n\n"
        "⚔️ Выбери действие и ударь:",
        parse_mode="HTML",
        reply_markup=attack_screen_buttons(game, prefix="crit_stun_attack"),
    )


async def crit_stun_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.message.reply_text("Нажми /start.")
        return

    if game["phase"] != "crit_stun_attack":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    zone = query.data.split(":")[1]
    game["krait_attack"] = zone

    update_combo(game, zone)

    game["phase"] = "crit_stun_defense"

    await remove_buttons(query)
    await query.message.reply_text(
        status(game)
        + "\n\n🛡️ Кошмар готовит ответный удар.\n"
          "Выбери, куда блокировать:",
        parse_mode="HTML",
        reply_markup=defense_zone_buttons(),
    )


async def crit_stun_defense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.message.reply_text("Нажми /start.")
        return

    if game["phase"] != "crit_stun_defense":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    zone = query.data.split(":")[1]
    game["krait_defense"] = zone

    attack_text, defense_text = resolve_crit_stun(game)

    text = status(game) + "\n\n" + attack_text + "\n" + defense_text

    end = check_end(game)
    if end:
        text += end_screen_text(end)
        await remove_buttons(query)
        await query.message.reply_text(
            text, parse_mode="HTML", reply_markup=new_game_button()
        )
        return

    next_turn(game)
    text += "\n\n⚔️ <b>Твой ход!</b>\nВыбери действие:"
    await remove_buttons(query)
    await query.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=attack_screen_buttons(game, prefix="attack")
    )


async def dodge_stun_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    game = games.get(user_id)

    if not game:
        await query.message.reply_text("Нажми /start.")
        return

    if game["phase"] != "dodge_attack_1":
        await query.answer("Сейчас это действие недоступно.", show_alert=True)
        return

    choice = query.data.split(":")[1]
    game["in_defense"] = (choice == "on")

    await remove_buttons(query)
    await query.message.reply_text(
        status(game)
        + "\n\n⚡ <b>УВОРОТ
