import asyncio
import logging
import os
from anthropic import AsyncAnthropic
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


# ── States ────────────────────────────────────────────────────────────────────

class Session(StatesGroup):
    choosing_language = State()
    in_dialogue       = State()
    viewing_report    = State()
    deepening_beliefs = State()


# ── UI strings ────────────────────────────────────────────────────────────────

UI = {
    "ru": {
        "welcome": (
            "Добро пожаловать.\n\n"
            "Это не тест с вариантами ответов — это живая диагностическая беседа.\n\n"
            "По итогу вы получите *Психологическую карту личности*:\n"
            "• Тип Эннеаграммы + крыло + инстинкт\n"
            "• Ключевые метапрограммы\n"
            "• Уровень Спиральной Динамики\n"
            "• Явные ценности и скрытые убеждения\n\n"
            "≈ 20–30 минут живого диалога.\n\n"
            "Готовы? Просто напишите что-нибудь — и мы начнём."
        ),
        "generating":     "⏳ Генерирую вашу психологическую карту...",
        "report_btn":     "📊 Получить мою карту",
        "deepen_btn":     "🔍 Исследовать убеждения глубже",
        "restart_btn":    "🔄 Начать заново",
        "restart_prompt": "Выберите язык:",
    },
    "de": {
        "welcome": (
            "Willkommen.\n\n"
            "Dies ist kein Multiple-Choice-Test — es ist ein lebendiges diagnostisches Gespräch.\n\n"
            "Am Ende erhalten Sie eine *Persönlichkeitskarte*:\n"
            "• Enneagramm-Typ + Flügel + Instinkt\n"
            "• Wichtigste Metaprogramme\n"
            "• Ebene der Spiraldynamik\n"
            "• Werte und versteckte Überzeugungen\n\n"
            "≈ 20–30 Minuten lebendiger Dialog.\n\n"
            "Bereit? Schreiben Sie einfach etwas — und wir beginnen."
        ),
        "generating":     "⏳ Ich erstelle Ihre Persönlichkeitskarte...",
        "report_btn":     "📊 Meine Karte erhalten",
        "deepen_btn":     "🔍 Überzeugungen tiefer erforschen",
        "restart_btn":    "🔄 Neu beginnen",
        "restart_prompt": "Sprache wählen:",
    },
    "en": {
        "welcome": (
            "Welcome.\n\n"
            "This is not a multiple-choice test — it's a live diagnostic conversation.\n\n"
            "At the end, you'll receive a *Psychological Personality Map*:\n"
            "• Enneagram type + wing + instinct\n"
            "• Key meta-programs\n"
            "• Spiral Dynamics level\n"
            "• Values and hidden beliefs\n\n"
            "≈ 20–30 minutes of live dialogue.\n\n"
            "Ready? Just write something — and we'll begin."
        ),
        "generating":     "⏳ Generating your psychological map...",
        "report_btn":     "📊 Get my map",
        "deepen_btn":     "🔍 Explore beliefs deeper",
        "restart_btn":    "🔄 Start over",
        "restart_prompt": "Choose language:",
    },
    "he": {
        "welcome": (
            "ברוכים הבאים.\n\n"
            "זה לא מבחן רב-ברירה — זוהי שיחה אבחנתית חיה.\n\n"
            "בסוף תקבל *מפת אישיות פסיכולוגית*:\n"
            "• סוג אנאגרם + כנף + אינסטינקט\n"
            "• תוכניות מטא עיקריות\n"
            "• רמת דינמיקה ספירלית\n"
            "• ערכים ואמונות נסתרות\n\n"
            "≈ 20–30 דקות של דיאלוג חי.\n\n"
            "מוכן? פשוט כתוב משהו — ונתחיל."
        ),
        "generating":     "⏳ יוצר את המפה הפסיכולוגית שלך...",
        "report_btn":     "📊 קבל את המפה שלי",
        "deepen_btn":     "🔍 לחקור אמונות לעומק",
        "restart_btn":    "🔄 להתחיל מחדש",
        "restart_prompt": "בחר שפה:",
    },
}


# ── System prompt ─────────────────────────────────────────────────────────────

