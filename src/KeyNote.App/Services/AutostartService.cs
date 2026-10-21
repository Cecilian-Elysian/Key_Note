using Microsoft.Win32;

namespace KeyNote.App.Services;

/// 开机自启:HKCU\Software\Microsoft\Windows\CurrentVersion\Run(对齐 Python tray.py)。
public static class AutostartService
{
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string ValueName = "KeyNote";

    public static void SetEnabled(bool enabled)
    {
        try
        {
            using var key = Registry.CurrentUser.CreateSubKey(RunKey, writable: true);
            if (key is null) return;
            if (enabled)
            {
                var exe = Environment.ProcessPath ?? "KeyNote.exe";
                key.SetValue(ValueName, $"\"{exe}\" --minimized", RegistryValueKind.String);
            }
            else
            {
                if (key.GetValue(ValueName) is not null) key.DeleteValue(ValueName, throwOnMissingValue: false);
            }
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("autostart", ex);
        }
    }
}
