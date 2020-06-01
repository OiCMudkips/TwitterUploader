import os
import sqlite3
import sys

def main():
    db_file = sys.argv[1]
    photos_directory = sys.argv[2]

    db_conn = sqlite3.connect(db_file)
    db_cursor = db_conn.cursor()

    for file_path in os.listdir(photos_directory):
        real_path = os.path.join(photos_directory, file_path)
        db_cursor.execute('INSERT INTO image (path) VALUES (?)', (file_path,))

    db_conn.commit()
    db_conn.close()    

if __name__ == '__main__':
    main()