#!/usr/bin/env python3
"""
ALEM B24 Telegram Bot
Ассистент по задачам Битрикс24 с AI (Claude)
"""

import os
import json
import logging
import requests
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ─── НАСТРОЙКИ ────────────────────────────────────────────────────────
TELEGRAM_TOKEN = "8712617410:AAHMKA4V1IJnvAGnpJwouvBMHhTlG1-l7Yw"
BITRIX_WEBHOOK = "https://alem.bitrix24.kz/rest/1/8cgdvpljebwpyx7r"
ANTHROPIC_API_KEY = ""  # Вставьте ваш ключ Claude API (опционально)

# Только эти Telegram ID могут пользоваться ботом (безопасность)
ALLOWED_USERS = []  # Оставьте пустым для доступа всем, или добавьте ваш ID

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── БИТРИКС24 API ────────────────────────────────────────────────────
def b24(method, params=None):
    if params is None:
        params = {}
    url = f"{BITRIX_WEBHOOK}/{method}"
    try:
        resp = requests.get(url, params=flatten(params), timeout=15)
        data = resp.json()
        return data.get('result')
    except Exception as e:
        logger.error(f"B24 error {method}: {e}")
        return None

def flatten(d, prefix=''):
    result = {}
    for k, v in d.items():
        key = f"{prefix}[{k}]" if prefix else k
        if isinstance(v, dict):
            result.update(flatten(v, key))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                result[f"{key}[{i}]"] = item
        else:
            result[key] = v
    return result

# ─── ФОРМАТИРОВАНИЕ ───────────────────────────────────────────────────
STATUS_MAP = {
    '1': '🆕 Новая', '2': '🔄 В работе', '3': '✅ Завершена',
    '4': '⏳ Ждёт ответа', '5': '👁 На контроле', '6': '🔒 Закрыта',
}
PRIORITY_MAP = {'0': '⬇️ Низкий', '1': '➡️ Средний', '2': '🔴 Высокий'}

def fmt_date(s):
    if not s:
        return 'нет'
    try:
        d = datetime.fromisoformat(s.replace('Z', '+00:00'))
        return d.strftime('%d.%m.%Y')
    except:
        return s[:10]

def is_overdue(deadline_str):
    if not deadline_str:
        return False
    try:
        dl = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
        return dl.replace(tzinfo=None) < datetime.now()
    except:
        return False

# ─── ПРОВЕРКА ДОСТУПА ─────────────────────────────────────────────────
def check_access(user_id):
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

# ─── КОМАНДЫ ──────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_access(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    text = (
        "👋 *Привет! Я ваш ассистент Alem B24*\n\n"
        "Я подключён к вашему Битрикс24 и помогаю управлять задачами.\n\n"
        "📋 *Команды:*\n"
        "/tasks — мои активные задачи\n"
        "/overdue — просроченные задачи\n"
        "/today — задачи на сегодня\n"
        "/projects — список проектов\n"
        "/crm — открытые сделки CRM\n"
        "/new [название] — создать задачу\n"
        "/help — помощь\n\n"
        "💬 *Или просто напишите мне текстом:*\n"
        "«Покажи задачи по EVENTER»\n"
        "«Создай задачу: подготовить презентацию»\n"
        "«Что срочного на сегодня?»"
    )
    await update.message.reply_text(text, parse_mode='Markdown')


