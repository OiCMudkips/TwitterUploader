"""Populates the DB with image paths on S3.
Depends on a AWS credentials file with a profile called "s3.
"""
import boto3
import os
import sqlite3
import sys

def main():
    db_file, bucket_name, bucket_path = sys.argv[1:]

    db_conn = sqlite3.connect(db_file)
    db_cursor = db_conn.cursor()

    s3_client = boto3.Session(profile_name='s3').client('s3')

    for resource in s3_client.list_objects(Bucket=bucket_name, Prefix=bucket_path)['Contents']:
        bucket_path = resource['Key']
        if bucket_path.endswith('/'):
            continue
        db_cursor.execute('INSERT INTO image2 (bucket_name, bucket_path) VALUES (?,?)', (bucket_name, bucket_path))

    db_conn.commit()
    db_conn.close()

if __name__ == '__main__':
    main()