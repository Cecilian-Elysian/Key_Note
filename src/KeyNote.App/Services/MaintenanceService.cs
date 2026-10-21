using KeyNote.Core.Settings;
using KeyNote.Core.Storage;

namespace KeyNote.App.Services;

/// 数据维护动作:备份 / VACUUM / CSV 导出。
/// 托盘菜单与设置页共用同一实现(此前两处各写一遍,文案还不一致)。
public static class MaintenanceService
{
    /// 立即备份,返回结果文案
    public static string Backup(AppSettings cfg)
    {
        var path = KeyNoteDb.Backup(cfg);
        return path is null ? "备份失败" : $"已备份:{Path.GetFileName(path)}";
    }

    /// 重建数据库回收空间,返回结果文案
    public static string Vacuum() => KeyNoteDb.Vacuum() ? "VACUUM 完成" : "VACUUM 失败";

    /// 导出最近 N 天原始按键记录,返回结果文案
    public static string ExportCsv(int days = 30)
    {
        var dir = Core.Utils.AppPaths.DataDir();
        var file = Path.Combine(dir, $"keynote-export-{DateTime.Now:yyyyMMdd-HHmmss}.csv");
        var rows = KeyNoteDb.ExportCsv(file, days);
        return $"已导出 {rows:N0} 行 → {Path.GetFileName(file)}";
    }
}
