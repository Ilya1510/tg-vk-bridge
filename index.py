import json, os, requests, random, boto3
from botocore.config import Config

TG_TOKEN = os.environ['TG_TOKEN']
TG_CHAT_ID = os.environ['TG_CHAT_ID']
VK_TOKEN = os.environ['VK_TOKEN']
VK_PEER_ID = int(os.environ['VK_PEER_ID'])
VK_CONFIRM = os.environ['VK_CONFIRM']
TG_BOT_USERNAME = os.environ['TG_BOT_USERNAME']
S3_BUCKET = os.environ['S3_BUCKET']

VK_REACTIONS = {
    1: '❤️', 2: '🔥', 3: '😂', 4: '👍',
    5: '💩', 7: '😭', 8: '😡', 9: '👎', 10: '👌', 11: '😃',
    12: '🤔', 13: '🙏', 15: '😍', 19: '😮',
    16: '🎉', 18: '🤝', 26: '👏', 27: '😢', 30: '😱', 42: '🤮',
}

s3 = boto3.client(
    's3',
    endpoint_url='https://storage.yandexcloud.net',
    config=Config(signature_version='s3v4'),
)

def load_mapping():
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key='mapping.json')
        return json.loads(obj['Body'].read())
    except Exception:
        return {'tg_to_vk': {}, 'vk_to_tg': {}, 'processed_updates': []}

def save_mapping(mapping):
    for key in ['tg_to_vk', 'vk_to_tg']:
        if len(mapping[key]) > 100:
            items = list(mapping[key].items())[-100:]
            mapping[key] = dict(items)
    # храним только последние 200 update_id
    mapping['processed_updates'] = mapping.get('processed_updates', [])[-200:]
    s3.put_object(Bucket=S3_BUCKET, Key='mapping.json', Body=json.dumps(mapping))

def get_vk_name(user_id):
    try:
        r = requests.get('https://api.vk.com/method/users.get', params={
            'access_token': VK_TOKEN,
            'user_ids': user_id,
            'v': '5.199',
        }).json()
        user = r['response'][0]
        return f"{user['first_name']} {user['last_name']}"
    except Exception:
        return str(user_id)

