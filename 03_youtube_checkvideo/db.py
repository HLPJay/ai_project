"""
db.py - 数据库操作
订阅表 + 已处理视频表，复用现有 reports.db
"""

import sqlite3
import datetime

DB_PATH = r"D:\claude_code\20260411_youtube_视频分析\reports.db"


def init_db():
    """建表（已存在则跳过）"""
    conn = sqlite3.connect(DB_PATH)

    # 订阅表：用户 ↔ 频道
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            channel_id   TEXT NOT NULL,
            channel_name TEXT,
            channel_url  TEXT,
            created_at   TEXT,
            UNIQUE(user_id, channel_id)
        )
    """)

    # 已处理视频表：防止重复推送
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_videos (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id     TEXT NOT NULL UNIQUE,
            channel_id   TEXT NOT NULL,
            title        TEXT,
            processed_at TEXT
        )
    """)

    conn.commit()
    conn.close()


# ── 订阅操作 ──

def add_subscription(user_id: int, channel_id: str,
                     channel_name: str, channel_url: str) -> bool:
    """添加订阅，返回 True=新增 False=已存在"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO subscriptions
            (user_id, channel_id, channel_name, channel_url, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, channel_id, channel_name, channel_url,
              datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def remove_subscription(user_id: int, channel_id: str) -> bool:
    """取消订阅，返回 True=成功 False=不存在"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "DELETE FROM subscriptions WHERE user_id=? AND channel_id=?",
        (user_id, channel_id)
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def get_user_subscriptions(user_id: int) -> list:
    """获取用户的所有订阅"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT channel_id, channel_name, channel_url, created_at
        FROM subscriptions WHERE user_id=?
        ORDER BY created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return [
        {'channel_id': r[0], 'channel_name': r[1],
         'channel_url': r[2], 'created_at': r[3]}
        for r in rows
    ]


def get_all_channels() -> list:
    """获取所有被订阅的唯一频道列表"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT DISTINCT channel_id, channel_name, channel_url
        FROM subscriptions
    """).fetchall()
    conn.close()
    return [
        {'channel_id': r[0], 'channel_name': r[1], 'channel_url': r[2]}
        for r in rows
    ]


def get_channel_subscribers(channel_id: str) -> list:
    """获取订阅了某个频道的所有用户 ID"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT user_id FROM subscriptions WHERE channel_id=?",
        (channel_id,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


# ── 已处理视频 ──

def is_video_processed(video_id: str) -> bool:
    """视频是否已经处理过"""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id FROM processed_videos WHERE video_id=?", (video_id,)
    ).fetchone()
    conn.close()
    return row is not None


def mark_video_processed(video_id: str, channel_id: str, title: str):
    """标记视频已处理"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO processed_videos (video_id, channel_id, title, processed_at)
            VALUES (?, ?, ?, ?)
        """, (video_id, channel_id, title,
              datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()
