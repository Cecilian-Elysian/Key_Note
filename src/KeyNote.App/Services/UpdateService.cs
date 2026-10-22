using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Reflection;
using System.Text.Json;
using KeyNote.Core.Utils;

namespace KeyNote.App.Services;

/// 应用内更新检查:拉 GitHub Releases API,比对最新稳定版与当前程序集版本。
/// 不引入更新框架依赖(不用 Squirrel/Velopack):命中新版可应用内下载安装包并静默升级。
public static class UpdateService
{
    /// 检查结果:HasUpdate 为真时 Latest/TagName/ReleaseUrl/AssetUrl 有效。
    /// Ok = 检查本身是否成功(失败不写每日时间戳,避免网络抖动被 24h 静默窗吞掉)。
    public sealed record UpdateInfo(
        Version Current,
        Version? Latest,
        string TagName,
        string ReleaseUrl,
        string AssetUrl,
        bool HasUpdate,
        string Message,
        bool Ok = true)
    {
        /// 更新说明(Release body),空则不展示
        public string Notes { get; init; } = "";

        /// 安装包字节数(下载后校验),0 表示未知
        public long AssetSize { get; init; }
    }

    /// 列表端点:空仓库返回 [] 。
    /// 不用 /releases/latest —— 仓库一个 Release 都没有时它返回 404,会被误报成「检查失败」。
    private const string ApiUrl = "https://api.github.com/repos/Cecilian-Elysian/Key_Note/releases";
    private const string RepoUrl = "https://github.com/Cecilian-Elysian/Key_Note/releases";
    private const string AssetName = "KeyNote_Setup.exe";

    private static readonly HttpClient Http = CreateClient();

    /// 当前程序集版本(1.0.0.0 → 显示 1.0.0)。
    public static Version CurrentVersion { get; } =
        Assembly.GetExecutingAssembly().GetName().Version ?? new Version(0, 0, 0, 0);

    /// 当前版本显示文本,如 "1.0.0"。
    public static string CurrentVersionText => CurrentVersion.ToString(3);

    /// 更新源名称(当前只有 GitHub;保留以便将来加镜像时透出给用户)
    public const string SourceName = "GitHub";

    /// 最近一次检查结果(供设置页回填)。
    public static UpdateInfo? LastResult { get; private set; }

    /// 检查完成事件(后台线程触发,订阅方需自行切回 UI 线程)。
    public static event Action<UpdateInfo>? Completed;

    /// 状态文案(关于页 / 托盘 / 日志共享同一份真相)
    public static string StatusMessage { get; private set; } = "尚未检查更新";

    /// 状态变化事件
    public static event Action<string>? StatusChanged;

    /// 当前运行副本是否由安装器安装(便携版无法自动替换自己)
    public static bool IsInstalled => File.Exists(Path.Combine(AppDir, "unins000.exe"));

    /// 应用所在目录
    public static string AppDir { get; } = Path.GetDirectoryName(
        Assembly.GetExecutingAssembly().Location) ?? AppContext.BaseDirectory;

    // ──── 检查入口 ────
    public static async Task<UpdateInfo> CheckAsync(string? endpoint = null)
    {
        var current = CurrentVersion;
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(10));
            using var request = new HttpRequestMessage(HttpMethod.Get, endpoint ?? ApiUrl);
            request.Headers.UserAgent.Add(new ProductInfoHeaderValue("KeyNote", CurrentVersionText));
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/vnd.github+json"));

            using var response = await Http.SendAsync(request, cts.Token).ConfigureAwait(false);

            if (response.StatusCode == HttpStatusCode.NotFound)
            {
                return Publish(Fail(current, "仓库暂无发布,当前已是最新"));
            }
            if (response.StatusCode == HttpStatusCode.Forbidden && IsRateLimited(response))
            {
                return Publish(Fail(current, "GitHub 请求限流,请稍后再试"));
            }
            if (!response.IsSuccessStatusCode)
            {
                return Publish(Fail(current, $"检查失败(HTTP {(int)response.StatusCode})"));
            }