def send_tg(text, photo_url=None, reply_to=None):
    payload = {'chat_id': TG_CHAT_ID}
    if reply_to:
        payload['reply_to_message_id'] = reply_to
    if photo_url:
        payload['caption'] = text
        r = requests.post(f'https://api.telegram.org/bot{TG_TOKEN}/sendPhoto',
                         json={**payload, 'photo': photo_url})
    else:
        payload['text'] = text
        r = requests.post(f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage', json=payload)
    try:
        return r.json()['result']['message_id']
    except Exception:
        return None

def upload_photo_to_vk(photo_url):
    try:
        server = requests.get('https://api.vk.com/method/photos.getMessagesUploadServer', params={
            'access_token': VK_TOKEN,
            'peer_id': VK_PEER_ID,
            'v': '5.199',
        }).json()['response']['upload_url']
        img_data = requests.get(photo_url).content
        uploaded = requests.post(server, files={'photo': ('photo.jpg', img_data, 'image/jpeg')}).json()
        saved = requests.post('https://api.vk.com/method/photos.saveMessagesPhoto', params={
            'access_token': VK_TOKEN,
            'photo': uploaded['photo'],
            'server': uploaded['server'],
            'hash': uploaded['hash'],
            'v': '5.199',
        }).json()['response'][0]
        return f"photo{saved['owner_id']}_{saved['id']}"
    except Exception as e:
        print("Photo upload error:", e)
        return None

def send_vk(text, attachment=None, reply_to=None):
    params = {
        'access_token': VK_TOKEN,
        'peer_id': VK_PEER_ID,
        'random_id': random.randint(0, 2**31),
        'v': '5.199',
    }
    if text:
        params['message'] = text
    if attachment:
        params['attachment'] = attachment
    if reply_to:
        params['forward'] = json.dumps({
            'peer_id': VK_PEER_ID,
            'conversation_message_ids': [int(reply_to)],
            'is_reply': True,
        })
    print("SEND_VK params:", {k: v for k, v in params.items() if k != 'access_token'})
    r = requests.post('https://api.vk.com/method/messages.send', params=params)
    print("SEND_VK response:", r.text)
    try:
        msg_id = r.json()['response']
        # получаем conversation_message_id по обычному id
        info = requests.get('https://api.vk.com/method/messages.getById', params={
            'access_token': VK_TOKEN,
            'message_ids': msg_id,
            'v': '5.199',
        }).json()
        cmid = info['response']['items'][0]['conversation_message_id']
        return cmid
    except Exception:
        return None

def handler(event, context):
    body_raw = event.get('body', '{}')
    print("BODY:", body_raw)
    if event.get('isBase64Encoded'):
        import base64
        body_raw = base64.b64decode(body_raw).decode('utf-8')
    try:
        body = json.loads(body_raw)
    except Exception:
        return {'statusCode': 400, 'body': 'bad json'}

    mapping = load_mapping()

    # защита от дублей Telegram
    update_id = body.get('update_id')
    if update_id:
        if update_id in mapping.get('processed_updates', []):
            print("DUPLICATE update_id:", update_id)
            return {'statusCode': 200, 'body': 'ok'}
        mapping.setdefault('processed_updates', []).append(update_id)

    # VK Callback API
    if 'type' in body:
        if body['type'] == 'confirmation':
            return {'statusCode': 200, 'body': VK_CONFIRM}

        if body['type'] == 'message_new':
            msg = body.get('object', {}).get('message', {})
            if msg.get('peer_id') == VK_PEER_ID:
                from_id = msg.get('from_id', 0)
                text = msg.get('text', '')
                attachments = msg.get('attachments', [])
                vk_msg_id = msg.get('conversation_message_id') or msg.get('cmid') or msg.get('id')
                reply_info = msg.get('reply_message')

                if from_id > 0:
                    name = get_vk_name(from_id)

                    tg_reply_to = None
                    if reply_info:
                        reply_cmid = str(reply_info.get('conversation_message_id') or reply_info.get('cmid') or reply_info.get('id', ''))
                        tg_reply_to = mapping['vk_to_tg'].get(reply_cmid)

                    tg_msg_id = None
                    for att in attachments:
                        if att.get('type') == 'photo':
                            sizes = att['photo']['sizes']
                            photo_url = sorted(sizes, key=lambda x: x['width'])[-1]['url']
                            tg_msg_id = send_tg(f'[VK] {name}:', photo_url=photo_url, reply_to=tg_reply_to)
                    if text:
                        tg_msg_id = send_tg(f'[VK] {name}: {text}', reply_to=tg_reply_to)

                    if tg_msg_id and vk_msg_id:
                        mapping['tg_to_vk'][str(tg_msg_id)] = str(vk_msg_id)
                        mapping['vk_to_tg'][str(vk_msg_id)] = tg_msg_id
                        save_mapping(mapping)

        if body['type'] == 'message_reaction_event':
            obj = body.get('object', {})
            from_id = obj.get('reacted_id', 0)
            reaction_id = obj.get('reaction_id', 0)
            cmid = str(obj.get('cmid') or obj.get('conversation_message_id', ''))
            emoji = VK_REACTIONS.get(reaction_id, f'реакция #{reaction_id}')
            if from_id > 0:
                name = get_vk_name(from_id)
                tg_reply_to = mapping['vk_to_tg'].get(cmid)
                send_tg(f'[VK] {name} поставил {emoji}', reply_to=tg_reply_to)

        return {'statusCode': 200, 'body': 'ok'}

    # Telegram реакции
    if 'message_reaction' in body:
        reaction = body['message_reaction']
        if str(reaction.get('chat', {}).get('id', '')) == TG_CHAT_ID:
            from_user = reaction.get('user', {}).get('first_name', 'Кто-то')
            new_reactions = reaction.get('new_reaction', [])
            tg_msg_id = str(reaction.get('message_id', ''))
            if new_reactions:
                emoji = new_reactions[0].get('emoji', '👍')
                vk_reply_to = mapping['tg_to_vk'].get(tg_msg_id)
                send_vk(f'[TG] {from_user} поставил {emoji}', reply_to=vk_reply_to)

    # Telegram сообщения
    if 'message' in body:
        msg = body['message']
        if str(msg.get('chat', {}).get('id', '')) != TG_CHAT_ID:
            return {'statusCode': 200, 'body': 'ok'}
        if msg.get('from', {}).get('is_bot'):
            return {'statusCode': 200, 'body': 'ok'}

        text = msg.get('text', '') or ''
        caption = msg.get('caption', '') or ''
        entities = msg.get('entities', []) or msg.get('caption_entities', [])
        from_user = msg.get('from', {}).get('first_name', 'Кто-то')
        last_name = msg.get('from', {}).get('last_name', '')
        full_name = f"{from_user} {last_name}".strip()
        photo = msg.get('photo')
        content = text or caption
        tg_msg_id = str(msg.get('message_id', ''))

        reply_info = msg.get('reply_to_message')
        vk_reply_to = None
        if reply_info:
            reply_tg_id = str(reply_info.get('message_id', ''))
            vk_reply_to = mapping['tg_to_vk'].get(reply_tg_id)
            print("TG REPLY:", reply_tg_id, "→ VK:", vk_reply_to)

        # убираем упоминание бота из текста если есть
        clean = content
        for ent in entities:
            if ent.get('type') == 'mention':
                mention = content[ent['offset']:ent['offset']+ent['length']]
                if mention.lstrip('@').lower() == TG_BOT_USERNAME.lower():
                    clean = content.replace(mention, '').strip()

        vk_msg_id = None
        if photo:
            file_id = photo[-1]['file_id']
            file_info = requests.get(
                f'https://api.telegram.org/bot{TG_TOKEN}/getFile',
                params={'file_id': file_id}
            ).json()['result']['file_path']
            photo_url = f'https://api.telegram.org/file/bot{TG_TOKEN}/{file_info}'
            attachment = upload_photo_to_vk(photo_url)
            vk_msg_id = send_vk(f'[TG] {full_name}: {clean}', attachment=attachment, reply_to=vk_reply_to)
        elif clean:
            vk_msg_id = send_vk(f'[TG] {full_name}: {clean}', reply_to=vk_reply_to)

        if vk_msg_id and tg_msg_id:
            mapping['tg_to_vk'][tg_msg_id] = str(vk_msg_id)
            mapping['vk_to_tg'][str(vk_msg_id)] = int(tg_msg_id)
            save_mapping(mapping)

    return {'statusCode': 200, 'body': 'ok'}
