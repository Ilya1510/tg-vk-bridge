import json
import time

import requests

import index


ALLOWED_UPDATES = ['message', 'message_reaction']
POLL_TIMEOUT = 25
ERROR_SLEEP = 5


def get_offset():
    mapping = index.load_mapping()
    return mapping.get('telegram_offset')


def save_offset(update_id):
    mapping = index.load_mapping()
    mapping['telegram_offset'] = update_id + 1
    index.save_mapping(mapping)


def process_update(update):
    response = index.handler({'body': json.dumps(update)}, None)
    print("processed update", update.get('update_id'), response, flush=True)


def poll_once():
    params = {
        'timeout': POLL_TIMEOUT,
        'limit': 20,
        'allowed_updates': json.dumps(ALLOWED_UPDATES),
    }
    offset = get_offset()
    if offset:
        params['offset'] = offset

    response = requests.get(
        f'https://api.telegram.org/bot{index.TG_TOKEN}/getUpdates',
        params=params,
        timeout=(10, POLL_TIMEOUT + 10),
    )
    response.raise_for_status()
    updates = response.json().get('result', [])

    if updates:
        print("got updates", len(updates), flush=True)

    for update in updates:
        update_id = update.get('update_id')
        if update_id is None:
            continue
        process_update(update)
        save_offset(update_id)


def main():
    print("tg-vk poller started", flush=True)
    while True:
        try:
            poll_once()
        except Exception as e:
            print("poller error", repr(e), flush=True)
            time.sleep(ERROR_SLEEP)


if __name__ == '__main__':
    main()
