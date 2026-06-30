"""
SQLite 数据库层 — 接口兼容 supabase-py，无缝切换

第一性原理：
    你的后端对数据库的操作只有四种：INSERT、SELECT、UPDATE、COUNT。
    SQLite 和 PostgreSQL 在这些操作上的 SQL 语法完全相同。
    唯一的区别是连接方式——SQLite 是本地文件，PostgreSQL 是网络端口。
    这一层封装了这个差异，main.py 不需要改一行代码。
"""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "jackmen.db")


class _QueryBuilder:
    """模拟 supabase-py 的链式调用接口"""
    
    def __init__(self, db: sqlite3.Connection, table: str, action: str):
        self._db = db
        self._table = table
        self._action = action          # "select", "insert", "update"
        self._columns = "*"
        self._filters = []
        self._order_by = None
        self._order_desc = False
        self._data = None
        self._limit = None
        self._count_exact = False
    
    def select(self, columns, count=None):
        self._columns = columns
        if count == "exact":
            self._count_exact = True
        return self
    
    def insert(self, data):
        self._action = "insert"
        self._data = data
        return self
    
    def update(self, data):
        self._action = "update"
        self._data = data
        return self
    
    def eq(self, column, value):
        self._filters.append((column, "=", value))
        return self
    
    def not_(self, column, value):
        self._filters.append((column, "!=", value))
        return self
    
    def order(self, column, desc=False):
        self._order_by = column
        self._order_desc = desc
        return self
    
    def range(self, start, end):
        self._limit = (start, end - start + 1)
        return self
    
    def limit(self, n):
        self._limit = (0, n)
        return self
    
    def execute(self):
        """执行查询并返回兼容 supabase-py 的结果对象"""
        if self._action == "insert":
            return self._execute_insert()
        elif self._action == "update":
            return self._execute_update()
        else:
            return self._execute_select()
    
    def _execute_insert(self):
        cols = ", ".join(self._data.keys())
        placeholders = ", ".join(["?" for _ in self._data])
        values = list(self._data.values())
        
        # Auto-add created_at if column exists
        sql = f"INSERT INTO {self._table} ({cols}) VALUES ({placeholders})"
        
        cur = self._db.execute(sql, values)
        self._db.commit()
        return _Result(data=[], count=0)
    
    def _execute_update(self):
        sets = ", ".join([f"{k} = ?" for k in self._data.keys()])
        values = list(self._data.values())
        
        where_sql, where_values = self._build_where()
        sql = f"UPDATE {self._table} SET {sets}{where_sql}"
        
        self._db.execute(sql, values + where_values)
        self._db.commit()
        return _Result(data=[], count=0)
    
    def _execute_select(self):
        if self._count_exact:
            sql = f"SELECT COUNT(*) as count FROM {self._table}"
        elif self._columns == "*":
            sql = f"SELECT * FROM {self._table}"
        else:
            sql = f"SELECT {self._columns} FROM {self._table}"
        
        where_sql, where_values = self._build_where()
        sql += where_sql
        
        if self._order_by:
            desc = " DESC" if self._order_desc else ""
            sql += f" ORDER BY {self._order_by}{desc}"
        
        if self._count_exact:
            cur = self._db.execute(sql, where_values)
            count = cur.fetchone()[0]
            return _Result(data=[], count=count)
        else:
            cur = self._db.execute(sql, where_values)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            
            data = []
            for row in rows:
                item = {}
                for i, col in enumerate(cols):
                    val = row[i]
                    # Parse JSONB fields (stored as TEXT in SQLite)
                    if col in ("answers", "tags"):
                        try:
                            val = json.loads(val) if isinstance(val, str) else val
                        except (json.JSONDecodeError, TypeError):
                            pass
                    item[col] = val
                data.append(item)
            
            return _Result(data=data, count=len(data))
    
    def _build_where(self):
        if not self._filters:
            return "", []
        
        conditions = []
        values = []
        for col, op, val in self._filters:
            conditions.append(f"{col} {op} ?")
            values.append(val)
        
        return " WHERE " + " AND ".join(conditions), values


class _Result:
    """模拟 supabase-py 的 execute() 返回对象"""
    def __init__(self, data: list, count: int):
        self.data = data
        self.count = count


class _TableProxy:
    """模拟 supabase.table() 返回对象"""
    def __init__(self, db: sqlite3.Connection, table: str):
        self._db = db
        self._table = table
    
    def select(self, columns="*", count=None):
        return _QueryBuilder(self._db, self._table, "select").select(columns, count=count)
    
    def insert(self, data):
        return _QueryBuilder(self._db, self._table, "insert").insert(data)
    
    def update(self, data):
        return _QueryBuilder(self._db, self._table, "update").update(data)


