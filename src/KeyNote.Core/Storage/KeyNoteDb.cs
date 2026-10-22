using System.Collections.Concurrent;
using System.Globalization;
using System.Text;
using KeyNote.Core.Settings;
using KeyNote.Core.Utils;
using Microsoft.Data.Sqlite;

namespace KeyNote.Core.Storage;

/// SQLite 持久化层:异步批量写入 + 聚合表(分/时/天/周×时/按键/按键类型/鼠标)+ 迁移 v1~v6
/// + 保留策略清理 + 备份/导出/健康检查(1:1 移植 Python db.py)。

/// SQLite 持久化层:连接管理 + 聚合查询 + 时间桶工具(迁移/写入/维护见同目录其它分部文件)。
public static partial class KeyNoteDb
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

    /// 当前数据目录(备份目录默认值基于它)
    private static string _dataDir = "";

    /// 运行时更新备份目录(设置页改「备份目录」后立即生效,无需重启)
    public static void SetBackupDir(string dir)
    {
        lock (Gate)
        {
            BackupDir = string.IsNullOrEmpty(dir) ? Path.Combine(_dataDir, "backups") : dir;
        }
    }

    private readonly record struct WriteItem(double Ts, char Kind, string Payload, string KeyType);

    // ──── 初始化 ────
    public static void Init(AppSettings cfg)
    {
        lock (Gate)
        {
            var dataDir = cfg.GetString("data_dir");
            if (string.IsNullOrEmpty(dataDir)) dataDir = AppPaths.DataDir();
            Directory.CreateDirectory(dataDir);
            _dataDir = dataDir;
            DbPath = Path.Combine(dataDir, "keynote.db");
            BackupDir = cfg.GetString("backup_dir");
            if (string.IsNullOrEmpty(BackupDir)) BackupDir = Path.Combine(dataDir, "backups");

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

    /// 事务内执行单条语句(连接上已有活动事务时,命令必须挂上该事务)。
    private static void Exec(SqliteTransaction tx, string sql)
    {
        using var cmd = tx.Connection!.CreateCommand();
        cmd.Transaction = tx;
        cmd.CommandText = sql;
        cmd.ExecuteNonQuery();
    }

    private static object? Scalar(string sql, params (string, object?)[] args)
    {
        using var cmd = ReadCmd(sql);
        if (cmd is null) return null;
        foreach (var (n, v) in args) cmd.Parameters.AddWithValue(n, v ?? DBNull.Value);
        return cmd.ExecuteScalar();
    }

    /// 安全读命令:读连接不可用(数据库打不开)时返回 null,由调用方返回空结果而不是抛 NRE。
    private static SqliteCommand? ReadCmd(string sql)
    {
        var conn = Read();
        if (conn is null) return null;
        var cmd = conn.CreateCommand();
        cmd.CommandText = sql;
        return cmd;
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

    /// 全时累计按键数:走小时桶(agg_hour 行数远小于 agg_minute,避免每次刷新全表扫)。
    public static long CountTotal()
    {
        if (!Ready) return 0;
        return (long)(Scalar("SELECT COALESCE(SUM(count), 0) FROM agg_hour") ?? 0L);
    }

    /// 近 N 天按键数(按日桶求和)。
    public static long CountKeysSince(int days)
    {
        if (!Ready) return 0;
        var since = Math.Max(MinMs, new DateTimeOffset(DateTime.Today.AddDays(-(days - 1))).ToUnixTimeMilliseconds());
        return (long)(Scalar("SELECT COALESCE(SUM(count), 0) FROM agg_day WHERE day_ts >= $a", ("$a", since)) ?? 0L);
    }

    /// 近 N 天鼠标点击数(鼠标聚合表无时间维度,只能查 raw)。
    /// 口径与键盘侧一致:按日历日(今日零点起算 N 天),不用滚动 24 小时。
    public static long MouseSince(int days)
    {
        if (!Ready) return 0;
        var since = Math.Max(MinMs, LocalMidnightMs(DateTime.Today.AddDays(-(days - 1))));
        return (long)(Scalar("SELECT COUNT(*) FROM mouse_clicks WHERE ts >= $a", ("$a", since)) ?? 0L);
    }

    public static List<(string Key, long Count)> TopKeys(int n = 20)
    {
        var rows = new List<(string, long)>();
        if (!Ready) return rows;
        using var cmd = ReadCmd("SELECT key, count FROM agg_key_total ORDER BY count DESC LIMIT $n");
        if (cmd is null) return rows;
        cmd.Parameters.AddWithValue("$n", n);
        using var r = cmd.ExecuteReader();
        while (r.Read()) rows.Add((r.GetString(0), r.GetInt64(1)));
        return rows;
    }

    /// Top 按键(合并大小写):统计页与键盘热力图口径统一,避免两页数字对不上。
    public static List<(string Key, long Count)> TopKeysMergedCase(int n = 20)
    {
        var rows = new List<(string, long)>();
        if (!Ready) return rows;
        using var cmd = ReadCmd("SELECT LOWER(key) AS k, SUM(count) AS c FROM agg_key_total " +
                                "GROUP BY LOWER(key) ORDER BY c DESC LIMIT $n");
        if (cmd is null) return rows;
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
        using var cmd = ReadCmd("SELECT minute_ts, count FROM agg_minute WHERE minute_ts BETWEEN $a AND $b ORDER BY minute_ts");
        if (cmd is null) return rows;
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
        using var cmd = ReadCmd("SELECT minute_ts, count FROM agg_minute WHERE minute_ts BETWEEN $a AND $b");
        if (cmd is null) return grid;
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

    /// GitHub 风格年度热力图数据:按天返回(count 数组,长度 = days)。
    /// 早期版本返回固定 53 周网格,days > 371 时超出部分被静默丢弃 → 改为日粒度直返。
    public static (long[] Daily, DateTime Start, DateTime End) HeatmapYearly(int days = 365)
    {
        var end = DateTime.Today;
        var start = end.AddDays(-(days - 1));
        var daily = new long[Math.Max(1, days)];
        if (!Ready) return (daily, start, end);
        var since = Math.Max(MinMs, new DateTimeOffset(start).ToUnixTimeMilliseconds());
        using var cmd = ReadCmd("SELECT day_ts, count FROM agg_day WHERE day_ts BETWEEN $a AND $b");
        if (cmd is null) return (daily, start, end);
        cmd.Parameters.AddWithValue("$a", since);
        cmd.Parameters.AddWithValue("$b", MaxMs);
        using var r = cmd.ExecuteReader();
        while (r.Read())
        {
            var local = DateTimeOffset.FromUnixTimeMilliseconds(r.GetInt64(0)).LocalDateTime.Date;
            var delta = (local - start).Days;
            if (delta < 0 || delta >= daily.Length) continue;
            daily[delta] += r.GetInt64(1);
        }
        return (daily, start, end);
    }

    public static List<(long DayTs, long Count)> DailyCounts(int days = 30)
    {
        var rows = new List<(long, long)>();
        if (!Ready) return rows;
        var end = DateTime.Today;
        var start = end.AddDays(-(days - 1));
        var since = Math.Max(MinMs, new DateTimeOffset(start).ToUnixTimeMilliseconds());
        using var cmd = ReadCmd("SELECT day_ts, count FROM agg_day WHERE day_ts BETWEEN $a AND $b ORDER BY day_ts");
        if (cmd is null) return rows;
        cmd.Parameters.AddWithValue("$a", since);
        cmd.Parameters.AddWithValue("$b", MaxMs);
        using var r = cmd.ExecuteReader();
        while (r.Read()) rows.Add((r.GetInt64(0), r.GetInt64(1)));
        return rows;
    }

    /// 连续记录天数:今天还没动静时从昨天起算(否则每天早上都归零)。
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
        if (byDay.GetValueOrDefault(cursor) <= 0) cursor = cursor.AddDays(-1);
        var streak = 0;
        while (byDay.GetValueOrDefault(cursor) > 0)
        {
            streak++;
            cursor = cursor.AddDays(-1);
        }
        return streak;
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
        using var cmd = ReadCmd("SELECT hour_ts, count FROM agg_hour WHERE hour_ts BETWEEN $a AND $b ORDER BY hour_ts");
        if (cmd is null) return rows;
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
        using var cmd = ReadCmd("SELECT button, count FROM agg_mouse_button_total ORDER BY count DESC");
        if (cmd is null) return rows;
        using var r = cmd.ExecuteReader();
        while (r.Read()) rows.Add((r.GetString(0), r.GetInt64(1)));
        return rows;
    }

    public static List<(string Type, long Count)> KeyTypeDistribution()
    {
        var rows = new List<(string, long)>();
        if (!Ready) return rows;
        using var cmd = ReadCmd("SELECT type, count FROM agg_key_type_total ORDER BY count DESC");
        if (cmd is null) return rows;
        using var r = cmd.ExecuteReader();
        while (r.Read()) rows.Add((r.GetString(0), r.GetInt64(1)));
        return rows;
    }
}
