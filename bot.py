import telebot
import pandas as pd
from datetime import datetime, date
import time
import schedule
import threading
import logging
import os

# ---------------------- НАСТРОЙКИ ----------------------
TOKEN = "8336094671:AAE7Znbcyc3f4Jr637HeLDwyTLpjiBQgcRw"  # ← сюда свой токен
EXCEL_FILE = "accounts.xlsx"
ADMIN_CHAT_ID = 519114250  # ← твой Telegram ID (чтобы только тебе приходили напоминания)
CHECK_TIME = "09:00"  # во сколько проверять и отправлять напоминания

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("reminders.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TOKEN)


# ---------------------- ФУНКЦИИ ----------------------

def load_accounts():
    """Читает excel и возвращает список словарей"""
    try:
        df = pd.read_excel(EXCEL_FILE, dtype=str)
        df = df.dropna(subset=['Аккаунт', 'Дата_пополнения'])

        accounts = []
        for _, row in df.iterrows():
            try:
                date_str = str(row['Дата_пополнения']).strip()  # на всякий случай в строку

                if ' ' in date_str:  # убираем время, если есть (типа "2026-02-06 00:00:00")
                    date_str = date_str.split(' ')[0]

                if '.' in date_str:  # формат 06.02.2026
                    d, m, y = date_str.split('.')
                    dt = datetime(int(y), int(m), int(d))

                elif '-' in date_str:  # формат 2026-02-06 или 2026-2-6
                    parts = date_str.split('-')
                    if len(parts) == 3:
                        y, m, d = parts
                        dt = datetime(int(y), int(m), int(d))
                    else:
                        raise ValueError("Неверный формат даты с '-'")

                else:
                    raise ValueError("Неизвестный формат даты")

                accounts.append({
                    'account': row['Аккаунт'].strip(),
                    'date': dt.date(),
                    'sum': row.get('Сумма', 'не указана'),
                    'comment': row.get('Комментарий', '')
                })

            except Exception as e:
                logger.error(f"Ошибка парсинга даты '{row['Дата_пополнения']}': {e}")
                continue  # пропускаем строку с ошибкой, чтобы бот не падал
        return accounts
    except Exception as e:
        logger.error(f"Не удалось прочитать файл {EXCEL_FILE}: {e}")
        return []


def check_reminders():
    """Проверяет, есть ли сегодня пополнения"""
    today = date.today()
    accounts = load_accounts()

    reminders = [acc for acc in accounts if acc['date'] == today]

    if not reminders:
        logger.info(f"{today} — нет напоминаний")
        return

    message = f"🔔 Напоминания на {today.strftime('%d.%m.%Y')}:\n\n"

    for r in reminders:
        line = f"• {r['account']}"
        if r['sum'] != 'не указана':
            line += f" — {r['sum']} ₽"
        if r['comment']:
            line += f" ({r['comment']})"
        message += line + "\n"

    try:
        bot.send_message(ADMIN_CHAT_ID, message)
        logger.info(f"Отправлено напоминание: {len(reminders)} аккаунтов")
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")


def run_scheduler():
    """Запускает проверку по расписанию"""
    schedule.every().day.at(CHECK_TIME).do(check_reminders)

    logger.info(f"Планировщик запущен. Проверка каждый день в {CHECK_TIME}")

    while True:
        schedule.run_pending()
        time.sleep(60)


# ---------------------- КОМАНДЫ БОТА ----------------------

@bot.message_handler(commands=['info'])
def show_info(message):
    bot.reply_to(message, message.chat.id)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if message.chat.id != ADMIN_CHAT_ID:
        bot.reply_to(message, "Извини, этот бот только для владельца.")
        return

    text = (
        "Привет! Я бот-напоминалка о пополнениях счетов.\n\n"
        "Команды:\n"
        "/today — показать, что нужно пополнить сегодня\n"
        "/reload — перезагрузить данные из excel\n"
        "/list — показать все будущие напоминания\n\n"
        "Данные берутся из файла accounts.xlsx\n"
        "Формат даты: 05.02.2026"
    )
    bot.reply_to(message, text)


@bot.message_handler(commands=['today'])
def show_today(message):
    if message.chat.id != ADMIN_CHAT_ID:
        return
    today = date.today()
    accounts = load_accounts()
    reminders = [acc for acc in accounts if acc['date'] == today]

    if not reminders:
        bot.reply_to(message, f"Сегодня ({today.strftime('%d.%m.%Y')}) ничего пополнять не нужно.")
        return

    text = f"Сегодня нужно пополнить:\n\n"
    for r in reminders:
        text += f"• {r['account']} — {r['sum']}"
        if r['comment']:
            text += f" ({r['comment']})"
        text += "\n"
    bot.reply_to(message, text)


@bot.message_handler(commands=['reload'])
def reload(message):
    if message.chat.id != ADMIN_CHAT_ID:
        return
    check_reminders()
    bot.reply_to(message, "Данные перезагружены и проверка выполнена.")


@bot.message_handler(commands=['list'])
def show_all(message):
    if message.chat.id != ADMIN_CHAT_ID:
        return

    accounts = load_accounts()
    today = date.today()

    future = [acc for acc in accounts if acc['date'] >= today]
    future.sort(key=lambda x: x['date'])

    if not future:
        bot.reply_to(message, "Нет будущих напоминаний.")
        return

    text = "Ближайшие пополнения:\n\n"
    for acc in future:
        text += f"{acc['date'].strftime('%d.%m.%Y')} — {acc['account']}"
        if acc['sum'] != 'не указана':
            text += f" ({acc['sum']} ₽)"
        if acc['comment']:
            text += f" — {acc['comment']}"
        text += "\n"

    bot.reply_to(message, text)


# ---------------------- ЗАПУСК ----------------------

if __name__ == "__main__":
    logger.info("Бот запущен")

    # Проверка сразу при старте
    check_reminders()

    # Запуск планировщика в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    # Запуск бота
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"Критическая ошибка бота: {e}")
        time.sleep(30)
        os._exit(1)