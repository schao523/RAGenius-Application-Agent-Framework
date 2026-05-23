import sqlite3
conn = sqlite3.connect(r"ragenius_app_skeleton/runtime_state.db")
cur = conn.cursor()
print(cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall())