            var json = await response.Content.ReadAsStringAsync(cts.Token).ConfigureAwait(false);
            return Publish(Parse(json, current));
        }
        catch (TaskCanceledException)
        {
            return Publish(Fail(current, "检查超时"));
        }
        catch (HttpRequestException ex)
        {
            CrashLog.Write("update.check", ex);
            return Publish(Fail(current, "网络不可用,检查失败"));
        }
        catch (Exception ex)
        {
            CrashLog.Write("update.check", ex);
            return Publish(Fail(current, "检查失败"));
        }
    }

    private static UpdateInfo Fail(Version current, string message)
        => new(current, null, string.Empty, RepoUrl, string.Empty, false, message, Ok: false);

    // ──── 解析与比较 ────
    /// 解析 releases 列表:滤掉 draft/prerelease,在稳定版里挑版本号最高的。
    internal static UpdateInfo Parse(string json, Version current)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;

        if (root.ValueKind != JsonValueKind.Array)
        {
            // 兼容单对象(/releases/latest 的返回形态)
            return ParseSingle(root, current);
        }

        UpdateInfo? best = null;
        Version? bestVersion = null;
        foreach (var item in root.EnumerateArray())
        {
            if (Bool(item, "draft") || Bool(item, "prerelease")) continue;
            var tag = Str(item, "tag_name");
            var version = ParseVersion(tag);
            if (version is null) continue;
            if (bestVersion is not null && !IsNewer(version, bestVersion)) continue;
            bestVersion = version;
            best = BuildInfo(current, item, tag, version);
        }

        if (best is null)
        {
            return new UpdateInfo(current, null, string.Empty, RepoUrl, string.Empty, false,
                "仓库暂无发布,当前已是最新");
        }
        if (!best.HasUpdate)
        {
            return best with { Message = $"已是最新(v{best.Latest?.ToString(3)})" };
        }
        return best;
    }

    private static UpdateInfo ParseSingle(JsonElement item, Version current)
    {
        var tag = Str(item, "tag_name");
        var version = ParseVersion(tag);
        if (version is null)
        {
            return new UpdateInfo(current, null, tag, Str(item, "html_url"), string.Empty, false,
                string.IsNullOrEmpty(tag) ? "无法读取版本号" : $"无法解析版本号:{tag}");
        }
        return BuildInfo(current, item, tag, version);
    }

    private static UpdateInfo BuildInfo(Version current, JsonElement item, string tag, Version version)
    {
        var html = Str(item, "html_url");
        if (string.IsNullOrEmpty(html)) html = RepoUrl;
        var (asset, size) = FindAsset(item);
        var notes = Str(item, "body");

        if (!IsNewer(version, current))
        {
            return new UpdateInfo(current, version, tag, html, asset, false,
                $"已是最新(v{version.ToString(3)})") { Notes = notes, AssetSize = size };
        }
        return new UpdateInfo(current, version, tag, html, asset, true,
            $"发现新版本 v{version.ToString(3)}") { Notes = notes, AssetSize = size };
    }

    /// tag → 版本:剥 v 前缀、切掉 semver 后缀(v1.0.0-rc2 → 1.0.0)。
    private static Version? ParseVersion(string tag)
    {
        var text = tag.Trim();
        if (text.StartsWith('v') || text.StartsWith('V')) text = text[1..];
        var cut = text.IndexOfAny(['-', '+', ' ']);
        if (cut > 0) text = text[..cut];
        return Version.TryParse(text, out var version) ? version : null;
    }

    /// 组件式比较:Version(1,0,0) < Version(1,0,0,0) 在 .NET 中成立,直接 CompareTo 会误报。
    private static bool IsNewer(Version latest, Version current)
    {
        var (lm, ln, lb) = Parts(latest);
        var (cm, cn, cb) = Parts(current);
        if (lm != cm) return lm > cm;
        if (ln != cn) return ln > cn;
        return lb > cb;
    }

    private static (int Major, int Minor, int Build) Parts(Version v)
        => (v.Major, v.Minor, v.Build < 0 ? 0 : v.Build);

    private static string Str(JsonElement root, string name)
        => root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? string.Empty
            : string.Empty;

    private static bool Bool(JsonElement root, string name)
        => root.TryGetProperty(name, out var value)
            && (value.ValueKind == JsonValueKind.True || value.ValueKind == JsonValueKind.String && value.GetString() == "true");

    /// 找安装包资产(优先 KeyNote_Setup.exe),同时取其字节数用于下载后校验。
    private static (string Url, long Size) FindAsset(JsonElement root)
    {
        if (!root.TryGetProperty("assets", out var assets) || assets.ValueKind != JsonValueKind.Array) return ("", 0);
        (string Url, long Size) fallback = ("", 0);
        foreach (var item in assets.EnumerateArray())
        {
            var name = Str(item, "name");
            var url = Str(item, "browser_download_url");
            if (url.Length == 0) continue;
            var size = item.TryGetProperty("size", out var sz) && sz.ValueKind == JsonValueKind.Number
                ? sz.GetInt64() : 0L;
            if (name.Equals(AssetName, StringComparison.OrdinalIgnoreCase)) return (url, size);
            if (fallback.Url.Length == 0 && name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) fallback = (url, size);
        }
        return fallback;
    }

    private static bool IsRateLimited(HttpResponseMessage response)
    {
        if (!response.Headers.TryGetValues("X-RateLimit-Remaining", out var values)) return false;
        foreach (var value in values)
        {
            if (value == "0") return true;
        }
        return false;
    }

    private static UpdateInfo Publish(UpdateInfo info)
    {
        LastResult = info;
        SetStatus(info.HasUpdate ? info.Message : info.Message);
        Completed?.Invoke(info);
        return info;
    }

    /// 设置状态文案(关于页 / 托盘 / 日志共享同一份真相)
    public static void SetStatus(string message)
    {
        if (StatusMessage == message) return;
        StatusMessage = message;
        StatusChanged?.Invoke(message);
    }

    /// 用系统浏览器打开 Release 页(未安装副本 / 下载失败时的兜底)。
    public static bool OpenReleasePage(string url)
    {
        if (string.IsNullOrWhiteSpace(url)) return false;
        if (!url.StartsWith("https://github.com/", StringComparison.OrdinalIgnoreCase)) return false;
        try
        {
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            return true;
        }
        catch (Exception ex)
        {
            CrashLog.Write("update.open", ex);
            return false;
        }
    }

    /// 下载安装包到指定路径(流式,带进度回调)。
    public static async Task DownloadAsync(string url, string path,
        Action<int, long, long>? onProgress, CancellationToken token = default)
    {
        using var response = await Http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, token).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();

        var total = response.Content.Headers.ContentLength ?? 0;
        await using var input = await response.Content.ReadAsStreamAsync(token).ConfigureAwait(false);
        await using var output = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.None, 81920, useAsync: true);

        var buffer = new byte[81920];
        long read = 0;
        var lastPercent = -1;
        while (true)
        {
            var n = await input.ReadAsync(buffer, token).ConfigureAwait(false);
            if (n <= 0) break;
            await output.WriteAsync(buffer.AsMemory(0, n), token).ConfigureAwait(false);
            read += n;
            var percent = total > 0 ? (int)(read * 100 / total) : 0;
            if (percent != lastPercent)
            {
                lastPercent = percent;
                onProgress?.Invoke(percent, read, total);
            }
        }
        await output.FlushAsync(token).ConfigureAwait(false);
    }

    private static HttpClient CreateClient()
    {
        var client = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/vnd.github+json"));
        return client;
    }
}
