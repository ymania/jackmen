"""
数据库层 — SQLite(本地) / PostgreSQL(生产) 自适应

本地: 零配置，SQLite 文件
生产: DATABASE_URL 环境变量 → PostgreSQL
"""
import sqlite3, json, os

DB_PATH = os.path.join(os.path.dirname(__file__), "jackmen.db")
DATABASE_URL = os.getenv("DATABASE_URL")
_IS_PG = bool(DATABASE_URL)

# ══════════════════════ 通用结果对象 ══════════════════════
class _Result:
    def __init__(self, data: list, count: int):
        self.data = data; self.count = count

# ══════════════════════ PostgreSQL ══════════════════════
if _IS_PG:
    import psycopg2
    import psycopg2.extras

    _pg_conn = None

    def _pg_get_conn():
        global _pg_conn
        if _pg_conn is None or _pg_conn.closed:
            url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
            _pg_conn = psycopg2.connect(url)
            _pg_conn.autocommit = True
            _pg_init_schema(_pg_conn)
        return _pg_conn

    def _pg_init_schema(conn):
        cur = conn.cursor()
        stmts = [
            "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, role TEXT NOT NULL, answers JSONB NOT NULL, contact TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW())",
            "CREATE TABLE IF NOT EXISTS notifications (id SERIAL PRIMARY KEY, user_id TEXT NOT NULL, from_id TEXT NOT NULL, from_contact TEXT, from_role TEXT, message TEXT NOT NULL, read BOOLEAN DEFAULT FALSE, created_at TIMESTAMPTZ DEFAULT NOW())",
            "CREATE INDEX IF NOT EXISTS idx_nf ON notifications(user_id, read)",
            "CREATE TABLE IF NOT EXISTS connections (id SERIAL PRIMARY KEY, user_id TEXT NOT NULL, matched_id TEXT NOT NULL, status TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE(user_id, matched_id))",
            "CREATE TABLE IF NOT EXISTS math_users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, nickname TEXT DEFAULT '', membership TEXT DEFAULT 'free', membership_expires_at TIMESTAMPTZ, created_at TIMESTAMPTZ DEFAULT NOW())",
            "CREATE TABLE IF NOT EXISTS problems (id SERIAL PRIMARY KEY, title TEXT DEFAULT '', content TEXT NOT NULL, subject TEXT DEFAULT '', difficulty INT DEFAULT 1, tags JSONB DEFAULT '[]', solution TEXT DEFAULT '', source TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW())",
            "CREATE TABLE IF NOT EXISTS user_problem_status (id SERIAL PRIMARY KEY, user_id TEXT NOT NULL, problem_id INT NOT NULL, status TEXT DEFAULT 'unsolved', wrong_reason TEXT DEFAULT '', marked BOOLEAN DEFAULT FALSE, attempted_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE(user_id, problem_id))",
            "CREATE TABLE IF NOT EXISTS forum_categories (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, slug TEXT UNIQUE NOT NULL, sort_order INT DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS forum_posts (id SERIAL PRIMARY KEY, category_id INT NOT NULL, user_id TEXT, title TEXT NOT NULL, content TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW())",
            "CREATE TABLE IF NOT EXISTS forum_comments (id SERIAL PRIMARY KEY, post_id INT NOT NULL, user_id TEXT, content TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW())",
            "CREATE TABLE IF NOT EXISTS pdf_materials (id SERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT DEFAULT '', file_url TEXT NOT NULL, category TEXT DEFAULT '', uploader_id TEXT, created_at TIMESTAMPTZ DEFAULT NOW())",
        ]
        for s in stmts:
            cur.execute(s)
        cur.execute(
            "INSERT INTO forum_categories (name, slug, sort_order) VALUES "
            "('数学分析','sfx',1),('高等代数','gda',2),('常微分方程','cwe',3),('抽象代数','cxd',4),('实变函数','sbf',5),('复变函数','fbf',6),('概率与统计','glt',7),('泛函分析','fhf',8),('初等数论','cds',9),('微分几何','wfj',10),('考研真题','kyz',11),('综合交流','zhj',12) "
            "ON CONFLICT (slug) DO NOTHING"
        )

    def _pg_execute(sql, params):
        conn = _pg_get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        upper = sql.strip().upper()
        if upper.startswith("SELECT"):
            rows = cur.fetchall()
            data = []
            for row in rows:
                item = dict(row)
                for k in list(item.keys()):
                    v = item[k]
                    if isinstance(v, str) and (v.startswith("[") or v.startswith("{")):
                        try: item[k] = json.loads(v)
                        except: pass
                data.append(item)
            return _Result(data=data, count=len(data))
        elif "RETURNING" in upper:
            row = cur.fetchone()
            return _Result(data=[dict(row)] if row else [], count=1)
        else:
            return _Result(data=[], count=cur.rowcount)

