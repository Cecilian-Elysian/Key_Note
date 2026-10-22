using System.Diagnostics;
using KeyNote.Core.Utils;

namespace KeyNote.App.Services;

/// 应用内下载 + 静默升级:下载安装包 → 校验大小 → 拉起安装器(自动替换并重启)。
public static class UpdateInstaller
{
    /// 安装包临时文件名(按版本区分,便于识别与清理)
    public static string TempPath(string version)
        => Path.Combine(Path.GetTempPath(), $"KeyNote_Setup_{version}.exe");

    /// 下载安装包到临时目录,带进度回调。返回文件路径。
    public static async Task<string> DownloadAsync(UpdateService.UpdateInfo info, Action<int, long, long>? onProgress,
        CancellationToken token = default)
    {
        if (string.IsNullOrEmpty(info.AssetUrl)) throw new InvalidOperationException("该版本没有可下载的安装包");
        var path = TempPath(info.Latest?.ToString(3) ?? "unknown");
        await UpdateService.DownloadAsync(info.AssetUrl, path, onProgress, token).ConfigureAwait(false);

        // 大小校验:与 GitHub API 报的资产大小一致才算完整
        if (info.AssetSize > 0)
        {
            var actual = new FileInfo(path).Length;
            if (actual != info.AssetSize)
            {
                TryDelete(path);
                throw new IOException($"下载文件大小不符(期望 {info.AssetSize:N0} 字节,实际 {actual:N0} 字节)");
            }
        }
        return path;
    }

    /// 拉起安装器静默升级:安装器会用 Restart Manager 关掉正在运行的我们并替换文件,装完自动重启。
    public static void LaunchInstaller(string installerPath)
    {
        var psi = new ProcessStartInfo(installerPath)
        {
            UseShellExecute = true,
            Arguments = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART",
        };
        Process.Start(psi);
    }

    /// 清理旧的临时安装包
    public static void CleanupOldFiles(string keepVersion)
    {
        try
        {
            foreach (var file in Directory.EnumerateFiles(Path.GetTempPath(), "KeyNote_Setup_*.exe"))
            {
                if (file.Contains(keepVersion, StringComparison.OrdinalIgnoreCase)) continue;
                TryDelete(file);
            }
        }
        catch (Exception ex)
        {
            CrashLog.Write("update.cleanup", ex);
        }
    }

    private static void TryDelete(string path)
    {
        try
        {
            if (File.Exists(path)) File.Delete(path);
        }
        catch
        {
            // 临时文件删不掉不影响主流程
        }
    }
}