class Database:
    """主数据库对象 — 用法完全等价于 supabase.Client"""
    
    def __init__(self, path: str = DB_PATH):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
    
    def _init_schema(self):
        self._conn.executescript("""
            -- ==================== 匹配系统 ====================
            CREATE TABLE IF NOT EXISTS users (
                id          TEXT PRIMARY KEY,
                role        TEXT NOT NULL CHECK (role IN ('freshman', 'senior')),
                answers     TEXT NOT NULL,     -- JSON array
                contact     TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            
            CREATE TABLE IF NOT EXISTS notifications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL REFERENCES users(id),
                from_id     TEXT NOT NULL,
                from_contact TEXT,
                from_role   TEXT,
                message     TEXT NOT NULL,
                read        INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            
            CREATE INDEX IF NOT EXISTS idx_notif_user 
                ON notifications(user_id, read);
            
            CREATE TABLE IF NOT EXISTS connections (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL REFERENCES users(id),
                matched_id  TEXT NOT NULL REFERENCES users(id),
                status      TEXT NOT NULL CHECK (status IN ('connected', 'ignored')),
                created_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, matched_id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_conn_user 
                ON connections(user_id, status);

            -- ==================== 用户系统（刷题功能） ====================
            CREATE TABLE IF NOT EXISTS math_users (
                id            TEXT PRIMARY KEY,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nickname      TEXT NOT NULL DEFAULT '',
                membership    TEXT NOT NULL DEFAULT 'free' CHECK (membership IN ('free', 'basic', 'premium')),
                membership_expires_at TEXT,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            -- ==================== 题库 ====================
            CREATE TABLE IF NOT EXISTS problems (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL DEFAULT '',
                content     TEXT NOT NULL,
                subject     TEXT NOT NULL DEFAULT '',
                difficulty  INTEGER NOT NULL DEFAULT 1 CHECK (difficulty BETWEEN 1 AND 5),
                tags        TEXT DEFAULT '[]',
                solution    TEXT DEFAULT '',
                source      TEXT DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now'))
            );

            -- ==================== 做题记录 / 错题本 ====================
            CREATE TABLE IF NOT EXISTS user_problem_status (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL REFERENCES math_users(id) ON DELETE CASCADE,
                problem_id  INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
                status      TEXT NOT NULL DEFAULT 'unsolved' CHECK (status IN ('correct', 'wrong', 'unsolved')),
                wrong_reason TEXT DEFAULT '',
                marked      INTEGER DEFAULT 0,
                attempted_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, problem_id)
            );

            -- ==================== 论坛 ====================
            CREATE TABLE IF NOT EXISTS forum_categories (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name  TEXT NOT NULL UNIQUE,
                slug  TEXT NOT NULL UNIQUE,
                sort_order INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS forum_posts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL REFERENCES forum_categories(id) ON DELETE CASCADE,
                user_id    TEXT REFERENCES math_users(id) ON DELETE SET NULL,
                title      TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS forum_comments (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id   INTEGER NOT NULL REFERENCES forum_posts(id) ON DELETE CASCADE,
                user_id   TEXT REFERENCES math_users(id) ON DELETE SET NULL,
                content   TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- ==================== PDF 资料 ====================
            CREATE TABLE IF NOT EXISTS pdf_materials (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT DEFAULT '',
                file_url    TEXT NOT NULL,
                category    TEXT DEFAULT '',
                uploader_id TEXT REFERENCES math_users(id) ON DELETE SET NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            -- ==================== 种子数据：论坛板块 ====================
            INSERT OR IGNORE INTO forum_categories (name, slug, sort_order) VALUES
                ('数学分析', 'shu-xue-fen-xi', 1),
                ('高等代数', 'gao-deng-dai-shu', 2),
                ('常微分方程', 'chang-wei-fen-fang-cheng', 3),
                ('抽象代数', 'chou-xiang-dai-shu', 4),
                ('实变函数', 'shi-bian-han-shu', 5),
                ('复变函数', 'fu-bian-han-shu', 6),
                ('概率论与数理统计', 'gai-lv-lun', 7),
                ('泛函分析', 'fan-han-fen-xi', 8),
                ('初等数论', 'chu-deng-shu-lun', 9),
                ('微分几何', 'wei-fen-ji-he', 10),
                ('考研真题', 'kao-yan-zhen-ti', 11),
                ('综合交流', 'zong-he-jiao-liu', 12);
        """)
        self._conn.commit()
    
    def table(self, name: str) -> _TableProxy:
        return _TableProxy(self._conn, name)


# 全局单例 — 等价于 supabase = create_client(...)
db = Database()