async def cmd_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_access(update.effective_user.id):
        return
    await update.message.reply_text("⏳ Загружаю задачи...")
    result = b24('tasks.task.list', {
        'filter': {'!STATUS': [3, 6, 7]},
        'select': ['ID', 'TITLE', 'STATUS', 'PRIORITY', 'DEADLINE', 'GROUP_ID'],
        'order': {'DEADLINE': 'ASC'},
        'params': {'PAGING': {'PAGE_SIZE': 30}}
    })
    tasks = result.get('tasks', []) if result else []
    if not tasks:
        await update.message.reply_text("✅ Нет активных задач!")
        return

    lines = [f"📋 *Активные задачи ({len(tasks)}):*\n"]
    for t in tasks[:20]:
        overdue = '🔴 ' if is_overdue(t.get('deadline')) else ''
        prio = '❗' if t.get('priority') == '2' else ''
        dl = fmt_date(t.get('deadline'))
        status = STATUS_MAP.get(t.get('status', '1'), '—')
        lines.append(
            f"{overdue}{prio}*{t['title']}*\n"
            f"  {status} | 📅 {dl} | #{t['id']}\n"
        )

    keyboard = [[
        InlineKeyboardButton("🔴 Просроченные", callback_data="overdue"),
        InlineKeyboardButton("📁 Проекты", callback_data="projects"),
    ]]
    await update.message.reply_text(
        '\n'.join(lines),
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cmd_overdue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_access(update.effective_user.id):
        return
    await update.message.reply_text("⏳ Проверяю просроченные...")
    result = b24('tasks.task.list', {
        'filter': {'!STATUS': [3, 6, 7], '<=DEADLINE': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')},
        'select': ['ID', 'TITLE', 'STATUS', 'PRIORITY', 'DEADLINE', 'GROUP_ID'],
        'order': {'DEADLINE': 'ASC'},
        'params': {'PAGING': {'PAGE_SIZE': 30}}
    })
    tasks = result.get('tasks', []) if result else []
    overdue = [t for t in tasks if is_overdue(t.get('deadline'))]

    if not overdue:
        await update.message.reply_text("🎉 Нет просроченных задач! Отлично!")
        return

    lines = [f"🔴 *Просроченные задачи ({len(overdue)}):*\n"]
    for t in overdue:
        dl = fmt_date(t.get('deadline'))
        try:
            d = datetime.fromisoformat(t['deadline'].replace('Z', '+00:00'))
            days = (datetime.now() - d.replace(tzinfo=None)).days
            days_str = f"просрочено {days}д"
        except:
            days_str = ''
        lines.append(f"🔴 *{t['title']}*\n  📅 {dl} ({days_str}) | #{t['id']}\n")

    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')


def parse_date_from_text(text):
    """Извлекает дату из текста. Возвращает datetime или None."""
    today = datetime.now()
    text_lower = text.lower()

    # Сегодня / завтра / послезавтра
    if any(w in text_lower for w in ['сегодня', 'today']):
        return today
    if any(w in text_lower for w in ['завтра', 'tomorrow']):
        return today + timedelta(days=1)
    if 'послезавтра' in text_lower:
        return today + timedelta(days=2)

    # Дни недели
    days_ru = {'понедельник': 0, 'вторник': 1, 'среда': 2, 'среду': 2,
               'четверг': 3, 'пятница': 4, 'пятницу': 4, 'суббота': 5,
               'субботу': 5, 'воскресенье': 6}
    for day_name, day_num in days_ru.items():
        if day_name in text_lower:
            diff = (day_num - today.weekday()) % 7
            if diff == 0:
                diff = 7
            return today + timedelta(days=diff)

    # Форматы: "9 марта", "09.03", "09.03.2026", "2026-03-09"
    months_ru = {'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
                 'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
                 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12}

    # "9 марта" или "9 марта 2026"
    for month_name, month_num in months_ru.items():
        pattern = rf'(\d{{1,2}})\s+{month_name}(?:\s+(\d{{4}}))?'
        m = re.search(pattern, text_lower)
        if m:
            day = int(m.group(1))
            year = int(m.group(2)) if m.group(2) else today.year
            try:
                return datetime(year, month_num, day)
            except:
                pass

    # "09.03.2026" или "09.03"
    m = re.search(r'(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?', text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            return datetime(year, month, day)
        except:
            pass

    # "2026-03-09"
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except:
            pass

    return None


async def cmd_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_access(update.effective_user.id):
        return
    await tasks_for_date(update, datetime.now(), "сегодня")


async def tasks_for_date(update, target_date, label):
    """Показывает задачи с дедлайном на конкретную дату."""
    date_str = target_date.strftime('%d.%m.%Y')
    await update.message.reply_text(f"⏳ Загружаю задачи на {date_str}...")

    date_start = target_date.strftime('%Y-%m-%dT00:00:00')
    date_end = target_date.strftime('%Y-%m-%dT23:59:59')

    result = b24('tasks.task.list', {
        'filter': {
            '!STATUS': [3, 6, 7],
            '>=DEADLINE': date_start,
            '<=DEADLINE': date_end,
        },
        'select': ['ID', 'TITLE', 'STATUS', 'PRIORITY', 'DEADLINE', 'GROUP_ID'],
        'order': {'PRIORITY': 'DESC'},
        'params': {'PAGING': {'PAGE_SIZE': 50}}
    })
    tasks = result.get('tasks', []) if result else []

    if not tasks:
        await update.message.reply_text(
            f"✅ На {date_str} задач с дедлайном нет.\n\n"
            f"Хотите посмотреть *все активные задачи*? Напишите /tasks",
            parse_mode='Markdown'
        )
        return

    lines = [f"📅 *Задачи на {date_str} ({len(tasks)}):*\n"]
    for t in tasks:
        overdue = '🔴 ' if is_overdue(t.get('deadline')) else ''
        prio = PRIORITY_MAP.get(t.get('priority', '1'), '')
        status = STATUS_MAP.get(t.get('status', '1'), '—')
        lines.append(f"{overdue}*{t['title']}*\n  {status} | {prio} | #{t['id']}\n")

    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')


async def cmd_projects(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_access(update.effective_user.id):
        return
    await update.message.reply_text("⏳ Загружаю проекты...")
    result = b24('sonet_group.get', {'filter': {'ACTIVE': 'Y'}})
    groups = result if isinstance(result, list) else (result.get('workgroups', []) if result else [])

    if not groups:
        await update.message.reply_text("Проекты не найдены.")
        return

    lines = [f"📁 *Проекты ({len(groups)}):*\n"]
    buttons = []
    for g in groups[:15]:
        lines.append(f"📁 *{g['name']}* (#{g['id']})\n  👥 {g.get('numberOfMembers', 0)} участников\n")
        buttons.append([InlineKeyboardButton(
            f"📋 Задачи: {g['name'][:30]}",
            callback_data=f"project_tasks_{g['id']}_{g['name'][:20]}"
        )])

    await update.message.reply_text(
        '\n'.join(lines),
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def cmd_crm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_access(update.effective_user.id):
        return
    await update.message.reply_text("⏳ Загружаю сделки CRM...")
    result = b24('crm.deal.list', {
        'filter': {'CLOSED': 'N'},
        'select': ['ID', 'TITLE', 'OPPORTUNITY', 'CURRENCY_ID', 'STAGE_ID', 'COMPANY_TITLE'],
        'order': {'DATE_CREATE': 'DESC'},
    })
    deals = result if isinstance(result, list) else []

    if not deals:
        await update.message.reply_text("💼 Открытых сделок нет.")
        return

    lines = [f"💼 *Открытые сделки CRM ({len(deals)}):*\n"]
    for d in deals[:15]:
        amt = float(d.get('opportunity', 0) or 0)
        amt_str = f"{amt:,.0f} {d.get('currencyId', '')}" if amt else '—'
        company = d.get('companyTitle', '—')
        lines.append(
            f"💼 *{d['title']}*\n"
            f"  🏢 {company} | 💰 {amt_str}\n"
            f"  📊 {d.get('stageId', '—')} | #{d['id']}\n"
        )

    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')


async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_access(update.effective_user.id):
        return
    title = ' '.join(ctx.args) if ctx.args else ''
    if not title:
        await update.message.reply_text(
            "📝 Напишите название задачи:\n`/new Подготовить презентацию для инвестора`",
            parse_mode='Markdown'
        )
        return
    result = b24('tasks.task.add', {'fields': {'TITLE': title, 'PRIORITY': '1'}})
    task_id = result.get('task', {}).get('id') if result else None
    if task_id:
        await update.message.reply_text(
            f"✅ Задача создана!\n*{title}*\nID: #{task_id}",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("❌ Не удалось создать задачу. Проверьте подключение.")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *Alem B24 Assistant — Помощь*\n\n"
        "*Команды:*\n"
        "/tasks — все активные задачи\n"
        "/overdue — просроченные задачи\n"
        "/today — задачи на сегодня\n"
        "/projects — проекты и группы\n"
        "/crm — сделки CRM\n"
        "/new [название] — создать задачу\n\n"
        "*Текстовые запросы:*\n"
        "Просто напишите мне — я пойму!\n\n"
        "«задачи eventer» — задачи по проекту\n"
        "«создай задачу: ...» — новая задача\n"
        "«что срочного?» — приоритеты дня\n"
        "«просроченные» — просроченные задачи\n"
    )
    await update.message.reply_text(text, parse_mode='Markdown')


# ─── ТЕКСТОВЫЕ СООБЩЕНИЯ (умный разбор) ──────────────────────────────

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_access(update.effective_user.id):
        return
    text = update.message.text.lower().strip()

    # Создать задачу
    if any(w in text for w in ['создай задачу', 'создать задачу', 'новая задача', 'добавь задачу']):
        title = update.message.text
        for w in ['создай задачу:', 'создай задачу', 'создать задачу:', 'новая задача:', 'добавь задачу:']:
            title = title.replace(w, '').replace(w.capitalize(), '').strip()
        if title:
            result = b24('tasks.task.add', {'fields': {'TITLE': title, 'PRIORITY': '1'}})
            task_id = result.get('task', {}).get('id') if result else None
            if task_id:
                await update.message.reply_text(f"✅ Задача создана!\n*{title}*\n#️⃣ #{task_id}", parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Не удалось создать задачу.")
        else:
            await update.message.reply_text("Напишите название: «Создай задачу: Подготовить отчёт»")
        return

    # Просроченные
    if any(w in text for w in ['просроч', 'overdue', 'опоздал', 'долг']):
        await cmd_overdue(update, ctx)
        return

    # Дата в тексте — «задачи на 9 марта», «на завтра», «на пятницу»
    if any(w in text for w in ['на ', 'задачи ']):
        target_date = parse_date_from_text(text)
        if target_date:
            await tasks_for_date(update, target_date, target_date.strftime('%d.%m.%Y'))
            return

    # Сегодня
    if any(w in text for w in ['сегодня', 'today']):
        await cmd_today(update, ctx)
        return

    # CRM
    if any(w in text for w in ['crm', 'сделк', 'клиент', 'продаж']):
        await cmd_crm(update, ctx)
        return

    # Проекты
    if any(w in text for w in ['проект', 'group', 'группа']):
        # Поиск задач по конкретному проекту
        keywords = ['eventer', 'afisha', 'entertainment city', 'alem']
        for kw in keywords:
            if kw in text:
                await search_project_tasks(update, kw)
                return
        await cmd_projects(update, ctx)
        return

    # Задачи
    if any(w in text for w in ['задач', 'task', 'дела', 'что делать']):
        await cmd_tasks(update, ctx)
        return

    # По умолчанию — показать меню
    keyboard = [
        [InlineKeyboardButton("📋 Задачи", callback_data="tasks"),
         InlineKeyboardButton("🔴 Просроченные", callback_data="overdue")],
        [InlineKeyboardButton("📁 Проекты", callback_data="projects"),
         InlineKeyboardButton("💼 CRM", callback_data="crm")],
        [InlineKeyboardButton("📅 Сегодня", callback_data="today")],
    ]
    await update.message.reply_text(
        f"Не совсем понял 🤔 Что показать?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def search_project_tasks(update, keyword):
    await update.message.reply_text(f"🔍 Ищу задачи по «{keyword}»...")
    result = b24('tasks.task.list', {
        'filter': {'!STATUS': [3, 6, 7], '%TITLE': keyword},
        'select': ['ID', 'TITLE', 'STATUS', 'PRIORITY', 'DEADLINE'],
        'params': {'PAGING': {'PAGE_SIZE': 30}}
    })
    tasks = result.get('tasks', []) if result else []
    if not tasks:
        await update.message.reply_text(f"Задач по «{keyword}» не найдено.")
        return
    lines = [f"📋 *Задачи по «{keyword}» ({len(tasks)}):*\n"]
    for t in tasks:
        overdue = '🔴 ' if is_overdue(t.get('deadline')) else ''
        lines.append(f"{overdue}*{t['title']}*\n  {STATUS_MAP.get(t.get('status','1'),'—')} | 📅 {fmt_date(t.get('deadline'))} | #{t['id']}\n")
    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')


# ─── КНОПКИ (Inline) ──────────────────────────────────────────────────

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    fake_update = update
    fake_update._effective_message = query.message

    if data == 'tasks':
        await cmd_tasks(fake_update, ctx)
    elif data == 'overdue':
        await cmd_overdue(fake_update, ctx)
    elif data == 'projects':
        await cmd_projects(fake_update, ctx)
    elif data == 'crm':
        await cmd_crm(fake_update, ctx)
    elif data == 'today':
        await cmd_today(fake_update, ctx)
    elif data.startswith('project_tasks_'):
        parts = data.split('_', 4)
        group_id = parts[3]
        group_name = parts[4] if len(parts) > 4 else 'проект'
        await query.message.reply_text(f"⏳ Загружаю задачи проекта «{group_name}»...")
        result = b24('tasks.task.list', {
            'filter': {'!STATUS': [3, 6, 7], 'GROUP_ID': group_id},
            'select': ['ID', 'TITLE', 'STATUS', 'PRIORITY', 'DEADLINE'],
            'params': {'PAGING': {'PAGE_SIZE': 30}}
        })
        tasks = result.get('tasks', []) if result else []
        if not tasks:
            await query.message.reply_text(f"✅ Нет активных задач в «{group_name}»")
            return
        lines = [f"📋 *{group_name} ({len(tasks)} задач):*\n"]
        for t in tasks:
            overdue = '🔴 ' if is_overdue(t.get('deadline')) else ''
            lines.append(f"{overdue}*{t['title']}*\n  {STATUS_MAP.get(t.get('status','1'),'—')} | 📅 {fmt_date(t.get('deadline'))} | #{t['id']}\n")
        await query.message.reply_text('\n'.join(lines), parse_mode='Markdown')


# ─── ЗАПУСК ───────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("overdue", cmd_overdue))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("projects", cmd_projects))
    app.add_handler(CommandHandler("crm", cmd_crm))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🤖 Alem B24 Bot запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()
