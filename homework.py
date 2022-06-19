import exceptions
import logging
import os
import sys
import time
from datetime import datetime
from http import HTTPStatus
from typing import Dict, List, Union

import requests
import telegram
import telegram.ext
from dotenv import load_dotenv
from telegram.error import TelegramError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv()


PRACTICUM_TOKEN = os.getenv('TOKEN_PRACTICUM')
TELEGRAM_TOKEN = os.getenv('TOKEN_TELEGRAM')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICT = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        logging.info(f'Отправляем сообщение в телеграм: {message}')
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except TelegramError as error:
        message = f'Ошибка отправки сообщения в телеграм: {error}'
        raise exceptions.ErrorSendMessage(message)
    else:
        logging.info('Сообщение в телеграм успешно отправлено')


def get_api_answer(current_timestamp) -> Dict[str, Union[int, List]]:
    """Делает запрос к API Яндекс.Практикума и возвращает ответ."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    logging.info(
        'Запрашиваем список домаших работ '
        f'по временной метке {current_timestamp}'
    )
    try:
        homeworks_list = requests.get(
            ENDPOINT, headers=HEADERS, params=params)
    except ConnectionError as error:
        message = f'Ошибка подключения к серверу: {error}'
        raise exceptions.ErrorServerConnection(message)
    if homeworks_list.status_code != HTTPStatus.OK:
        message = (
            'Неверный ответ сервера: '
            f'http code = {homeworks_list.status_code}; '
            f'reason = {homeworks_list.reason}; '
            f'content = {homeworks_list.text}'
        )
        raise exceptions.ErrorStatusCode(message)
    homeworks_list = homeworks_list.json()
    if len(homeworks_list) == 0:
        logging.info('За последнее время нет домашних работ')
    return homeworks_list


def check_response(
    response: Dict[str, Union[int, List]]
) -> Dict[str, Union[int, str, datetime]]:
    """Проверяет ответ API на корректность."""
    logging.info('Проверка ответа от API начата.')
    if not isinstance(response, dict):
        message = f'Ответ от API не является списком: response = {response}'
        raise TypeError(message)
    logging.info('Корректный ответ API')
    current_date = response.get('current_date')
    if current_date is None:
        message = 'В ответе от API нет даты'
        raise KeyError(message)
    homework = response.get('homeworks')
    if homework is None:
        message = 'В ответе от API нет домашней работы'
        raise KeyError(message)
    if not isinstance(homework, list):
        message = (
            'Ответ от API по ключу homework '
            f'не является списком: {homework}'
        )
        raise TypeError(message)
    if len(homework) == 0:
        message = 'Список домашних работ пуст'
        logging.info(message)
    return homework


def parse_status(homework):
    """Извлечение информации о статусе домашней работы."""
    logging.info('Получение данных из домашей работы')
    homework_name = homework['homework_name']
    if homework_name is None:
        message = 'Ошибка ключа домашней работы'
        raise exceptions.KeyErrorInHomework(message)
    homework_status = homework.get('status')
    if homework_status is None:
        message = 'В домашней работе нет статуса'
        raise exceptions.KeyErrorInHomework(message)
    if homework_status not in HOMEWORK_VERDICT:
        message = f'Среди корректных статусов такого нет: {homework_status}'
        raise exceptions.KeyErrorInHomework(message)
    verdict = HOMEWORK_VERDICT[homework_status]
    logging.info('Данные о домашней работе получены, формирование сообщения')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens() -> bool:
    """Проверяет наличие всех переменных окружения."""
    return all((
        PRACTICUM_TOKEN,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID
    ))


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        message = (
            'Отсутствуют обязательные переменные окружения: '
            'PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID.'
            'Программа принудительно остановлена!'
        )
        logging.critical(message)
        sys.exit(message)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    current_status = None
    prev_status = current_status
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homework = check_response(response)
            message = parse_status(homework[0])
            if current_status == prev_status:
                logging.info('По домашним работам нет обновлений')
            else:
                send_message(bot, message)
                current_timestamp = response['date_updated']
                prev_status = message
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.exception(message)
            send_message(bot, message)
        time.sleep(RETRY_TIME)


if __name__ == '__main__':
    logging.basicConfig(
        format=(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s; '
            'line: %(lineno)s'
        ),
        level=logging.INFO,
        handlers=[
            logging.FileHandler(os.path.join(BASE_DIR, 'info.log')),
            logging.StreamHandler(sys.stdout)
        ]
    )
    main()
