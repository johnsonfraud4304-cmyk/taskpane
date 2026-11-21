import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "tasks.db"


def migrate():
    """数据库迁移：加 synced_to_reminders 字段"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 检查字段是否存在
    c.execute("PRAGMA table_info(tasks)")
    cols = [row[1] for row in c.fetchall()]
    if "synced_to_reminders" not in cols:
        c.execute("ALTER TABLE tasks ADD COLUMN synced_to_reminders INTEGER DEFAULT 0")
        print("✅ 添加字段 synced_to_reminders")
    else:
        print("✓ 字段 synced_to_reminders 已存在")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()