def system_prompt(lang: str) -> str:
    lang_rule = {
        "ru": "Веди весь диалог ТОЛЬКО на русском языке.",
        "de": "Führe das gesamte Gespräch NUR auf Deutsch.",
        "en": "Conduct the entire conversation ONLY in English.",
        "he": "נהל את כל השיחה רק בעברית. כתוב מימין לשמאל.",
    }[lang]

    return f"""
{lang_rule}

<role>
Ты — интеллектуальный диагностический ассистент.
Ты ведёшь живую беседу и одновременно строишь многоуровневый психологический профиль
по четырём моделям: Эннеаграмма, Метапрограммы НЛП, Спиральная Динамика, Ценности и Убеждения.
</role>

<dialogue_rules>
— Один вопрос за раз. Никогда не задавай список вопросов.
— После каждого ответа: кратко анализируй внутри → обновляй гипотезы → задавай следующий вопрос.
— НЕ раскрывай свои гипотезы во время диалога.
— Вопросы звучат естественно, как в живом разговоре.
— Иногда мягко отражай наблюдение: "Интересно, у тебя как будто..."
— Стиль: интеллектуальный, глубокий, спокойный, внимательный.
</dialogue_rules>

<layer_enneagram>
Выявляй глубинную мотивационную структуру.
Главное: чего избегает, что контролирует, что считает угрозой, как защищает идентичность.

Типы:
1: правильность / страх быть плохим
2: нужность / страх быть ненужным
3: успех / страх быть ничтожным
4: уникальность / страх быть обычным
5: автономия / страх истощения
6: безопасность / страх угрозы
7: свобода / страх ограничения
8: сила / страх уязвимости
9: покой / страх разрыва

Также: крыло, инстинкт (SP/SX/SO), уровень зрелости.
</layer_enneagram>

<layer_metaprograms>
Выявляй из речевых паттернов:
— К/От (мотивация достижения vs избегания)
— Я/Другие (фокус внимания)
— Общее/Частное (масштаб мышления)
— Процесс/Результат
— Сходство/Различие
— Внутренняя/Внешняя референция
— Активность/Рефлексивность
— Возможности/Процедуры
</layer_metaprograms>

<layer_spiral_dynamics>
Бежевый: выживание
Фиолетовый: племя, ритуалы
Красный: сила, эго, власть
Синий: порядок, правила, долг
Оранжевый: успех, эффективность, прагматизм
Зелёный: люди, равенство, эмпатия
Жёлтый: системность, интеграция, сложность
Бирюзовый: холистическое сознание

Ключи: отношение к власти, правилам, деньгам, свободе, коллективу, смыслу.
</layer_spiral_dynamics>

<layer_values_beliefs>
ЯВНЫЕ ЦЕННОСТИ: что называет важным, о чём говорит с энергией.

СКРЫТЫЕ УБЕЖДЕНИЯ — ищи через:
— Пресуппозиции в речи
— Противоречия между словами и поведением
— Номинализации (что стоит за "безопасность", "успех", "свобода")
— Паттерны: "я всегда", "у меня никогда", "люди обычно"
— Эмоциональные реакции
— Что подразумевается, но не сказано
</layer_values_beliefs>

<report_format>
Когда пользователь просит отчёт, генерируй строго в этом формате:

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🗺 ПСИХОЛОГИЧЕСКАЯ КАРТА
━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔷 ЭННЕАГРАММА
Тип [X][w][Y] · [инстинкт] · Уровень [N]
[3-4 предложения об основной структуре]

🔷 МЕТАПРОГРАММЫ
[5-6 ключевых с кратким пояснением каждой]

🔷 СПИРАЛЬНАЯ ДИНАМИКА
Центр тяжести: [Цвет]
[2-3 предложения о ценностной системе]

🔷 ЯВНЫЕ ЦЕННОСТИ
[4-6 ценностей с объяснением]

🔷 СКРЫТЫЕ УБЕЖДЕНИЯ
⚠ [убеждение 1] — [мягкое наблюдение]
⚠ [убеждение 2] — [мягкое наблюдение]
⚠ [убеждение 3] — [мягкое наблюдение]
━━━━━━━━━━━━━━━━━━━━━━━━━━━

После отчёта добавь приглашение исследовать убеждения глубже.
В самом конце напиши маркер: ###REPORT_DONE###
</report_format>

<deepening_beliefs>
Если пользователь хочет углубиться в скрытые убеждения:
— Возьми каждое убеждение из отчёта
— Покажи как оно проявляется в конкретных ситуациях из его рассказов
— Объясни какую защитную функцию оно выполняет
— Покажи какую цену человек платит за это убеждение
— Спроси: когда это убеждение могло сформироваться?
— Будь бережным, как мудрый наблюдатель — не как терапевт в лоб
</deepening_beliefs>

<forbidden>
Запрещено: давать тип сразу, задавать несколько вопросов сразу,
путать интроверсию с типом 5, тревожность с типом 6, эмоциональность с типом 4.
</forbidden>
"""


# ── Keyboards ─────────────────────────────────────────────────────────────────

def kb_language():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton(text="🇩🇪 Deutsch",  callback_data="lang_de"),
        ],
        [
            InlineKeyboardButton(text="🇬🇧 English",  callback_data="lang_en"),
            InlineKeyboardButton(text="🇮🇱 עברית",    callback_data="lang_he"),
        ],
    ])

