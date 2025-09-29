import logging
import time
import threading
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# === Настройки Telegram-бота ===
TOKEN = '8360255097:AAE4RCe_x_xKNDbDFBuhcKVhY17C2JjZ9Sk'

# === Глобальные переменные ===
current_schedule = ""
active_chats = set()  # Множество chat_id, которые общались с ботом
driver = None  # Глобальный экземпляр драйвера

# === Инициализация драйвера ===
def init_driver():
    global driver
    if driver is None:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        driver = webdriver.Chrome(options=options)

# === Закрытие драйвера ===
def close_driver():
    global driver
    if driver:
        driver.quit()
        driver = None

# === Парсер расписания (с переиспользованием драйвера) ===
def get_schedule():
    global driver
    try:
        if driver is None:
            init_driver()

        driver.get("https://www.ямк-салехард.рф/")
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        # Клик по "Техническому профилю"
        tech_dept = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@value='otp']")))
        tech_dept.click()

        # Ждём появление кнопки "24ВЕБ"
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@value='24ВЕБ']")))

        # Клик по "24ВЕБ"
        group_24veb = driver.find_element(By.XPATH, "//button[@value='24ВЕБ']")
        group_24veb.click()

        # Ждём модальное окно
        wait.until(EC.visibility_of_element_located((By.ID, "modal1")))
        time.sleep(2)

        # Получаем HTML
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')

        modal = soup.find('div', id='modal1')
        schedule_text = ""
        if modal:
            schedule_divs = modal.find_all('div', class_='container_table uchen')

            for i, div in enumerate(schedule_divs):
                day_header = div.find_previous_sibling('div', class_='day_header')
                day_title = day_header.get_text(strip=True) if day_header else f"День {i+1}"
                schedule_text += f"\n<b>📅 {day_title}</b>\n\n"

                table = div.find('table')
                if table:
                    rows = table.find_all('tr')
                    for idx, row in enumerate(rows):
                        cells = row.find_all(['th', 'td'])
                        cell_texts = [cell.get_text(strip=True) for cell in cells]

                        # Пропускаем заголовок таблицы (обычно это ['Пара', 'предмет', ...])
                        if idx == 0 and 'Пара' in cell_texts:
                            continue

                        # Обработка строки: Пара | Предмет | Кабинет | Преподаватель | Время
                        if len(cell_texts) >= 4:
                            para = cell_texts[0] if cell_texts[0] else "–"
                            predmet = cell_texts[1] if len(cell_texts) > 1 and cell_texts[1] else "–"
                            kabinet = cell_texts[2] if len(cell_texts) > 2 and cell_texts[2] else "–"
                            prepod = cell_texts[3] if len(cell_texts) > 3 and cell_texts[3] else "–"
                            vremya = cell_texts[4] if len(cell_texts) > 4 and cell_texts[4] else "–"

                            # Форматируем строку красиво
                            schedule_text += f"<b>{para}</b> — {predmet}\n"
                            schedule_text += f"     📍 {kabinet} | 👨‍🏫 {prepod} | ⏰ {vremya}\n\n"
                        elif len(cell_texts) == 1 and cell_texts[0] and '–' not in cell_texts[0]:
                            # Это строка с временем (например: 09:05-09:50)
                            schedule_text += f"     ⏰ {cell_texts[0]}\n\n"
                else:
                    schedule_text += "❌ Расписание не найдено.\n\n"

        else:
            schedule_text = "❌ Не найдено модальное окно с расписанием"

    except Exception as e:
        schedule_text = f"❌ Ошибка при получении расписания: {e}"

    return schedule_text


# === Функция для проверки обновлений ===
async def check_schedule_updates(app):
    global current_schedule

    while True:
        new_schedule = get_schedule()

        if new_schedule != current_schedule:
            if current_schedule:
                # Было обновление!
                print("Обнаружено обновление расписания!")
                # Отправляем всем чатам асинхронно
                tasks = []
                for chat_id in active_chats:
                    task = app.bot.send_message(chat_id=chat_id, text="🔄 Расписание обновилось!\n\n" + new_schedule, parse_mode='HTML')
                    tasks.append(task)

                # Выполняем все отправки параллельно
                try:
                    await asyncio.gather(*tasks, return_exceptions=True)
                except Exception as e:
                    print(f"Ошибка при отправке уведомлений: {e}")

            current_schedule = new_schedule

        # Ждём 30 минут перед следующей проверкой
        time.sleep(1800)  # 1800 секунд = 30 минут


# === Команды бота ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    active_chats.add(chat_id)

    await update.message.reply_text(
        "Привет! Я буду присылать обновления расписания автоматически.\n"
        "Нажми /get_schedule, чтобы получить расписание группы 24ВЕБ."
    )


async def get_schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    active_chats.add(chat_id)

    await update.message.reply_text("Получаю расписание...")

    schedule = get_schedule()
    await context.bot.send_message(chat_id=chat_id, text=schedule, parse_mode='HTML')


def main():
    global current_schedule
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("get_schedule", get_schedule_command))

    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    # Запускаем проверку обновлений в отдельном потоке
    def run_scheduler():
        import asyncio
        # Для работы с asyncio в потоке
        asyncio.run(check_schedule_updates(application))

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    print("Бот запущен...")
    application.run_polling()


if __name__ == '__main__':
    try:
        main()
    finally:
        close_driver()