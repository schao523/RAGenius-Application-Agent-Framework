import sqlite3
from pathlib import Path


DB_PATH = Path(r"D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\rag_app.db")
SKILL_ID = "research_paper_finder"

conn = sqlite3.connect(str(DB_PATH))
try:
    before = conn.execute("select count(*) from skills where id = ?", (SKILL_ID,)).fetchone()[0]
    conn.execute("delete from skills where id = ?", (SKILL_ID,))
    conn.commit()
    after = conn.execute("select count(*) from skills where id = ?", (SKILL_ID,)).fetchone()[0]
    print({"before": before, "after": after})
finally:
    conn.close()