def kb_dialogue(lang: str):
    ui = UI[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ui["report_btn"],  callback_data="get_report")],
        [InlineKeyboardButton(text=ui["restart_btn"], callback_data="restart")],
    ])

def kb_after_report(lang: str):
    ui = UI[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ui["deepen_btn"],  callback_data="deepen_beliefs")],
        [InlineKeyboardButton(text=ui["restart_btn"], callback_data="restart")],
    ])

def kb_restart(lang: str):
    ui = UI[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ui["restart_btn"], callback_data="restart")],
    ])


# ── Claude helper ─────────────────────────────────────────────────────────────

async def ask_claude(lang: str, history: list, extra_user_msg: str = None) -> str:
    msgs = history.copy()
    if extra_user_msg:
        msgs.append({"role": "user", "content": extra_user_msg})
    response = await client.messages.create(
        model="claude-sonnet-4-5-20251001",
        max_tokens=1500,
        system=system_prompt(lang),
        messages=msgs,
    )
    return response.content[0].text


# ── Handlers ──────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
@dp.message(Command("restart"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Session.choosing_language)
    await message.answer(
        "Выберите язык / Choose language / Sprache wählen / בחר שפה",
        reply_markup=kb_language()
    )


@dp.callback_query(F.data.startswith("lang_"))
async def cb_language(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    await state.update_data(lang=lang, history=[], msg_count=0)
    await state.set_state(Session.in_dialogue)
    await callback.message.edit_text(UI[lang]["welcome"], parse_mode="Markdown")

    # Get opening question from Claude
    seed = [{"role": "user", "content": "Начни диагностику."}]
    reply = await ask_claude(lang, seed)
    history = seed + [{"role": "assistant", "content": reply}]
    await state.update_data(history=history)

    await callback.message.answer(reply)
    await callback.answer()


@dp.callback_query(F.data == "get_report")
async def cb_get_report(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await callback.message.answer(UI[lang]["generating"])
    await callback.answer()
    await _generate_report(callback.message, state, data)


@dp.callback_query(F.data == "deepen_beliefs")
async def cb_deepen(callback: CallbackQuery, state: FSMContext):
    data  = await state.get_data()
    lang  = data.get("lang", "ru")
    history = data.get("history", [])

    await state.set_state(Session.deepening_beliefs)
    await bot.send_chat_action(callback.message.chat.id, "typing")

    reply = await ask_claude(lang, history, "Да, хочу исследовать скрытые убеждения глубже.")
    history += [
        {"role": "user",      "content": "Да, хочу исследовать скрытые убеждения глубже."},
        {"role": "assistant", "content": reply},
    ]
    await state.update_data(history=history)
    await callback.message.answer(reply, reply_markup=kb_restart(lang))
    await callback.answer()


@dp.callback_query(F.data == "restart")
async def cb_restart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(Session.choosing_language)
    await callback.message.answer(
        "Выберите язык / Choose language / Sprache wählen / בחר שפה",
        reply_markup=kb_language()
    )
    await callback.answer()


@dp.message(Session.in_dialogue)
async def handle_dialogue(message: Message, state: FSMContext):
    data      = await state.get_data()
    lang      = data.get("lang", "ru")
    history   = data.get("history", [])
    msg_count = data.get("msg_count", 0) + 1

    history.append({"role": "user", "content": message.text})
    await bot.send_chat_action(message.chat.id, "typing")

    reply = await ask_claude(lang, history)
    history.append({"role": "assistant", "content": reply})
    await state.update_data(history=history, msg_count=msg_count)

    markup = kb_dialogue(lang) if msg_count >= 8 else None
    await message.answer(reply, reply_markup=markup)


@dp.message(Session.deepening_beliefs)
async def handle_deepening(message: Message, state: FSMContext):
    data    = await state.get_data()
    lang    = data.get("lang", "ru")
    history = data.get("history", [])

    history.append({"role": "user", "content": message.text})
    await bot.send_chat_action(message.chat.id, "typing")

    reply = await ask_claude(lang, history)
    history.append({"role": "assistant", "content": reply})
    await state.update_data(history=history)
    await message.answer(reply, reply_markup=kb_restart(lang))


# ── Report generator ──────────────────────────────────────────────────────────

async def _generate_report(message: Message, state: FSMContext, data: dict):
    lang    = data.get("lang", "ru")
    history = data.get("history", [])

    await bot.send_chat_action(message.chat.id, "typing")

    report = await ask_claude(
        lang, history,
        "Сгенерируй мою полную психологическую карту личности."
    )

    history += [
        {"role": "user",      "content": "Сгенерируй мою полную психологическую карту личности."},
        {"role": "assistant", "content": report},
    ]
    await state.update_data(history=history)
    await state.set_state(Session.viewing_report)

    clean = report.replace("###REPORT_DONE###", "").strip()
    await message.answer(clean, reply_markup=kb_after_report(lang))


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
