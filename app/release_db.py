import sqlite3

DB_PATH = '/var/lib/app/releases.db'

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS seen_releases (
                repo TEXT PRIMARY KEY,
                release_date TEXT
            )
        ''')

def get_seen_releases():
    with sqlite3.connect(DB_PATH) as conn:
        return dict(conn.execute('SELECT repo, release_date FROM seen_releases'))

def save_seen_release(repo, release_date):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            INSERT INTO seen_releases (repo, release_date)
            VALUES (?, ?)
            ON CONFLICT(repo) DO UPDATE SET release_date=excluded.release_date
        ''', (repo, release_date))
