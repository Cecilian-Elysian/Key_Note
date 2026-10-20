using System.Collections.Concurrent;
using System.Globalization;
using System.Text;
using KeyNote.Core.Settings;
using KeyNote.Core.Utils;
using Microsoft.Data.Sqlite;

namespace KeyNote.Core.Storage;

/// SQLite 持久化层:异步批量写入 + 聚合表(分/时/天/周×时/按键/按键类型/鼠标)+ 迁移 v1~v6
/// + 保留策略清理 + 备份/导出/健康检查(1:1 移植 Python db.py)。
public static class KeyNoteDb
{
    private const long MinMs = 10_000_000_000;      // 1970-04-26,低于此视为脏数据
    private const long MaxMs = 4_102_444_800_000;   // 2100-01-01

    private static readonly object Gate = new();
    private static SqliteConnection? _conn;      // 读/管理连接(UI 线程)
    private static SqliteConnection? _writerConn; // 写连接(仅 writer 线程独占)
    private static Thread? _writerThread;
    private static BlockingCollection<WriteItem>? _queue;
    private static volatile bool _shutdown;
    private static long? _sessionId;
    private static int _retentionDays = 365;
    private static DateTime _lastCleanup = DateTime.UtcNow;

    public static string DbPath { get; private set; } = "";
    public static string BackupDir { get; private set; } = "";
    public static string LogPath { get; private set; } = "";

    private readonly record struct WriteItem(double Ts, char Kind, string Payload, string KeyType);

    // ──── 初始化 ────
    public static void Init(AppSettings cfg)
    {
        lock (Gate)
        {
            var dataDir = cfg.GetString("data_dir");
            if (string.IsNullOrEmpty(dataDir)) dataDir = AppPaths.DataDir();
            Directory.CreateDirectory(dataDir);
            DbPath = Path.Combine(dataDir, "keynote.db");
            BackupDir = cfg.GetString("backup_dir");
            if (string.IsNullOrEmpty(BackupDir)) BackupDir = Path.Combine(dataDir, "backups");
            LogPath = Path.Combine(dataDir, "keynote.log");

            var batchSize = Math.Max(1, cfg.GetInt("db_flush_batch_size", 200));
            var interval = Math.Max(0.05, cfg.GetDouble("db_flush_interval_sec", 1.0));
            _retentionDays = Math.Max(0, cfg.GetInt("db_retention_days", 365));

            _conn = new SqliteConnection(new SqliteConnectionStringBuilder
            {
                DataSource = DbPath,
                Pooling = true,
            }.ToString());
            _conn.Open();
            Exec("PRAGMA journal_mode=WAL");
            Exec("PRAGMA synchronous=NORMAL");
            Exec("PRAGMA temp_store=MEMORY");
            Exec("PRAGMA cache_size=-65536");
            Exec("PRAGMA mmap_size=268435456");
            Exec("PRAGMA wal_autocheckpoint=1000");
            Exec("PRAGMA busy_timeout=5000");

            RunMigrations();

            // 写线程独立连接:SqliteConnection 非线程安全,读写分连接(WAL 下并行)
            _writerConn = new SqliteConnection(new SqliteConnectionStringBuilder
            {
                DataSource = DbPath,
                Pooling = true,
            }.ToString());
            _writerConn.Open();
            Exec(_writerConn, "PRAGMA journal_mode=WAL");
            Exec(_writerConn, "PRAGMA synchronous=NORMAL");
            Exec(_writerConn, "PRAGMA temp_store=MEMORY");
            Exec(_writerConn, "PRAGMA busy_timeout=5000");

            _queue = new BlockingCollection<WriteItem>(new ConcurrentQueue<WriteItem>(), 100_000);
            _shutdown = false;
            _writerThread = new Thread(() => WriterLoop(batchSize, interval))
            {
                IsBackground = true,
                Name = "db-writer",
            };
            _writerThread.Start();

            StartSession();
            AutoBackupIfNeeded(Math.Max(0, cfg.GetInt("db_auto_backup_days", 7)));
        }
    }

    private static void Exec(string sql)
    {
        using var cmd = _conn!.CreateCommand();
        cmd.CommandText = sql;
        cmd.ExecuteNonQuery();
    }

    private static void Exec(SqliteConnection conn, string sql)
    {
        using var cmd = conn.CreateCommand();
        cmd.CommandText = sql;
        cmd.ExecuteNonQuery();
    }

