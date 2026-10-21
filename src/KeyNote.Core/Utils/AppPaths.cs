namespace KeyNote.Core.Utils;

/// 数据目录定位:portable.flag 在 exe 旁 → 便携模式(exe 目录),否则 %LOCALAPPDATA%\KeyNote。
public static class AppPaths
{
    private const string AppSubdir = "KeyNote";

    public static string ExeDir
    {
        get
        {
            var exe = System.Reflection.Assembly.GetEntryAssembly()?.Location;
            return string.IsNullOrEmpty(exe) ? AppContext.BaseDirectory : Path.GetDirectoryName(exe)!;
        }
    }

    public static string DataDir()
    {
        var portableFlag = Path.Combine(ExeDir, "portable.flag");
        if (File.Exists(portableFlag)) return ExeDir;
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        if (string.IsNullOrEmpty(local)) local = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "AppData", "Local");
        var dir = Path.Combine(local, AppSubdir);
        Directory.CreateDirectory(dir);
        return dir;
    }

    /// 崩溃日志路径(固定在默认数据目录,不跟随 data_dir)
    public static string CrashLogPath => Path.Combine(DataDir(), "keynote.crash.log");
}
