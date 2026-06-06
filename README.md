# Telegram ↔ VK Bridge

Мост между семейным чатом в Telegram и беседой в VK.

Telegram → VK работает через long polling на маленькой VM в Yandex Compute Cloud. VK → Telegram
остается на Yandex Cloud Functions через VK Callback API.

## Что умеет

- **Telegram → VK**: упомяни `@gridasov_family_bridge_bot текст` — сообщение придёт в VK беседу
- **VK → Telegram**: любое сообщение от человека в VK беседе приходит в Telegram чат
- Пересылка фотографий в обе стороны
- Reply (ответы на сообщения) в обе стороны
- Реакции в обе стороны
- Бот не пересылает сам себя (защита от бесконечного цикла)
- Имена отображаются нормально: `[VK] Илья Грибасов: текст`

## Архитектура

```
Telegram чат "Семья"
    ↓ Telegram getUpdates long polling
Yandex Compute VM: tg-vk-poller
    ↓ общий Python-код
    ↓
VK чат сообщества (Пумпурум)

VK чат сообщества
    ↓ любое сообщение/фото от человека
Yandex Cloud Function
    ↓
Telegram чат "Семья"
```

Маппинг сообщений (для reply и реакций) хранится в Yandex Object Storage — до 100 последних сообщений.

## Компоненты

| Компонент | Описание |
|---|---|
| Telegram бот | @gridasov_family_bridge_bot — updates забирает VM через `getUpdates` |
| VK сообщество | club237165074 — Callback API, бот добавлен в беседу |
| Yandex Compute VM | `tg-vk-poller` — systemd-сервис `tg-vk-poller.service`, быстрый Telegram → VK long polling |
| Yandex Cloud Function | `tg-vk-bridge` — обработка VK Callback API и общий handler для updates |
| Yandex Object Storage | бакет `tg-vk-bridge` — хранит mapping.json |

## Переменные окружения

Задаются в настройках Cloud Function и в `/opt/tg-vk-bridge/.env` на VM:

| Переменная | Описание |
|---|---|
| `TG_TOKEN` | Токен Telegram бота от @BotFather |
| `TG_CHAT_ID` | ID семейного Telegram чата |
| `VK_TOKEN` | Ключ доступа VK сообщества |
| `VK_PEER_ID` | peer_id VK беседы |
| `VK_CONFIRM` | Строка подтверждения Callback API VK |
| `TG_BOT_USERNAME` | Username бота без @ |
| `S3_BUCKET` | Имя бакета в Object Storage |
| `AWS_ACCESS_KEY_ID` | Ключ сервисного аккаунта Yandex |
| `AWS_SECRET_ACCESS_KEY` | Секрет сервисного аккаунта Yandex |

## Зависимости

```
requests
boto3
```

## Деплой

### Cloud Function

1. Скопировать `index.py` и `requirements.txt` в редактор Cloud Function.
2. Задать все переменные окружения.
3. Создать версию.
4. В настройках VK группы → Callback API → указать URL функции → подтвердить.
5. Включить события: **Входящее сообщение**, **Действие с реакциями на сообщение**.

### Telegram poller VM

1. Telegram webhook должен быть выключен:
```
https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=false
```
2. На VM положить `index.py`, `poller.py`, `requirements.txt` в `/opt/tg-vk-bridge`.
3. Создать `/opt/tg-vk-bridge/.env` с теми же переменными окружения.
4. Установить зависимости в virtualenv.
5. Запустить systemd-сервис:
```
sudo systemctl enable --now tg-vk-poller.service
```

Почему не webhook: Telegram регулярно получал `Connection timed out` при доставке webhook
в Yandex Cloud endpoint, из-за чего updates уходили в retry/backoff и могли задерживаться на минуты.
Long polling на always-on VM сам забирает updates у Telegram и убирает этот класс задержек.