    private static void Exec(SqliteConnection conn, string sql, params (string, object?)[] args)
    {
        using var cmd = conn.CreateCommand();
        cmd.CommandText = sql;
        foreach (var (n, v) in args) cmd.Parameters.AddWithValue(n, v ?? DBNull.Value);
        cmd.ExecuteNonQuery();
    }

    private static object? Scalar(string sql, params (string, object?)[] args)
    {
        using var cmd = Read()!.CreateCommand();
        cmd.CommandText = sql;
        foreach (var (n, v) in args) cmd.Parameters.AddWithValue(n, v ?? DBNull.Value);
        return cmd.ExecuteScalar();
    }

    /// 读连接按线程隔离(UI 线程 + 托盘线程并发读;WAL 下互不阻塞)。
    private static readonly ThreadLocal<SqliteConnection?> ReadLocal = new(CreateReadConn);

    private static SqliteConnection? CreateReadConn()
    {
        if (DbPath.Length == 0) return null;
        try
        {
            var c = new SqliteConnection(new SqliteConnectionStringBuilder
            {
                DataSource = DbPath,
                Pooling = true,
            }.ToString());
            c.Open();
            using (var pragma = c.CreateCommand())
            {
                pragma.CommandText = "PRAGMA busy_timeout=5000";
                pragma.ExecuteNonQuery();
            }
            return c;
        }
        catch (Exception ex)
        {
            CrashLog.Write("db.read.open", ex);
            return null;
        }
    }

    private static SqliteConnection? Read() => ReadLocal.Value;

    private static bool Ready => DbPath.Length > 0;

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

    // ──── 写入队列 ────
    public static void Enqueue(string key, string keyType) => EnqueueEvent('k', key, keyType);

    public static void EnqueueMouse(string button) => EnqueueEvent('m', button, "");

    private static void EnqueueEvent(char kind, string payload, string keyType)
    {
        var q = _queue;
        if (q is null || _shutdown) return;
        try
        {
            q.TryAdd(new WriteItem(DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0, kind, payload, keyType));
        }
        catch
        {
            // 队列满时丢弃(与 Python 版一致)
        }
    }

    private static void WriterLoop(int batchSize, double interval)
    {
        while (!_shutdown)
        {
            var batch = CollectBatch(batchSize, interval);
            if (batch.Count > 0)
            {
                FlushBatch(batch);
                MaybeCleanup();
            }
        }
        var final = new List<WriteItem>();
        while (_queue is not null && _queue.TryTake(out var item)) final.Add(item);
        if (final.Count > 0) FlushBatch(final);
    }

    private static List<WriteItem> CollectBatch(int batchSize, double interval)
    {
        var batch = new List<WriteItem>();
        var deadline = DateTime.UtcNow.AddSeconds(interval);
        while (batch.Count < batchSize && !_shutdown)
        {
            var remaining = (deadline - DateTime.UtcNow).TotalSeconds;
            if (remaining <= 0) break;
            var wait = Math.Min(remaining, 0.05);
            if (_queue is not null && _queue.TryTake(out var item, (int)(wait * 1000)))
            {
                batch.Add(item);
            }
            else if (batch.Count > 0)
            {
                break;
            }
        }
        return batch;
    }

