import os
import requests
import logging
import sys
import time
import telegram
import telegram.ext

from telegram import TelegramError

from http import HTTPStatus

from datetime import datetime

from typing import Dict, List, Union

from dotenv import load_dotenv

load_dotenv()


PRACTICUM_TOKEN = os.getenv('TOKEN_PRACTICUM')
TELEGRAM_TOKEN = os.getenv('TOKEN_TELEGRAM')
TELEGRAM_CHAT_ID = 318810817


RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        logging.info('Отправляем сообщение в телеграм: %s', message)
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except Exception as error:
        message = f'Ошибка отправки сообщения в телеграм: {error}'
        raise TelegramError(message)
    else:
        logging.info('Сообщение в телеграм успешно отправлено')


def get_api_answer(
        current_timestamp
) -> Dict[str, Union[int, List[Dict[str, Union[int, str, datetime]]]]]:
    """Делает запрос к API Яндекс.Практикума и возвращает ответ."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    homeworks_list = requests.get(
        ENDPOINT, headers=HEADERS, params=params)
    if homeworks_list.status_code != HTTPStatus.OK:
        message = (
            'Неверный ответ сервера: '
            f'http code = {homeworks_list.status_code}; '
            f'reason = {homeworks_list.reason}; '
            f'content = {homeworks_list.text}'
        )
        raise ConnectionError(message)
    homeworks_list = homeworks_list.json()
    if len(homeworks_list) == 0:
        logging.info('За последнее время нет домашних работ')
    return homeworks_list


def check_response(
    response: Dict[str, Union[int, List[Dict[str, Union[int, str, datetime]]]]]
) -> List[Dict[str, Union[int, str, datetime]]]:
    """Проверяет ответ API на корректность."""
    logging.info('Проверка ответа от API начата.')
    if not isinstance(response, dict):
        message = f'Ответ от API не является списком: response = {response}'
        raise TypeError(message)
    logging.info('Корректный ответ API')
    return response.get('homeworks')[0]


def parse_status(homework):
    """Извлечение информации о статусе домашней работы."""
    logging.info('Получение данных из домашей работы')
    try:
        homework_name = homework['homework_name']
    except Exception as error:
        message = f'Ошибка ключа домашней работы: {error}'
        raise KeyError(message)
    homework_status = homework['status']
    verdict = HOMEWORK_STATUSES[homework_status]
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
            logging.info(
                'Запрашиваем список домаших работ по временной метке %s',
                current_timestamp)
        except Exception as error:
            message = f'Ошибка подключения к Практикуму: {error}'
            logging.error(message)
            send_message(bot, message)
        try:
            homework = check_response(response)
            message = parse_status(homework)
            current_status = homework['status']
            if current_status == prev_status:
                logging.info('По домашним работам нет обновлений')
                break
            send_message(bot, message)
            current_timestamp = response['date_updated']
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.exception(message)
            send_message(bot, message)
        time.sleep(RETRY_TIME)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        level=logging.INFO)
    main()