# ══════════════════════ SQLite ══════════════════════
class _QueryBuilder:
    def __init__(self, db, table, action):
        self._db = db; self._table = table; self._action = action
        self._columns = "*"; self._filters = []; self._order_by = None
        self._order_desc = False; self._data = None; self._count_exact = False

    def select(self, columns, count=None):
        self._columns = columns
        if count == "exact": self._count_exact = True
        return self

    def insert(self, data): self._action = "insert"; self._data = data; return self
    def update(self, data): self._action = "update"; self._data = data; return self
    def eq(self, col, val): self._filters.append((col, "=", val)); return self
    def order(self, col, desc=False): self._order_by = col; self._order_desc = desc; return self

    def execute(self):
        if _IS_PG: return self._pg()
        else: return self._sqlite()

    def _pg(self):
        ph = "%s"
        if self._action == "insert":
            return _pg_execute(
                f"INSERT INTO {self._table} ({','.join(self._data.keys())}) VALUES ({','.join([ph]*len(self._data))})",
                list(self._data.values()))
        elif self._action == "update":
            sets = ", ".join([f"{k}={ph}" for k in self._data])
            w, wp = self._where(ph)
            return _pg_execute(f"UPDATE {self._table} SET {sets}{w}", list(self._data.values()) + wp)
        else:
            col = "COUNT(*) AS count" if self._count_exact else self._columns
            w, wp = self._where(ph)
            sql = f"SELECT {col} FROM {self._table}{w}"
            if self._order_by: sql += f" ORDER BY {self._order_by}" + (" DESC" if self._order_desc else "")
            r = _pg_execute(sql, wp)
            if self._count_exact: r.count = r.data[0]["count"] if r.data else 0
            return r

    def _sqlite(self):
        if self._action == "insert":
            self._db._conn.execute(
                f"INSERT INTO {self._table} ({','.join(self._data.keys())}) VALUES ({','.join(['?']*len(self._data))})",
                list(self._data.values())); self._db._conn.commit(); return _Result([], 0)
        elif self._action == "update":
            sets = ", ".join([f"{k}=?" for k in self._data])
            w, wp = self._where("?")
            self._db._conn.execute(f"UPDATE {self._table} SET {sets}{w}", list(self._data.values())+wp)
            self._db._conn.commit(); return _Result([], 0)
        else:
            col = "COUNT(*) AS count" if self._count_exact else self._columns
            w, wp = self._where("?")
            sql = f"SELECT {col} FROM {self._table}{w}"
            if self._order_by: sql += f" ORDER BY {self._order_by}" + (" DESC" if self._order_desc else "")
            cur = self._db._conn.execute(sql, wp)
            if self._count_exact: return _Result([], cur.fetchone()[0])
            rows = cur.fetchall(); cols = [d[0] for d in cur.description]
            data = []
            for row in rows:
                item = {}
                for i, c in enumerate(cols):
                    v = row[i]
                    if c in ("answers","tags") and isinstance(v, str):
                        try: v = json.loads(v)
                        except: pass
                    item[c] = v
                data.append(item)
            return _Result(data, len(data))

    def _where(self, ph):
        if not self._filters: return "", []
        cs = []; ps = []
        for c, o, v in self._filters: cs.append(f"{c} {o} {ph}"); ps.append(v)
        return " WHERE " + " AND ".join(cs), ps