    private static void FlushBatch(List<WriteItem> batch)
    {
        var kRows = new List<(long, string, long?)>();
        var mRows = new List<(long, string, long?)>();
        var minute = new Dictionary<long, long>();
        var hour = new Dictionary<long, long>();
        var dowHour = new Dictionary<(int, int), long>();
        var key = new Dictionary<string, long>();
        var keyType = new Dictionary<string, long>();
        var day = new Dictionary<long, long>();
        var mouse = new Dictionary<string, long>();
        var sid = _sessionId is > 0 ? _sessionId : null;

        foreach (var item in batch)
        {
            var tsMs = (long)(item.Ts * 1000);
            var local = DateTimeOffset.FromUnixTimeMilliseconds(tsMs).LocalDateTime;
            if (item.Kind == 'k')
            {
                kRows.Add((tsMs, item.Payload, sid));
                var mMs = LocalMinuteMs(local);
                var hMs = LocalHourMs(local);
                var dMs = LocalMidnightMs(local);
                minute[mMs] = minute.GetValueOrDefault(mMs) + 1;
                hour[hMs] = hour.GetValueOrDefault(hMs) + 1;
                var dh = (DowIndex(local), local.Hour);
                dowHour[dh] = dowHour.GetValueOrDefault(dh) + 1;
                key[item.Payload] = key.GetValueOrDefault(item.Payload) + 1;
                if (!string.IsNullOrEmpty(item.KeyType))
                {
                    keyType[item.KeyType] = keyType.GetValueOrDefault(item.KeyType) + 1;
                }
                day[dMs] = day.GetValueOrDefault(dMs) + 1;
            }
            else if (item.Kind == 'm')
            {
                mRows.Add((tsMs, item.Payload, sid));
                mouse[item.Payload] = mouse.GetValueOrDefault(item.Payload) + 1;
            }
        }

        try
        {
            using var tx = _writerConn!.BeginTransaction();
            if (kRows.Count > 0)
            {
                Exec(tx, "INSERT INTO keypresses (ts, key, session_id) VALUES ($ts, $key, $sid)", kRows.Select(r => new (string, object?)[] { ("$ts", r.Item1), ("$key", r.Item2), ("$sid", r.Item3) }));
                UpsertBuckets(tx, "agg_minute", "minute_ts", minute);
                UpsertBuckets(tx, "agg_hour", "hour_ts", hour);
                UpsertDowHour(tx, dowHour);
                UpsertTextBuckets(tx, "agg_key_total", "key", key);
                if (keyType.Count > 0) UpsertTextBuckets(tx, "agg_key_type_total", "type", keyType);
                UpsertBuckets(tx, "agg_day", "day_ts", day);
            }
            if (mRows.Count > 0)
            {
                Exec(tx, "INSERT INTO mouse_clicks (ts, button, session_id) VALUES ($ts, $btn, $sid)", mRows.Select(r => new (string, object?)[] { ("$ts", r.Item1), ("$btn", r.Item2), ("$sid", r.Item3) }));
                UpsertTextBuckets(tx, "agg_mouse_button_total", "button", mouse);
            }
            tx.Commit();
        }
        catch (Exception ex)
        {
            CrashLog.Write("db.write", ex);
        }
    }

    private static void Exec(SqliteTransaction tx, string sql, IEnumerable<(string, object?)[]> rows)
    {
        using var cmd = _writerConn!.CreateCommand();
        cmd.Transaction = tx;
        cmd.CommandText = sql;
        foreach (var row in rows)
        {
            cmd.Parameters.Clear();
            foreach (var (n, v) in row) cmd.Parameters.AddWithValue(n, v ?? DBNull.Value);
            cmd.ExecuteNonQuery();
        }
    }

    private static void UpsertBuckets(SqliteTransaction tx, string table, string column, Dictionary<long, long> buckets)
    {
        if (buckets.Count == 0) return;
        using var cmd = _writerConn!.CreateCommand();
        cmd.Transaction = tx;
        cmd.CommandText = $"INSERT INTO {table}({column}, count) VALUES ($ts, $c) " +
                         $"ON CONFLICT({column}) DO UPDATE SET count = count + excluded.count";
        foreach (var (ts, cnt) in buckets)
        {
            cmd.Parameters.Clear();
            cmd.Parameters.AddWithValue("$ts", ts);
            cmd.Parameters.AddWithValue("$c", cnt);
            cmd.ExecuteNonQuery();
        }
    }

    private static void UpsertTextBuckets(SqliteTransaction tx, string table, string column, Dictionary<string, long> buckets)
    {
        if (buckets.Count == 0) return;
        using var cmd = _writerConn!.CreateCommand();
        cmd.Transaction = tx;
        cmd.CommandText = $"INSERT INTO {table}({column}, count) VALUES ($k, $c) " +
                         $"ON CONFLICT({column}) DO UPDATE SET count = count + excluded.count";
        foreach (var (k, cnt) in buckets)
        {
            cmd.Parameters.Clear();
            cmd.Parameters.AddWithValue("$k", k);
            cmd.Parameters.AddWithValue("$c", cnt);
            cmd.ExecuteNonQuery();
        }
    }

