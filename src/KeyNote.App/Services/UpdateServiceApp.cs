using KeyNote.Core.Storage;
using KeyNote.Core.Utils;
using Microsoft.UI.Xaml;

namespace KeyNote.App.Services;

/// 更新安装流程:应用内下载 → 校验 → 拉起安装器(自动替换 + 重启)。
/// 设置页与托盘气泡路径共用。
public static class UpdateServiceApp
{
    /// 执行更新安装。返回 true = 已拉起安装器(应用即将退出)。
    public static async Task<bool> InstallAsync(UpdateService.UpdateInfo info, XamlRoot? root)
    {
        if (root is null) return false;

        if (!UpdateService.IsInstalled)
        {
            // 便携版运行副本:没有安装器可替换自己,只能给用户打开下载页
            UpdateService.SetStatus("便携版运行副本无法自动安装,已打开下载页");
            UpdateService.OpenReleasePage(info.ReleaseUrl);
            return false;
        }

        var version = info.Latest?.ToString(3) ?? "unknown";
        try
        {
            UpdateInstaller.CleanupOldFiles(version);
            var ok = await UpdatePrompt.RunDownloadAsync(info, root,
                progress => UpdateInstaller.DownloadAsync(info, progress),
                text => UpdateService.SetStatus(text));
            if (!ok)
            {
                UpdateService.SetStatus("下载失败,已打开下载页");
                UpdateService.OpenReleasePage(info.ReleaseUrl);
                return false;
            }

            var path = UpdateInstaller.TempPath(version);
            UpdateService.SetStatus("正在安装更新…");
            // 先把待写队列排空:安装器会用 Restart Manager 强制关进程,不能丢最后一批按键
            KeyNoteDb.Flush();
            UpdateInstaller.LaunchInstaller(path);
            return true;
        }
        catch (Exception ex)
        {
            CrashLog.Write("app.update.install", ex);
            UpdateService.SetStatus($"更新失败:{ex.Message}");
            UpdateService.OpenReleasePage(info.ReleaseUrl);
            return false;
        }
    }
}
