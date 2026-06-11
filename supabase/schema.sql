-- jack门 数据库建表
-- 在 Supabase SQL Editor 中全选执行

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    role        TEXT NOT NULL CHECK (role IN ('freshman', 'senior')),
    answers     JSONB NOT NULL,
    contact     TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 通知表
CREATE TABLE IF NOT EXISTS notifications (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    from_id     TEXT NOT NULL,
    from_contact TEXT,
    from_role   TEXT,
    message     TEXT NOT NULL,
    read        BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, read);

-- RLS 策略：允许匿名读写（校园小应用，无需登录）
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- users 表：所有人可读写
CREATE POLICY "anon_can_read_users" ON users FOR SELECT USING (true);
CREATE POLICY "anon_can_insert_users" ON users FOR INSERT WITH CHECK (true);

-- notifications 表：所有人可读写
CREATE POLICY "anon_can_read_notifications" ON notifications FOR SELECT USING (true);
CREATE POLICY "anon_can_insert_notifications" ON notifications FOR INSERT WITH CHECK (true);
CREATE POLICY "anon_can_update_notifications" ON notifications FOR UPDATE USING (true);
