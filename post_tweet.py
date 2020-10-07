#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Downloads a file from S3 and uploads it to Twitter.
Reads caption data and sets an image as uploaded in an SQLite database,
which itself is saved on S3.

I would make this a Lambda but there's literally no way to setup a crontab
without also using yet another service, and I want to limit my exposure to AWS
services so I guess this will remain a cron task on my website's hosting.
"""
import functools
import json
import os
import posixpath
import random
import sqlite3
import sys
import tempfile
import time
import traceback
import typing

import boto3
import requests
from requests_oauthlib import OAuth1


class ImagePostException(Exception):
    pass


REQUIRED_FIELDS = set([
    'db_bucket',
    'db_path',
    'twitter_api_key',
    'twitter_api_secret',
    'twitter_access_token',
    'twitter_access_secret',
])


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


@functools.lru_cache(maxsize=1)
def get_s3_client():
    return boto3.Session(profile_name='s3').client('s3')


def get_s3_file(bucket_name: str, bucket_path: str, output_file: typing.BinaryIO) -> typing.BinaryIO:
    client = get_s3_client()
    client.download_fileobj(Bucket=bucket_name, Key=bucket_path, Fileobj=output_file)
    return output_file


def upload_s3_file(bucket_name: str, bucket_path: str, upload_file: typing.BinaryIO):
    upload_file.seek(0)

    client = get_s3_client()
    client.upload_fileobj(Fileobj=upload_file, Bucket=bucket_name, Key=bucket_path)


def upload_image_to_twitter(image_name: str, image_path: str, image_file: typing.BinaryIO, oauth: OAuth1):
    __, image_extension = posixpath.splitext(image_name)
    mime_type = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
    }[image_extension.lower()]
    image_size = os.path.getsize(image_path)

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

    chunk_num = 0
    while image_file.tell() < image_size:
        current_chunk = image_file.read(3*1024*1024)
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
    config_file = sys.argv[1]
    with open(config_file, encoding='utf-8') as f:
        config = json.loads(f.read())

    missing_fields = REQUIRED_FIELDS - set(config.keys())
    if missing_fields:
        raise ImagePostException(f'Missing fields in config: {missing_fields}')

    db_file = get_s3_file(config["db_bucket"], config["db_path"], tempfile.NamedTemporaryFile(delete=False))
    db_file_name = db_file.name
    db_file.close() # Windows cannot open the same file twice, so we have to close this open file before opening it again in sqlite3.

    db_conn = sqlite3.connect(db_file_name)
    db_cursor = db_conn.cursor()

    images_to_upload = db_cursor.execute('SELECT id, bucket_name, bucket_path, caption from image2 WHERE uploaded = 0').fetchall()
    img_id, img_bucket_name, img_bucket_path, caption = random.SystemRandom().choice(images_to_upload)

    if len(caption) > 280:
        raise ImagePostException(f"{img_id}'s caption is too long.")

    oauth = OAuth1(
        config['twitter_api_key'],
        config['twitter_api_secret'],
        config['twitter_access_token'],
        config['twitter_access_secret'],
    )

    try:
        image_name = posixpath.basename(img_bucket_path)
        image_file = get_s3_file(
            img_bucket_name, img_bucket_path, tempfile.NamedTemporaryFile(),
        )
        image_file.seek(0)
        image_path = image_file.name

        twitter_image_id = upload_image_to_twitter(image_name, image_path, image_file, oauth)
        twitter_post = post_tweet(caption, twitter_image_id, oauth)

        image_file.close()
    except Exception as e:
        raise ImagePostException(f'Failed to upload {img_id} to Twitter') from e

    try:
        db_cursor.execute('UPDATE image2 SET uploaded = 1 WHERE id = ?', (img_id,))
        db_conn.commit()
        db_conn.close()
        with open(db_file_name, 'rb') as db_file:
            upload_s3_file(config["db_bucket"], config["db_path"], db_file)
    except Exception as e:
        raise ImagePostException(f'Failed to upload {img_id} to Twitter') from e

    log_success(img_id, twitter_post)
    os.remove(db_file_name)

    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        log_error(traceback.format_exc())
        sys.exit(1)
