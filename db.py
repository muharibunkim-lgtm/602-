import sqlite3
import pandas as pd

DB_PATH = "stock_game.db"

INITIAL_COMPANIES = [
    ("미래IT",    "IT",     10000),
    ("글로벌무역", "무역",    8000),
    ("행복식품",  "식품",    5000),
    ("클린에너지", "에너지", 12000),
]

INITIAL_GOLD_PRICE     = 100000
INITIAL_BTC_PRICE      = 5000000
INITIAL_BOND_RATE      = 0.5
INITIAL_SAVING_RATE    = 3.0
INITIAL_SAVING_PERIOD  = 5
INITIAL_INFLATION_RATE = 0.3

NUM_STUDENTS     = 23
INITIAL_CASH     = 1_000_000
DEFAULT_PASSWORD = "0000"


def get_connection():
    """
    로컬 SQLite 전용 연결 함수.
    - WAL 모드: 한 명이 쓰는 동안에도 다른 사람이 읽을 수 있게 해줌
    - busy_timeout: 락이 걸려도 즉시 에러 대신 최대 8초 대기 후 재시도
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            company_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            sector        TEXT    NOT NULL,
            current_price INTEGER NOT NULL,
            prev_price    INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS alt_assets (
            asset_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_type    TEXT    NOT NULL UNIQUE,
            name          TEXT    NOT NULL,
            unit          TEXT    NOT NULL,
            current_price REAL    NOT NULL,
            prev_price    REAL    NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS game_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS news (
            news_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            day        INTEGER NOT NULL,
            company_id INTEGER,
            content    TEXT    NOT NULL,
            news_type  TEXT    NOT NULL DEFAULT 'stock'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id      INTEGER PRIMARY KEY,
            cash            REAL    NOT NULL,
            cumulative_loss REAL    NOT NULL DEFAULT 0,
            password        TEXT    NOT NULL DEFAULT '0000'
        )
    """)

    for col, definition in [
        ("password",        "TEXT NOT NULL DEFAULT '0000'"),
        ("cumulative_loss", "REAL NOT NULL DEFAULT 0"),
    ]:
        try:
            c.execute(f"ALTER TABLE students ADD COLUMN {col} {definition}")
        except Exception:
            pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            holding_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            quantity   INTEGER NOT NULL DEFAULT 0,
            UNIQUE (student_id, company_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS alt_holdings (
            alt_holding_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id     INTEGER NOT NULL,
            asset_type     TEXT    NOT NULL,
            quantity       REAL    NOT NULL DEFAULT 0,
            UNIQUE (student_id, asset_type)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS bond_holdings (
            bond_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL UNIQUE,
            amount     REAL    NOT NULL DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS savings (
            saving_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            amount     REAL    NOT NULL,
            rate       REAL    NOT NULL,
            start_day  INTEGER NOT NULL,
            end_day    INTEGER NOT NULL,
            is_matured INTEGER NOT NULL DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            tx_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            asset_type TEXT    NOT NULL DEFAULT 'stock',
            company_id INTEGER,
            tx_type    TEXT    NOT NULL,
            quantity   REAL    NOT NULL,
            price      REAL    NOT NULL,
            reason     TEXT    NOT NULL,
            day        INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS inflation_log (
            log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            day         INTEGER NOT NULL,
            rate        REAL    NOT NULL,
            student_id  INTEGER NOT NULL,
            loss_amount REAL    NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            day        INTEGER NOT NULL,
            asset_type TEXT    NOT NULL,
            company_id INTEGER,
            asset_key  TEXT    NOT NULL,
            price      REAL    NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS asset_snapshot (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            day         INTEGER NOT NULL,
            student_id  INTEGER NOT NULL,
            total_value REAL    NOT NULL,
            UNIQUE (day, student_id)
        )
    """)
    
    # 초기 데이터 삽입 (숫자 인덱스 [0]으로 수정됨)
    c.execute("SELECT COUNT(*) FROM companies")
    if c.fetchone()[0] == 0:
        for name, sector, price in INITIAL_COMPANIES:
            c.execute(
                "INSERT INTO companies (name,sector,current_price,prev_price) VALUES (?,?,?,?)",
                (name, sector, price, price)
            )

    c.execute("SELECT COUNT(*) FROM alt_assets")
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO alt_assets (asset_type,name,unit,current_price,prev_price) VALUES (?,?,?,?,?)",
            ("gold", "금", "g", INITIAL_GOLD_PRICE, INITIAL_GOLD_PRICE)
        )
        c.execute(
            "INSERT INTO alt_assets (asset_type,name,unit,current_price,prev_price) VALUES (?,?,?,?,?)",
            ("bitcoin", "비트코인", "BTC", INITIAL_BTC_PRICE, INITIAL_BTC_PRICE)
        )

    defaults = {
        "day":            "1",
        "bond_rate":      str(INITIAL_BOND_RATE),
        "saving_rate":    str(INITIAL_SAVING_RATE),
        "saving_period":  str(INITIAL_SAVING_PERIOD),
        "inflation_rate": str(INITIAL_INFLATION_RATE),
    }
    for key, value in defaults.items():
        c.execute(
            "INSERT OR IGNORE INTO game_settings (key,value) VALUES (?,?)",
            (key, value)
        )

    c.execute("SELECT COUNT(*) FROM students")
    if c.fetchone()[0] == 0:
        for i in range(1, NUM_STUDENTS + 1):
            c.execute(
                "INSERT INTO students (student_id,cash,password) VALUES (?,?,?)",
                (i, INITIAL_CASH, DEFAULT_PASSWORD)
            )

    # 1일차 최초 가격을 이력에 기록 (그래프 시작점)
    c.execute("SELECT COUNT(*) as cnt FROM price_history")
    if c.fetchone()["cnt"] == 0:
        for name, sector, price in INITIAL_COMPANIES:
            row = c.execute(
                "SELECT company_id FROM companies WHERE name=? AND sector=?", (name, sector)
            ).fetchone()
            c.execute(
                "INSERT INTO price_history (day,asset_type,company_id,asset_key,price) VALUES (1,'stock',?,?,?)",
                (row["company_id"], name, price)
            )
        c.execute(
            "INSERT INTO price_history (day,asset_type,company_id,asset_key,price) VALUES (1,'gold',NULL,'gold',?)",
            (INITIAL_GOLD_PRICE,)
        )
        c.execute(
            "INSERT INTO price_history (day,asset_type,company_id,asset_key,price) VALUES (1,'bitcoin',NULL,'bitcoin',?)",
            (INITIAL_BTC_PRICE,)
        )

    
    conn.commit()
    conn.close()


def get_setting(key: str) -> str:
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM game_settings WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def set_setting(key: str, value: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO game_settings (key,value) VALUES (?,?)",
        (key, value)
    )
    conn.commit()
    conn.close()


def verify_student_password(student_id: int, password: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT password FROM students WHERE student_id=?", (student_id,)
    ).fetchone()
    conn.close()
    return row[0] == password if row else False


def update_student_password(student_id: int, new_password: str):
    conn = get_connection()
    conn.execute(
        "UPDATE students SET password=? WHERE student_id=?",
        (new_password, student_id)
    )
    conn.commit()
    conn.close()


def reset_all_passwords(new_password: str):
    conn = get_connection()
    conn.execute("UPDATE students SET password=?", (new_password,))
    conn.commit()
    conn.close()


def get_all_passwords() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql(
        "SELECT student_id, password FROM students ORDER BY student_id", conn
    )
    conn.close()
    return df


def reset_game(reset_password: bool = False):
    conn = get_connection()
    try:
        try:
            conn.execute("BEGIN")
        except Exception:
            pass

        conn.execute("DELETE FROM holdings")
        conn.execute("DELETE FROM alt_holdings")
        conn.execute("DELETE FROM bond_holdings")
        conn.execute("DELETE FROM savings")
        conn.execute("DELETE FROM transactions")
        conn.execute("DELETE FROM news")
        conn.execute("DELETE FROM inflation_log")

        if reset_password:
            conn.execute(
                "UPDATE students SET cash=?, cumulative_loss=0, password=?",
                (INITIAL_CASH, DEFAULT_PASSWORD)
            )
        else:
            conn.execute(
                "UPDATE students SET cash=?, cumulative_loss=0",
                (INITIAL_CASH,)
            )

        for name, sector, price in INITIAL_COMPANIES:
            conn.execute(
                "UPDATE companies SET current_price=?, prev_price=? WHERE name=? AND sector=?",
                (price, price, name, sector)
            )
        conn.execute(
            "UPDATE alt_assets SET current_price=?, prev_price=? WHERE asset_type='gold'",
            (INITIAL_GOLD_PRICE, INITIAL_GOLD_PRICE)
        )
        conn.execute(
            "UPDATE alt_assets SET current_price=?, prev_price=? WHERE asset_type='bitcoin'",
            (INITIAL_BTC_PRICE, INITIAL_BTC_PRICE)
        )

        for key, val in [
            ("day",            "1"),
            ("bond_rate",      str(INITIAL_BOND_RATE)),
            ("saving_rate",    str(INITIAL_SAVING_RATE)),
            ("saving_period",  str(INITIAL_SAVING_PERIOD)),
            ("inflation_rate", str(INITIAL_INFLATION_RATE)),
        ]:
            conn.execute(
                "INSERT OR REPLACE INTO game_settings (key,value) VALUES (?,?)",
                (key, val)
            )

        conn.commit()
        conn.close()
        return True, "게임이 성공적으로 초기화되었습니다!"
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()
        return False, f"오류 발생: {e}"


def get_game_summary() -> dict:
    conn = get_connection()
    day      = int(get_setting("day") or 1)
    tx_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    news_cnt = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    active   = conn.execute(
        "SELECT COUNT(DISTINCT student_id) FROM transactions"
    ).fetchone()[0]
    conn.close()
    return {
        "current_day":      day,
        "tx_count":        tx_count,
        "news_count":      news_cnt,
        "active_students": active,
    }


def grant_emergency_fund(student_id: int, amount: float, day: int, reason: str = "긴급 지원금"):
    """교사가 파산 위기 학생에게 긴급 지원금을 지급합니다."""
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE students SET cash = cash + ? WHERE student_id=?",
            (amount, student_id)
        )
        conn.execute(
            """
            INSERT INTO transactions
                (student_id, asset_type, tx_type, quantity, price, reason, day)
            VALUES (?, 'emergency', 'buy', 1, ?, ?, ?)
            """,
            (student_id, amount, reason, day)
        )
        conn.commit()
        conn.close()
        return True, f"{student_id}번 학생에게 {int(amount):,}원 긴급 지원금을 지급했습니다."
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, str(e)


def log_price_history(day: int):
    """현재 시세를 이력 테이블에 기록합니다. (하루 경과 시 호출)"""
    conn = get_connection()
    companies = conn.execute("SELECT company_id, name, current_price FROM companies").fetchall()
    for row in companies:
        conn.execute(
            "INSERT INTO price_history (day,asset_type,company_id,asset_key,price) VALUES (?,?,?,?,?)",
            (day, "stock", row["company_id"], row["name"], row["current_price"])
        )
    alts = conn.execute("SELECT asset_type, current_price FROM alt_assets").fetchall()
    for row in alts:
        conn.execute(
            "INSERT INTO price_history (day,asset_type,company_id,asset_key,price) VALUES (?,?,NULL,?,?)",
            (day, row["asset_type"], row["asset_type"], row["current_price"])
        )
    conn.commit()
    conn.close()


def get_price_history(asset_key: str) -> pd.DataFrame:
    """특정 기업명 또는 자산(gold/bitcoin)의 날짜별 가격 이력을 가져옵니다."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT day, price FROM price_history WHERE asset_key=? ORDER BY day",
        (asset_key,)
    )
    rows = cur.fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["day", "price"]) if rows else pd.DataFrame(columns=["day", "price"])


def record_student_snapshot(day: int, student_id: int, total_value: float):
    """학생의 특정 일자 총자산을 기록합니다. (하루 경과 시 호출)"""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO asset_snapshot (day,student_id,total_value) VALUES (?,?,?)",
        (day, student_id, total_value)
    )
    conn.commit()
    conn.close()


def get_student_snapshot_history(student_id: int) -> pd.DataFrame:
    """학생의 날짜별 총자산 변화 이력을 가져옵니다."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT day, total_value FROM asset_snapshot WHERE student_id=? ORDER BY day",
        (student_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["day", "total_value"]) if rows else pd.DataFrame(columns=["day", "total_value"])
