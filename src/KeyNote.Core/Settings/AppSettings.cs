using System.Text.Json;
using System.Text.Json.Nodes;
using KeyNote.Core.Utils;

namespace KeyNote.Core.Settings;

/// config.json 持久化:字典模型保留未知键(与 Python 版互读),原子写(temp + flush + rename)。
public sealed class AppSettings
{
    private static readonly object Gate = new();
    private static readonly Dictionary<string, object?> Defaults = new()
    {
        ["auto_start"] = false,
        ["close_to_tray"] = true,
        ["start_minimized"] = false,
        ["listener_enabled"] = true,
        ["idle_pause_min"] = 0,
        ["font_family"] = "Microsoft YaHei UI",
        ["window_alpha"] = 1.0,
        ["remember_window_pos"] = true,
        ["_window_geometry"] = "",
        ["chart_auto_refresh"] = true,
        ["refresh_interval_sec"] = 5,
        ["heatmap_days"] = 365,
        ["db_retention_days"] = 365,
        ["db_auto_backup_days"] = 7,
        ["backup_keep_daily"] = 7,
        ["backup_keep_weekly"] = 4,
        ["db_flush_batch_size"] = 200,
        ["db_flush_interval_sec"] = 1.0,
        ["log_to_file"] = false,
        ["silent_start"] = false,
        ["hide_tray_icon"] = false,
        ["window_topmost"] = false,
        ["data_dir"] = "",
        ["mouse_listener_enabled"] = true,
        ["backup_dir"] = "",
    };

    public static string ConfigPath => Path.Combine(AppPaths.DataDir(), "config.json");

    private Dictionary<string, JsonNode> _data = new();

    private AppSettings() { }

    // ──── 加载/保存 ────
    public static AppSettings Load()
    {
        var s = new AppSettings();
        lock (Gate)
        {
            try
            {
                if (!File.Exists(ConfigPath))
                {
                    s = FromDefaults();
                    s.Save();
                    return s;
                }
                var node = JsonNode.Parse(File.ReadAllText(ConfigPath));
                var merged = FromDefaults();
                if (node is JsonObject obj)
                {
                    foreach (var (k, v) in obj)
                    {
                        if (v is not null) merged._data[k] = v.DeepClone();
                    }
                }
                return merged;
            }
            catch
            {
                return FromDefaults();
            }
        }
    }

    private static AppSettings FromDefaults()
    {
        var s = new AppSettings();
        foreach (var (k, v) in Defaults)
        {
            s._data[k] = JsonValue.Create(v);
        }
        return s;
    }

    public void Save()
    {
        lock (Gate)
        {
            try
            {
                var obj = new JsonObject();
                foreach (var (k, v) in _data) obj[k] = v.DeepClone();
                var dir = Path.GetDirectoryName(ConfigPath)!;
                Directory.CreateDirectory(dir);
                var tmp = ConfigPath + ".tmp";
                using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None))
                using (var w = new StreamWriter(fs))
                {
                    w.Write(obj.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
                    w.Flush();
                    fs.Flush(flushToDisk: true);
                }
                File.Move(tmp, ConfigPath, overwrite: true);
            }
            catch (Exception ex)
            {
                Utils.CrashLog.Write("config.save", ex);
            }
        }
    }

    // ──── 类型化取值(缺键回退默认) ────
    public bool GetBool(string key, bool def = false)
    {
        if (_data.TryGetValue(key, out var n) && n is JsonValue v && v.TryGetValue<bool>(out var b)) return b;
        return def;
    }

    public int GetInt(string key, int def = 0)
    {
        if (_data.TryGetValue(key, out var n) && n is JsonValue v)
        {
            if (v.TryGetValue<int>(out var i)) return i;
            if (v.TryGetValue<double>(out var d)) return (int)d;
        }
        return def;
    }

    public double GetDouble(string key, double def = 0)
    {
        if (_data.TryGetValue(key, out var n) && n is JsonValue v && v.TryGetValue<double>(out var d)) return d;
        return def;
    }

    public string GetString(string key, string def = "")
    {
        if (_data.TryGetValue(key, out var n) && n is JsonValue v && v.TryGetValue<string>(out var s)) return s;
        return def;
    }

    public void Set(string key, bool value) => _data[key] = JsonValue.Create(value);
    public void Set(string key, int value) => _data[key] = JsonValue.Create(value);
    public void Set(string key, double value) => _data[key] = JsonValue.Create(value);
    public void Set(string key, string value) => _data[key] = JsonValue.Create(value);

    // ──── 常用键糖衣 ────
    public bool ListenerEnabled => GetBool("listener_enabled", true);
    public bool MouseListenerEnabled => GetBool("mouse_listener_enabled", true);
    public int RetentionDays => GetInt("db_retention_days", 365);
    public int HeatmapDays => GetInt("heatmap_days", 365);
    public int RefreshIntervalSec => GetInt("refresh_interval_sec", 5);
    public bool ChartAutoRefresh => GetBool("chart_auto_refresh", true);
    public bool CloseToTray => GetBool("close_to_tray", true);
    public bool SilentStart => GetBool("silent_start", false);
    public bool StartMinimized => GetBool("start_minimized", false);
    public bool HideTrayIcon => GetBool("hide_tray_icon", false);
    public bool AutoStart => GetBool("auto_start", false);
}
