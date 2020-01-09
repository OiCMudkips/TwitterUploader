#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import random
import textwrap
import time
import traceback


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

        twitter_post = upload_image(
            image_path,
            caption,
            config['twitter_api_key'],
            config['twitter_api_secret'],
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