    private static void UpsertDowHour(SqliteTransaction tx, Dictionary<(int, int), long> buckets)
    {
        if (buckets.Count == 0) return;
        using var cmd = _writerConn!.CreateCommand();
        cmd.Transaction = tx;
        cmd.CommandText = "INSERT INTO agg_dow_hour(dow, hour, count) VALUES ($d, $h, $c) " +
                         "ON CONFLICT(dow, hour) DO UPDATE SET count = count + excluded.count";
        foreach (var ((d, h), cnt) in buckets)
        {
            cmd.Parameters.Clear();
            cmd.Parameters.AddWithValue("$d", d);
            cmd.Parameters.AddWithValue("$h", h);
            cmd.Parameters.AddWithValue("$c", cnt);
            cmd.ExecuteNonQuery();
        }
    }

    private static void MaybeCleanup()
    {
        if (DateTime.UtcNow - _lastCleanup < TimeSpan.FromDays(1)) return;
        _lastCleanup = DateTime.UtcNow;
        if (_retentionDays <= 0) return;
        var cutoff = NowMs() - _retentionDays * 86_400_000L;
        try
        {
            Exec(_writerConn!, "DELETE FROM keypresses WHERE ts < $cut", ("$cut", cutoff));
            Exec(_writerConn!, "DELETE FROM mouse_clicks WHERE ts < $cut", ("$cut", cutoff));
            Exec(_writerConn!, "DELETE FROM sessions WHERE ended_at IS NOT NULL AND ended_at < $cut", ("$cut", cutoff));
        }
        catch (Exception ex)
        {
            CrashLog.Write("db.cleanup", ex);
        }
    }

    public static void SetRetentionDays(int days) => _retentionDays = Math.Max(0, days);

    // ──── 时间工具(与 Python 版一致) ────
    private static long NowMs() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
    private static long LocalMidnightMs(DateTime local) => new DateTimeOffset(local.Date).ToUnixTimeMilliseconds();
    private static long LocalHourMs(DateTime local) => new DateTimeOffset(new DateTime(local.Year, local.Month, local.Day, local.Hour, 0, 0)).ToUnixTimeMilliseconds();
    private static long LocalMinuteMs(DateTime local) => new DateTimeOffset(new DateTime(local.Year, local.Month, local.Day, local.Hour, local.Minute, 0)).ToUnixTimeMilliseconds();

    /// Python weekday():周一=0 … 周日=6
    private static int DowIndex(DateTime local) => ((int)local.DayOfWeek + 6) % 7;

    // ──── 查询接口 ────
    public static int CountToday()
    {
        if (!Ready) return 0;
        var midnight = LocalMidnightMs(DateTime.Now);
        return (int)(long)(Scalar("SELECT COUNT(*) FROM keypresses WHERE ts >= $ts", ("$ts", midnight)) ?? 0L);
    }

    public static long CountTotal()
    {
        if (!Ready) return 0;
        return (long)(Scalar("SELECT COALESCE(SUM(count), 0) FROM agg_minute WHERE minute_ts BETWEEN $a AND $b", ("$a", MinMs), ("$b", MaxMs)) ?? 0L);
    }

    public static List<(string Key, long Count)> TopKeys(int n = 20)
    {
        var rows = new List<(string, long)>();
        if (!Ready) return rows;
        using var cmd = Read()!.CreateCommand();
        cmd.CommandText = "SELECT key, count FROM agg_key_total ORDER BY count DESC LIMIT $n";
        cmd.Parameters.AddWithValue("$n", n);
        using var r = cmd.ExecuteReader();
        while (r.Read()) rows.Add((r.GetString(0), r.GetInt64(1)));
        return rows;
    }

    public static List<(long Ts, long Count)> RateSeries(int hours = 24)
    {
        var rows = new List<(long, long)>();
        if (!Ready) return rows;
        var since = Math.Max(MinMs, NowMs() - hours * 3_600_000L);
        using var cmd = Read()!.CreateCommand();
        cmd.CommandText = "SELECT minute_ts, count FROM agg_minute WHERE minute_ts BETWEEN $a AND $b ORDER BY minute_ts";
        cmd.Parameters.AddWithValue("$a", since);
        cmd.Parameters.AddWithValue("$b", MaxMs);
        using var r = cmd.ExecuteReader();
        while (r.Read()) rows.Add((r.GetInt64(0), r.GetInt64(1)));
        return rows;
    }

