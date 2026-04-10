# Telegram ↔ VK Bridge

Мост между семейным чатом в Telegram и беседой в VK. Работает через Yandex Cloud Functions (бессерверно).

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
    ↓ @gridasov_family_bridge_bot текст/фото
Yandex Cloud Function
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
| Telegram бот | @gridasov_family_bridge_bot — принимает webhook от Telegram |
| VK сообщество | club237165074 — Callback API, бот добавлен в беседу |
| Yandex Cloud Function | `tg-vk-bridge` — основная логика пересылки |
| Yandex Object Storage | бакет `tg-vk-bridge` — хранит mapping.json |

## Переменные окружения

Задаются в настройках Cloud Function:

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

1. Скопировать `index.py` и `requirements.txt` в редактор Cloud Function
2. Задать все переменные окружения
3. Создать версию
4. Установить Telegram webhook:
```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=<URL_ФУНКЦИИ>&allowed_updates=["message","message_reaction"]
```
5. В настройках VK группы → Callback API → указать URL функции → подтвердить
6. Включить события: **Входящее сообщение**, **Действие с реакциями на сообщение**
