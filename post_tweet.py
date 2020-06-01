#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import random
import sqlite3
import time
import traceback

import requests
from requests_oauthlib import OAuth1


class ImagePostException(Exception):
    pass


REQUIRED_FIELDS = set(
    'db_file',
    'twitter_api_key',
    'twitter_api_secret',
    'twitter_access_token',
    'twitter_access_secret',
)


def log_error(error_message: str) -> None:
    print(
        'Failed to upload an image. Timestamp: {timestamp}. Traceback: {error_message}'.format(
            timestamp=time.time(),
            error_message=error_message,
        ),
    )


def log_success(image_id: int, twitter_post: str) -> None:
    print(
        'Successfully uploaded {image_id} to Twitter. Timestamp: {timestamp}. URL: {twitter_post}'.format(
            image_id=image_id,
            timestamp=time.time(),
            twitter_post=twitter_post,
        ),
    )


def upload_image(path: str, oauth: OAuth1):
    __, image_extension = os.path.splitext(os.path.basename(path))
    mime_type = {
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
    }[image_extension.lower()]
    image_size = os.path.getsize(path)

    init_params = {
        'command': 'INIT',
        'total_bytes': image_size,
        'media_type': mime_type,
        'media_category': 'tweet_image',
    }
    result = requests.post(
        'https://upload.twitter.com/1.1/media/upload.json',
        data=init_params,
        auth=oauth,
    )
    result.raise_for_status()
    media_id = result.json()['media_id']

    with open(path, mode='rb') as f:
        chunk_num = 0
        while f.tell() < image_size:
            current_chunk = f.read(3*1024*1024)
            append_params = {
                'command': 'APPEND',
                'media_id': media_id,
                'segment_index': chunk_num,
            }
            append_files = {'media': current_chunk}
            result = requests.post(
                'https://upload.twitter.com/1.1/media/upload.json',
                data=append_params,
                files=append_files,
                auth=oauth,
            )

            result.raise_for_status()
            chunk_num = chunk_num + 1

    finalize_params = {
        'command': 'FINALIZE',
        'media_id': media_id,
    }
    result = requests.post(
        'https://upload.twitter.com/1.1/media/upload.json',
        data=finalize_params,
        auth=oauth,
    )
    result.raise_for_status()

    # according to Twitter docs the processing_info field is only applicable for videos
    return media_id


def post_tweet(caption: str, image_id: str, oauth: OAuth1):
    params = {
        'status': caption,
        'media_ids': image_id,
        'display_coordinates': 'false',
    }
    response = requests.post(
        'https://api.twitter.com/1.1/statuses/update.json',
        data=params,
        auth=oauth,
    ).json()

    url = f"https://twitter.com/i/web/status/{response['id']}"
    return url


def main() -> int:
    with open('config.json', encoding='utf-8') as f:
        config = json.loads(f.read())

    missing_fields = REQUIRED_FIELDS - set(config.keys())
    if missing_fields:
        log_error(f'Missing fields in config: {missing_fields}')
        return 1

    secure_random = random.SystemRandom()
    db_conn = sqlite3.connect(config['db_file'])
    db_cursor = db_conn.cursor()

    images_to_upload = db_cursor.execute('SELECT id, path, caption from image WHERE uploaded = 0')
    img_id, path, caption = secure_random.choice(images_to_upload)

    if os.path.getsize(path) > 5 * 1024 * 1024:
        raise ImagePostException(f'{img_id} is too big. Size: {os.path.getsize(path)}')

    if len(caption) > 280:
        raise ImagePostException(f"{img_id}'s caption is too long.")

    oauth = OAuth1(
        config['twitter_api_key'],
        client_secret=config['twitter_api_secret'],
        resource_owner_key=config['twitter_access_token'],
        resource_owner_secret=config['twitter_access_secret'],
    )

    try:
        image_id = upload_image(path, oauth)
        twitter_post = post_tweet(caption, image_id, oauth)
    except Exception as e:
        raise ImagePostException(f'Failed to upload {img_id} to Twitter') from e

    try:
        db_cursor.execute('UPDATE image SET uploaded = 1 WHERE id = ?', (img_id,))
        db_conn.commit()
        db_conn.close()
    except Exception as e:
        raise ImagePostException(f'Failed to upload {img_id} to Twitter') from e

    log_success(image, twitter_post)


if __name__ == '__main__':
    try:
        return main()
    except Exception:
        log_error(traceback.format_exc())
        return 1