class _TableProxy:
    def __init__(self, db, table): self._db = db; self._table = table
    def select(self, c="*", count=None): return _QueryBuilder(self._db, self._table, "select").select(c, count=count)
    def insert(self, d): return _QueryBuilder(self._db, self._table, "insert").insert(d)
    def update(self, d): return _QueryBuilder(self._db, self._table, "update").update(d)


class _SQLiteDB:
    def __init__(self, path=DB_PATH):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, role TEXT CHECK(role IN('freshman','senior')), answers TEXT, contact TEXT, created_at TEXT DEFAULT(datetime('now')));
            CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, from_id TEXT, from_contact TEXT, from_role TEXT, message TEXT, read INTEGER DEFAULT 0, created_at TEXT DEFAULT(datetime('now')));
            CREATE TABLE IF NOT EXISTS connections (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, matched_id TEXT, status TEXT, created_at TEXT DEFAULT(datetime('now')), UNIQUE(user_id,matched_id));
            CREATE TABLE IF NOT EXISTS math_users (id TEXT PRIMARY KEY, email TEXT UNIQUE, password_hash TEXT, nickname TEXT DEFAULT '', membership TEXT DEFAULT 'free', created_at TEXT DEFAULT(datetime('now')));
            CREATE TABLE IF NOT EXISTS problems (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, content TEXT, subject TEXT, difficulty INTEGER DEFAULT 1, tags TEXT DEFAULT '[]', solution TEXT DEFAULT '', source TEXT DEFAULT '', created_at TEXT DEFAULT(datetime('now')));
            CREATE TABLE IF NOT EXISTS user_problem_status (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, problem_id INTEGER, status TEXT DEFAULT 'unsolved', wrong_reason TEXT DEFAULT '', marked INTEGER DEFAULT 0, attempted_at TEXT DEFAULT(datetime('now')), UNIQUE(user_id,problem_id));
            CREATE TABLE IF NOT EXISTS forum_categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, slug TEXT UNIQUE, sort_order INTEGER DEFAULT 0);
            INSERT OR IGNORE INTO forum_categories(name,slug,sort_order) VALUES('数学分析','sfx',1),('高等代数','gda',2),('常微分方程','cwe',3),('抽象代数','cxd',4),('实变函数','sbf',5),('复变函数','fbf',6),('概率与统计','glt',7),('泛函分析','fhf',8),('初等数论','cds',9),('微分几何','wfj',10),('考研真题','kyz',11),('综合交流','zhj',12);
            CREATE TABLE IF NOT EXISTS forum_posts (id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, user_id TEXT, title TEXT, content TEXT, created_at TEXT DEFAULT(datetime('now')), updated_at TEXT DEFAULT(datetime('now')));
            CREATE TABLE IF NOT EXISTS forum_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, user_id TEXT, content TEXT, created_at TEXT DEFAULT(datetime('now')));
            CREATE TABLE IF NOT EXISTS pdf_materials (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, description TEXT DEFAULT '', file_url TEXT, category TEXT DEFAULT '', uploader_id TEXT, created_at TEXT DEFAULT(datetime('now')));
        """)
        self._conn.commit()
    def table(self, name): return _TableProxy(self, name)


# ══════════════════════ 导出 ══════════════════════
if _IS_PG:
    # 懒连接：不在 import 时连 PG，否则连接失败会炸掉整个应用（连 /health 都起不来）
    db = type('PgDB', (), {'table': lambda s, n: _TableProxy(None, n)})()
else:
    db = _SQLiteDB()