    /// 7×24 热力图:grid[weekday(周一=0), hour]
    public static int[,] HeatmapData(int days = 7)
    {
        var grid = new int[7, 24];
        if (!Ready) return grid;
        var since = Math.Max(MinMs, NowMs() - days * 86_400_000L);
        using var cmd = Read()!.CreateCommand();
        cmd.CommandText = "SELECT minute_ts, count FROM agg_minute WHERE minute_ts BETWEEN $a AND $b";
        cmd.Parameters.AddWithValue("$a", since);
        cmd.Parameters.AddWithValue("$b", MaxMs);
        using var r = cmd.ExecuteReader();
        while (r.Read())
        {
            var local = DateTimeOffset.FromUnixTimeMilliseconds(r.GetInt64(0)).LocalDateTime;
            grid[DowIndex(local), local.Hour] += (int)r.GetInt64(1);
        }
        return grid;
    }

    /// GitHub 风格年度热力图:grid[week, dow](周一=0)
    public static (int[,] Grid, DateTime Start, DateTime End) HeatmapYearly(int days = 365)
    {
        var end = DateTime.Today;
        var start = end.AddDays(-(days - 1));
        var grid = new int[53, 7];
        if (!Ready) return (grid, start, end);
        var since = Math.Max(MinMs, new DateTimeOffset(start).ToUnixTimeMilliseconds());
        using var cmd = Read()!.CreateCommand();
        cmd.CommandText = "SELECT day_ts, count FROM agg_day WHERE day_ts BETWEEN $a AND $b";
        cmd.Parameters.AddWithValue("$a", since);
        cmd.Parameters.AddWithValue("$b", MaxMs);
        using var r = cmd.ExecuteReader();
        while (r.Read())
        {
            var local = DateTimeOffset.FromUnixTimeMilliseconds(r.GetInt64(0)).LocalDateTime.Date;
            var delta = (local - start).Days;
            if (delta < 0 || delta >= days) continue;
            var week = delta / 7;
            var dow = DowIndex(local);
            if (week is >= 0 and < 53) grid[week, dow] += (int)r.GetInt64(1);
        }
        return (grid, start, end);
    }

    public static List<(long DayTs, long Count)> DailyCounts(int days = 30)
    {
        var rows = new List<(long, long)>();
        if (!Ready) return rows;
        var end = DateTime.Today;
        var start = end.AddDays(-(days - 1));
        var since = Math.Max(MinMs, new DateTimeOffset(start).ToUnixTimeMilliseconds());
        using var cmd = Read()!.CreateCommand();
        cmd.CommandText = "SELECT day_ts, count FROM agg_day WHERE day_ts BETWEEN $a AND $b ORDER BY day_ts";
        cmd.Parameters.AddWithValue("$a", since);
        cmd.Parameters.AddWithValue("$b", MaxMs);
        using var r = cmd.ExecuteReader();
        while (r.Read()) rows.Add((r.GetInt64(0), r.GetInt64(1)));
        return rows;
    }

    public static int StreakDays(int days = 365)
    {
        var byDay = new Dictionary<DateTime, long>();
        foreach (var (ts, c) in DailyCounts(days))
        {
            var d = DateTimeOffset.FromUnixTimeMilliseconds(ts).LocalDateTime.Date;
            byDay[d] = byDay.GetValueOrDefault(d) + c;
        }
        if (byDay.Count == 0) return 0;
        var cursor = DateTime.Today;
        var streak = 0;
        while (byDay.GetValueOrDefault(cursor) > 0)
        {
            streak++;
            cursor = cursor.AddDays(-1);
        }
        return streak;
    }

    public static int DailyAverage(int days = 7)
    {
        if (days <= 0) return 0;
        var byDay = new Dictionary<DateTime, long>();
        foreach (var (ts, c) in DailyCounts(days))
        {
            var d = DateTimeOffset.FromUnixTimeMilliseconds(ts).LocalDateTime.Date;
            byDay[d] = byDay.GetValueOrDefault(d) + c;
        }
        var end = DateTime.Today;
        var start = end.AddDays(-(days - 1));
        long total = 0;
        for (var cursor = start; cursor <= end; cursor = cursor.AddDays(1))
        {
            total += byDay.GetValueOrDefault(cursor);
        }
        return (int)(total / days);
    }

