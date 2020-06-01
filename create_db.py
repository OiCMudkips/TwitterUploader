import sqlite3
import sys

def main():
    db_file = sys.argv[1]

    db_cursor = sqlite3.connect(db_file).cursor()
    db_cursor.execute('CREATE TABLE image (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, caption TEXT, uploaded INTEGER DEFAULT 0);')

if __name__ == '__main__':
    main()