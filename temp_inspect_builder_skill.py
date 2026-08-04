import sqlite3
from pathlib import Path


DBS = [
    Path(r"D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\rag_app.db"),
    Path(r"D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\live_builder.db"),
    Path(r"D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\live_builder_real.db"),
]

SQL = """
select
  s.id as skill_row_id,
  s.slug,
  s.name,
  v.id as version_row_id,
  v.version,
  v.state,
  v.storage_root_rel_path
from skills s
left join skill_versions v on v.skill_id = s.id
where s.slug in ('research-paper-finder', 'research_paper_finder')
   or s.name in ('research-paper-finder', 'research_paper_finder')
order by v.created_at
"""

for path in DBS:
    print("DB", path)
    if not path.exists():
        print("  missing")
        continue
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(SQL).fetchall()
        print("  rows", len(rows))
        for row in rows:
            print(" ", dict(row))
    finally:
        conn.close()