    public static int DailyActiveDays(int days = 30)
    {
        if (!Ready) return 0;
        var end = DateTime.Today;
        var start = end.AddDays(-(days - 1));
        var since = Math.Max(MinMs, new DateTimeOffset(start).ToUnixTimeMilliseconds());
        return (int)(long)(Scalar("SELECT COUNT(*) FROM agg_day WHERE day_ts BETWEEN $a AND $b AND count > 0", ("$a", since), ("$b", MaxMs)) ?? 0L);
    }

    public static List<(long HourTs, long Count)> HourlyToday()
    {
        var rows = new List<(long, long)>();
        if (!Ready) return rows;
        var since = Math.Max(MinMs, LocalMidnightMs(DateTime.Now));
        using var cmd = Read()!.CreateCommand();
        cmd.CommandText = "SELECT hour_ts, count FROM agg_hour WHERE hour_ts BETWEEN $a AND $b ORDER BY hour_ts";
        cmd.Parameters.AddWithValue("$a", since);
        cmd.Parameters.AddWithValue("$b", MaxMs);
        using var r = cmd.ExecuteReader();
        while (r.Read()) rows.Add((r.GetInt64(0), r.GetInt64(1)));
        return rows;
    }

    public static double CpmRecent(int minutes = 5)
    {
        if (_conn is null || minutes <= 0) return 0;
        var since = Math.Max(MinMs, NowMs() - minutes * 60_000L);
        var total = (long)(Scalar("SELECT COALESCE(SUM(count), 0) FROM agg_minute WHERE minute_ts BETWEEN $a AND $b", ("$a", since), ("$b", MaxMs)) ?? 0L);
        return total / (double)minutes;
    }

    public static long MouseTotal()
    {
        if (!Ready) return 0;
        return (long)(Scalar("SELECT COALESCE(SUM(count), 0) FROM agg_mouse_button_total") ?? 0L);
    }

    public static List<(string Button, long Count)> MouseByButton()
    {
        var rows = new List<(string, long)>();
        if (!Ready) return rows;
        using var cmd = Read()!.CreateCommand();
        cmd.CommandText = "SELECT button, count FROM agg_mouse_button_total ORDER BY count DESC";
        using var r = cmd.ExecuteReader();
        while (r.Read()) rows.Add((r.GetString(0), r.GetInt64(1)));
        return rows;
    }

    public static List<(string Type, long Count)> KeyTypeDistribution()
    {
        var rows = new List<(string, long)>();
        if (!Ready) return rows;
        using var cmd = Read()!.CreateCommand();
        cmd.CommandText = "SELECT type, count FROM agg_key_type_total ORDER BY count DESC";
        using var r = cmd.ExecuteReader();
        while (r.Read()) rows.Add((r.GetString(0), r.GetInt64(1)));
        return rows;
    }

