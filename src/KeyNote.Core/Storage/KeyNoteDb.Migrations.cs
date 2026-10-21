using System.Collections.Concurrent;
using System.Globalization;
using System.Text;
using KeyNote.Core.Settings;
using KeyNote.Core.Utils;
using Microsoft.Data.Sqlite;

namespace KeyNote.Core.Storage;

/// 数据库迁移 v1~v6(与历史 Python 版库兼容)与会话记录。
public static partial class KeyNoteDb
{

    // ──── 迁移 v1~v6 ────
    private static void RunMigrations()
    {
        Exec("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL)");
        var current = Convert.ToInt64(Scalar("SELECT COALESCE(MAX(version), 0) FROM schema_version") ?? 0L);
        if (current < 1) MigrateToV1();
        if (current < 2) MigrateToV2();
        if (current < 3) MigrateToV3();
        if (current < 4) MigrateToV4();
        if (current < 5) MigrateToV5();
        if (current < 6) MigrateToV6();
    }

    private static void MigrateToV1()
    {
        Exec("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at INTEGER NOT NULL, ended_at INTEGER)");
        Exec("CREATE TABLE IF NOT EXISTS keypresses (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, key TEXT NOT NULL)");
        if (!TableHasColumn("keypresses", "session_id"))
        {
            Exec("ALTER TABLE keypresses ADD COLUMN session_id INTEGER REFERENCES sessions(id)");
        }
        Exec("CREATE INDEX IF NOT EXISTS idx_session_ts ON keypresses(session_id, ts)");
        Exec("CREATE INDEX IF NOT EXISTS idx_ts_key ON keypresses(ts, key)");
        Exec("INSERT INTO schema_version(version, applied_at) VALUES (1, " + NowMs() + ")");
    }

    private static void MigrateToV2()
    {
        Exec("CREATE TABLE IF NOT EXISTS agg_minute (minute_ts INTEGER PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0)");
        Exec("CREATE TABLE IF NOT EXISTS agg_hour (hour_ts INTEGER PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0)");
        Exec("CREATE TABLE IF NOT EXISTS agg_dow_hour (dow INTEGER NOT NULL, hour INTEGER NOT NULL, count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (dow, hour))");
        Exec("CREATE TABLE IF NOT EXISTS agg_key_total (key TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0)");
        Exec("INSERT INTO schema_version(version, applied_at) VALUES (2, " + NowMs() + ")");
    }

    private static void MigrateToV3()
    {
        Exec("CREATE TABLE IF NOT EXISTS agg_day (day_ts INTEGER PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0)");
        Exec("INSERT INTO schema_version(version, applied_at) VALUES (3, " + NowMs() + ")");
    }

    private static void MigrateToV4()
    {
        // 旧数据按 UTC 整除分桶,回填为本地整点/整分/整日
        // 不开显式事务:逐语句自动提交,重写幂等;中断则版本号未推进,下次重跑
        RewriteBuckets("agg_day", "day_ts", LocalMidnightMs);
        RewriteBuckets("agg_hour", "hour_ts", LocalHourMs);
        RewriteBuckets("agg_minute", "minute_ts", LocalMinuteMs);
        Exec("INSERT INTO schema_version(version, applied_at) VALUES (4, " + NowMs() + ")");
    }

    private static void RewriteBuckets(string table, string column, Func<DateTime, long> toLocal)
    {
        var buckets = new Dictionary<long, long>();
        using (var read = _conn!.CreateCommand())
        {
            read.CommandText = $"SELECT {column}, count FROM {table}";
            using var r = read.ExecuteReader();
            while (r.Read())
            {
                var oldTs = r.GetInt64(0);
                var cnt = r.GetInt64(1);
                var local = DateTimeOffset.FromUnixTimeMilliseconds(oldTs).LocalDateTime;
                var newTs = toLocal(local);
                buckets[newTs] = buckets.GetValueOrDefault(newTs) + cnt;
            }
        }
        Exec($"DELETE FROM {table}");
        if (buckets.Count == 0) return;
        using var ins = _conn.CreateCommand();
        ins.CommandText = $"INSERT INTO {table}({column}, count) VALUES ($ts, $c) " +
                         "ON CONFLICT(" + column + ") DO UPDATE SET count = count + excluded.count";
        foreach (var (ts, cnt) in buckets)
        {
            ins.Parameters.Clear();
            ins.Parameters.AddWithValue("$ts", ts);
            ins.Parameters.AddWithValue("$c", cnt);
            ins.ExecuteNonQuery();
        }
    }

    private static void MigrateToV5()
    {
        Exec("CREATE TABLE IF NOT EXISTS mouse_clicks (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, button TEXT NOT NULL, session_id INTEGER REFERENCES sessions(id))");
        Exec("CREATE INDEX IF NOT EXISTS idx_mc_ts ON mouse_clicks(ts)");
        Exec("CREATE TABLE IF NOT EXISTS agg_mouse_button_total (button TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0)");
        Exec("INSERT INTO schema_version(version, applied_at) VALUES (5, " + NowMs() + ")");
    }

    private static void MigrateToV6()
    {
        Exec("CREATE TABLE IF NOT EXISTS agg_key_type_total (type TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0)");
        Exec("INSERT INTO schema_version(version, applied_at) VALUES (6, " + NowMs() + ")");
    }

    private static bool TableHasColumn(string table, string column)
    {
        try
        {
            using var cmd = _conn!.CreateCommand();
            cmd.CommandText = $"PRAGMA table_info({table})";
            using var r = cmd.ExecuteReader();
            while (r.Read())
            {
                if (string.Equals(r.GetString(1), column, StringComparison.OrdinalIgnoreCase)) return true;
            }
        }
        catch
        {
            // 表不存在视为无该列
        }
        return false;
    }

    // ──── 会话 ────
    private static void StartSession()
    {
        using var cmd = _conn!.CreateCommand();
        cmd.CommandText = "INSERT INTO sessions(started_at) VALUES ($ts)";
        cmd.Parameters.AddWithValue("$ts", NowMs());
        cmd.ExecuteNonQuery();
        // last_insert_rowid 是连接级的,必须同连接取
        using var idCmd = _conn.CreateCommand();
        idCmd.CommandText = "SELECT last_insert_rowid()";
        _sessionId = Convert.ToInt64(idCmd.ExecuteScalar() ?? 0L);
    }

    private static void EndSession()
    {
        if (_conn is null || _sessionId is null) return;
        using var cmd = Read()!.CreateCommand();
        cmd.CommandText = "UPDATE sessions SET ended_at = $ts WHERE id = $id";
        cmd.Parameters.AddWithValue("$ts", NowMs());
        cmd.Parameters.AddWithValue("$id", _sessionId.Value);
        cmd.ExecuteNonQuery();
        _sessionId = null;
    }
}
