using System.Collections.Concurrent;
using System.Globalization;
using System.Text;
using KeyNote.Core.Settings;
using KeyNote.Core.Utils;
using Microsoft.Data.Sqlite;

namespace KeyNote.Core.Storage;

/// 备份/导出/VACUUM/健康检查与关闭收尾。
public static partial class KeyNoteDb
{

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
                _conn!.BackupDatabase(bck);
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
        using var cmd = ReadCmd("SELECT ts, key, session_id FROM keypresses WHERE ts >= $c ORDER BY ts");
        if (cmd is null) return 0;
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
            w.WriteLine($"{Csv(iso)},{Csv(key)},{Csv(sid)}");
            count++;
        }
        return count;
    }

    /// CSV 字段转义(RFC 4180):含逗号/引号/换行的按键名必须加引号,内部引号翻倍。
    private static string Csv(string value)
    {
        if (value.Length == 0) return "\"\"";
        if (value.IndexOfAny([',', '"', '\n', '\r']) < 0) return value;
        return "\"" + value.Replace("\"", "\"\"") + "\"";
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
            info.DroppedEvents = Interlocked.Read(ref _droppedEvents);
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

    /// 落盘失败被丢弃的事件数(数据完整性可见,不再静默丢数)
    public long DroppedEvents { get; set; }
}