    // ──── 备份/维护 ────
    public static string? Backup(AppSettings cfg, bool manual = false)
    {
        if (!Ready) return null;
        try
        {
            Directory.CreateDirectory(BackupDir);
            var ts = DateTime.Now.ToString("yyyyMMdd-HHmmss");
            var dest = Path.Combine(BackupDir, $"keynote-{ts}.db");
            using (var bck = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = dest }.ToString()))
            {
                bck.Open();
                _conn.BackupDatabase(bck);
            }
            PruneOldBackups(Math.Max(0, cfg.GetInt("backup_keep_daily", 7)), Math.Max(0, cfg.GetInt("backup_keep_weekly", 4)));
            return dest;
        }
        catch (Exception ex)
        {
            CrashLog.Write("db.backup", ex);
            return null;
        }
    }

    private static void AutoBackupIfNeeded(int intervalDays)
    {
        if (intervalDays <= 0) return;
        var cfg = AppSettings.Load();
        if (!Directory.Exists(BackupDir))
        {
            Backup(cfg);
            return;
        }
        var files = BackupFiles();
        if (files.Count == 0 || (DateTime.Now - files[0].LastWriteTime).TotalDays > intervalDays)
        {
            Backup(cfg);
        }
    }

    private static List<FileInfo> BackupFiles()
    {
        if (!Directory.Exists(BackupDir)) return new List<FileInfo>();
        return new DirectoryInfo(BackupDir)
            .GetFiles("keynote-*.db")
            .OrderByDescending(f => f.LastWriteTime)
            .ToList();
    }

    private static void PruneOldBackups(int keepDaily, int keepWeekly)
    {
        var files = BackupFiles();
        if (files.Count == 0) return;
        var keep = new HashSet<FileInfo>();
        foreach (var f in files.Take(keepDaily)) keep.Add(f);
        var weekly = new List<FileInfo>();
        long lastWeek = -1;
        foreach (var f in files)
        {
            var week = (long)(f.LastWriteTime.Ticks / TimeSpan.TicksPerDay / 7);
            if (week != lastWeek)
            {
                weekly.Add(f);
                lastWeek = week;
            }
            if (weekly.Count >= keepWeekly) break;
        }
        foreach (var f in weekly) keep.Add(f);
        foreach (var f in files)
        {
            if (keep.Contains(f)) continue;
            try { f.Delete(); } catch { /* 占用则跳过 */ }
        }
    }

    public static bool Vacuum()
    {
        if (!Ready) return false;
        try
        {
            Exec("VACUUM");
            return true;
        }
        catch (Exception ex)
        {
            CrashLog.Write("db.vacuum", ex);
            return false;
        }
    }

    public static int ExportCsv(string path, int days = 30)
    {
        if (!Ready) return 0;
        var cutoff = NowMs() - Math.Max(1, days) * 86_400_000L;
        using var cmd = Read()!.CreateCommand();
        cmd.CommandText = "SELECT ts, key, session_id FROM keypresses WHERE ts >= $c ORDER BY ts";
        cmd.Parameters.AddWithValue("$c", cutoff);
        using var r = cmd.ExecuteReader();
        using var w = new StreamWriter(path, append: false, Encoding.UTF8);
        w.WriteLine("ts_iso,key,session_id");
        var count = 0;
        while (r.Read())
        {
            var ts = r.GetInt64(0);
            var key = r.GetString(1);
            var sid = r.IsDBNull(2) ? "" : r.GetInt64(2).ToString(CultureInfo.InvariantCulture);
            var iso = DateTimeOffset.FromUnixTimeMilliseconds(ts).LocalDateTime.ToString("yyyy-MM-dd HH:mm:ss");
            w.WriteLine($"{iso},{key},{sid}");
            count++;
        }
        return count;
    }

    public static HealthInfo Health()
    {
        var info = new HealthInfo { RetentionDays = _retentionDays };
        if (!Ready) return info;
        try
        {
            info.SizeBytes = File.Exists(DbPath) ? new FileInfo(DbPath).Length : 0;
            var wal = DbPath + "-wal";
            var shm = DbPath + "-shm";
            info.WalBytes = File.Exists(wal) ? new FileInfo(wal).Length : 0;
            info.ShmBytes = File.Exists(shm) ? new FileInfo(shm).Length : 0;
            info.RawCount = (int)(long)(Scalar("SELECT COUNT(*) FROM keypresses") ?? 0L);
            info.MinuteBuckets = (int)(long)(Scalar("SELECT COUNT(*) FROM agg_minute") ?? 0L);
            info.UniqueKeys = (int)(long)(Scalar("SELECT COUNT(*) FROM agg_key_total") ?? 0L);
            var backups = BackupFiles();
            info.LastBackupTs = backups.Count > 0 ? (long)(backups[0].LastWriteTime - new DateTime(1970, 1, 1)).TotalSeconds : 0;
        }
        catch (Exception ex)
        {
            CrashLog.Write("db.health", ex);
        }
        return info;
    }

    public static void Close()
    {
        lock (Gate)
        {
            _shutdown = true;
            try { _writerThread?.Join(TimeSpan.FromSeconds(5)); } catch { /* 忽略 */ }
            _writerThread = null;
            _queue = null;
            EndSession();
            if (_writerConn is not null)
            {
                try { _writerConn.Close(); } catch { /* 忽略 */ }
                _writerConn = null;
            }
            if (_conn is not null)
            {
                try { Exec("PRAGMA wal_checkpoint(TRUNCATE)"); } catch { /* 忽略 */ }
                try { _conn.Close(); } catch { /* 忽略 */ }
                _conn = null;
            }
            _sessionId = null;
        }
    }
}

/// DB 健康快照(托盘菜单用)。
public sealed class HealthInfo
{
    public long SizeBytes { get; set; }
    public long WalBytes { get; set; }
    public long ShmBytes { get; set; }
    public int RawCount { get; set; }
    public int MinuteBuckets { get; set; }
    public int UniqueKeys { get; set; }
    public long LastBackupTs { get; set; }
    public int RetentionDays { get; set; }
}
