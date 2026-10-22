using System.Collections.Concurrent;
using System.Globalization;
using System.Text;
using KeyNote.Core.Settings;
using KeyNote.Core.Utils;
using Microsoft.Data.Sqlite;

namespace KeyNote.Core.Storage;

/// 写入队列与后台 writer 线程:批量落盘 + 聚合表 upsert + 保留期清理。
public static partial class KeyNoteDb
{

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
            Interlocked.Exchange(ref _writeFailures, 0);
        }
        catch (Exception ex)
        {
            CrashLog.Write("db.write", ex);
            // 落盘失败:整批重新入队(有界重试),否则这批数据(最多 200 条)会静默消失
            RequeueBatch(batch);
        }
    }

    /// 失败批次回队;连续失败超过上限则计入丢弃计数(供 Health() 暴露)。
    private static void RequeueBatch(List<WriteItem> batch)
    {
        if (_queue is null || _shutdown) return;
        if (Interlocked.Increment(ref _writeFailures) > MaxWriteFailures)
        {
            Interlocked.Add(ref _droppedEvents, batch.Count);
            return;
        }
        foreach (var item in batch)
        {
            if (!_queue.TryAdd(item)) Interlocked.Increment(ref _droppedEvents);
        }
    }

    /// 落盘连续失败次数(成功一次即清零)。
    private static int _writeFailures;
    private static long _droppedEvents;
    private const int MaxWriteFailures = 5;

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
}
