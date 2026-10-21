using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Reflection;
using System.Text.Json;
using KeyNote.Core.Utils;

namespace KeyNote.App.Services;

/// 应用内更新检查:拉 GitHub Releases API,比对最新 tag 与当前程序集版本。
/// 不引入更新框架依赖(不用 Squirrel/Velopack),命中新版只给出 Release 页链接,由系统浏览器下载。
public static class UpdateService
{
    /// 检查结果:HasUpdate 为真时 Latest/TagName/ReleaseUrl 有效。
    public sealed record UpdateInfo(
        Version Current,
        Version? Latest,
        string TagName,
        string ReleaseUrl,
        string AssetUrl,
        bool HasUpdate,
        string Message);

    private const string ApiUrl = "https://api.github.com/repos/Cecilian-Elysian/Key_Note/releases/latest";
    private const string RepoUrl = "https://github.com/Cecilian-Elysian/Key_Note/releases";

    private static readonly HttpClient Http = CreateClient();

    /// 当前程序集版本(1.0.0.0 → 显示 1.0.0)。
    public static Version CurrentVersion { get; } =
        Assembly.GetExecutingAssembly().GetName().Version ?? new Version(0, 0, 0, 0);

    /// 当前版本显示文本,如 "1.0.0"。
    public static string CurrentVersionText => CurrentVersion.ToString(3);

    /// 最近一次检查结果(供设置页回填)。
    public static UpdateInfo? LastResult { get; private set; }

    /// 检查完成事件(后台线程触发,订阅方需自行切回 UI 线程)。
    public static event Action<UpdateInfo>? Completed;

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
                return Publish(new UpdateInfo(current, null, string.Empty, RepoUrl, string.Empty, false, "仓库暂无发布,当前已是最新"));
            }
            if (response.StatusCode == HttpStatusCode.Forbidden && IsRateLimited(response))
            {
                return Publish(new UpdateInfo(current, null, string.Empty, RepoUrl, string.Empty, false, "GitHub 请求限流,请稍后再试"));
            }
            if (!response.IsSuccessStatusCode)
            {
                return Publish(new UpdateInfo(current, null, string.Empty, RepoUrl, string.Empty, false, $"检查失败(HTTP {(int)response.StatusCode})"));
            }

            var json = await response.Content.ReadAsStringAsync(cts.Token).ConfigureAwait(false);
            return Publish(Parse(json, current));
        }
        catch (TaskCanceledException)
        {
            return Publish(new UpdateInfo(current, null, string.Empty, RepoUrl, string.Empty, false, "检查超时"));
        }
        catch (HttpRequestException ex)
        {
            CrashLog.Write("update.check", ex);
            return Publish(new UpdateInfo(current, null, string.Empty, RepoUrl, string.Empty, false, "网络不可用,检查失败"));
        }
        catch (Exception ex)
        {
            CrashLog.Write("update.check", ex);
            return Publish(new UpdateInfo(current, null, string.Empty, RepoUrl, string.Empty, false, "检查失败"));
        }
    }

    /// 用系统浏览器打开 Release 页(有新版时由用户自行下载安装包)。
    public static bool OpenReleasePage(string url)
    {
        if (string.IsNullOrWhiteSpace(url)) return false;
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

    // ──── 解析与比较 ────
    internal static UpdateInfo Parse(string json, Version current)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;

        var tag = Str(root, "tag_name");
        var html = Str(root, "html_url");
        if (string.IsNullOrEmpty(html)) html = RepoUrl;
        var asset = FindAsset(root);

        var latest = ParseVersion(tag);
        if (latest is null)
        {
            return new UpdateInfo(current, null, tag, html, asset, false,
                string.IsNullOrEmpty(tag) ? "无法读取版本号" : $"无法解析版本号:{tag}");
        }
        if (!IsNewer(latest, current))
        {
            return new UpdateInfo(current, latest, tag, html, asset, false,
                $"已是最新(v{latest.ToString(3)})");
        }
        return new UpdateInfo(current, latest, tag, html, asset, true,
            $"发现新版本 v{latest.ToString(3)}");
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

    /// 找安装包资产(优先 KeyNote_Setup.exe)。
    private static string FindAsset(JsonElement root)
    {
        if (!root.TryGetProperty("assets", out var assets) || assets.ValueKind != JsonValueKind.Array) return string.Empty;
        var fallback = string.Empty;
        foreach (var item in assets.EnumerateArray())
        {
            var name = Str(item, "name");
            var url = Str(item, "browser_download_url");
            if (url.Length == 0) continue;
            if (name.Equals("KeyNote_Setup.exe", StringComparison.OrdinalIgnoreCase)) return url;
            if (fallback.Length == 0 && name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) fallback = url;
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
        Completed?.Invoke(info);
        return info;
    }

    private static HttpClient CreateClient()
    {
        var client = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/vnd.github+json"));
        return client;
    }
}
