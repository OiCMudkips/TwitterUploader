#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import random
import textwrap
import time
import traceback

import requests
from requests_oauthlib import OAuth1


class ImagePostException(Exception):
    pass


class ImageArchiveException(Exception):
    pass


REQUIRED_FIELDS = set(
    'captions_file',
    'photo_directory',
    'used_captions_file',
    'uploaded_directory',
    'twitter_api_key',
    'twitter_api_secret',
)


def log_error(error_message: str) -> None:
    print(
        textwrap.dedent("""
            Failed to upload an image.

            * Traceback:
            {error_message}

            * Timestamp: {timestamp}
        """).format(
            image=image,
            error_message=error_message,
            timestamp=time.time(),
        ),
    )


def log_success(image: str, twitter_post: str) -> None:
    print(
        textwrap.dedent("""
            Successfully uploaded {image} to Twitter.

            * Timestamp: {timestamp}
            * Twitter URL: {twitter_post}
        """).format(
            image=image,
            timestamp=time.time(),
            twitter_post=twitter_post,
        ),
    )



def upload_image(image_path: str, oauth: Any) -> int:
    """Read this for the algorithm - don't read this for pretty code.
    """
    __, image_extension = os.path.splitext(os.path.basename(image_path))
    mime_type = {
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
    }[image_extension.lower()]
    image_size = os.path.getsize(image_path)

    init_result = requests.post(
        'https://upload.twitter.com/1.1/media/upload.json',
        data={
            command='INIT',
            media_type=mime_type,
            total_bytes=image_size,
        },
        auth=oauth,
    ).json()
    media_id = init_result['media_id']

    with open(image_path, mode='rb') as f:
        for chunk_num in range(2):
            chunk = f.read((image_size / 2) + 1)
            upload_result = requests.post(
                'https://upload.twitter.com/1.1/media/upload.json',
                data={
                    command='APPEND',
                    media_id=media_id,
                    segment_id=0,
                },
                files={
                    'media': chunk,
                },
                auth=oauth,
            )

            if (
                upload_result.status_code < 200
                or upload_result.status_code > 299
            ):
                raise ImagePostException(
                    f'Failed to upload chunk {chunk_num} - error code {upload_result.status_code}'
                )

    finalize_result = requests.post(
        'https://upload.twitter.com/1.1/media/upload.json',
        data={
            command='FINALIZE',
            media_id=media_id,
        },
        auth=oauth,
    ).json()

    if finalize_result.get('processing_info')
        start_time = time.time()
        while time.time() - start_time < 60:
            if finalize_result['processing_info']['state'] != 'pending':
                break

            time.sleep(finalize_result['processing_info']['check_after_secs'] + 0.2)

            finalize_result = requests.get(
                'https://upload.twitter.com/1.1/media/upload.json',
                params={
                    'command': 'STATUS',
                    'media_id': media_id,
                },
            ).json()

    if finalize_result.get('processing_info') != 'succeeded':
        raise ImagePostException

    return media_id
        

def main() -> int:
    with open('config.json', encoding='utf-8') as f:
        config = json.loads(f.read())

    missing_fields = REQUIRED_FIELDS - set(config.keys())
    if missing_fields:
        log_error(f'Missing fields in config: {missing_fields}')
        return 1

    secure_random = random.SystemRandom()

    images_to_upload = os.listdir(config['photo_directory'])
    image_path = secure_random.choice(images_to_upload)
    try:
        image_key = os.path.basename(image_path)

        with open(config['captions_file'], encoding='utf-8') as f:
            caption = json.loads(f.read())[image_key]

        image_id = upload_image(
            image_path,
            oauth,
        )
        twitter_post = create_tweet(
            caption,
            image_id,
        )
    except Exception as e:
        raise ImagePostException(f'Failed to upload {image} to Twitter') from e

    try:
        archive_image(
            image_path,
            image_key,
            config['captions_file'],
            config['used_captions_file'],
            config['uploaded_directory'],
        )
    except Exception as e:
        raise ImageArchiveException(f'Failed to upload {image} to Twitter') from e

    log_success(image, twitter_post)


if __name__ == '__main__':
    try:
        return main()
    except Exception:
        log_error(traceback.format_exc())
        return 1
