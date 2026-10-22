using KeyNote.Core.Utils;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace KeyNote.App.Services;

/// 更新提示对话框:确认框(版本对比 + 更新说明)与下载进度框。
public static class UpdatePrompt
{
    /// 弹确认框。true = 用户选择「下载并安装」。
    public static async Task<bool> ShowAsync(UpdateService.UpdateInfo info, XamlRoot? root, string closeText = "稍后")
    {
        if (root is null) return false;

        var panel = new StackPanel { Spacing = 12 };
        panel.Children.Add(new TextBlock
        {
            Text = $"当前 {info.Current.ToString(3)} → 最新 {info.Latest?.ToString(3)}",
            FontSize = 13,
            Foreground = MutedBrush(),
            TextWrapping = TextWrapping.Wrap,
        });

        if (!string.IsNullOrWhiteSpace(info.Notes))
        {
            panel.Children.Add(new TextBlock
            {
                Text = "更新内容",
                FontSize = 12,
                Foreground = MutedBrush(),
                Margin = new Thickness(0, 4, 0, 0),
            });
            panel.Children.Add(BuildNotes(info.Notes));
        }

        panel.Children.Add(new TextBlock
        {
            Text = UpdateService.IsInstalled
                ? "安装完成后应用会自动重启(安装包未签名,Windows 可能弹出安全提示)"
                : "当前是便携版运行副本,无法自动安装更新,建议手动下载",
            FontSize = 12,
            Foreground = MutedBrush(),
            TextWrapping = TextWrapping.Wrap,
        });

        var dialog = new ContentDialog
        {
            Title = $"发现新版本 {info.Latest?.ToString(3)}",
            Content = panel,
            PrimaryButtonText = UpdateService.IsInstalled ? "下载并安装" : "打开下载页",
            CloseButtonText = closeText,
            DefaultButton = ContentDialogButton.Primary,
            XamlRoot = root,
        };
        return await dialog.ShowAsync() == ContentDialogResult.Primary;
    }

    /// 下载进度框:状态文字 + 进度条,下载中不允许关闭。
    public static async Task<bool> RunDownloadAsync(UpdateService.UpdateInfo info, XamlRoot? root,
        Func<Action<int, long, long>, Task> download, Action<string> status)
    {
        if (root is null) return false;

        var statusText = new TextBlock
        {
            Text = "正在准备下载…",
            FontSize = 12,
            Foreground = MutedBrush(),
            TextWrapping = TextWrapping.Wrap,
        };
        var bar = new ProgressBar
        {
            Height = 8,
            IsIndeterminate = true,
            Minimum = 0,
            Maximum = 100,
        };
        var panel = new StackPanel { Spacing = 10 };
        panel.Children.Add(statusText);
        panel.Children.Add(bar);

        var allowClose = false;
        var dialog = new ContentDialog
        {
            Title = $"正在下载版本 {info.Latest?.ToString(3)}",
            Content = panel,
            CloseButtonText = "取消",
            XamlRoot = root,
        };
        dialog.Closing += (_, e) =>
        {
            if (!allowClose) e.Cancel = true;
        };

        var showTask = dialog.ShowAsync().AsTask();
        try
        {
            await download((percent, read, total) =>
            {
                bar.IsIndeterminate = false;
                bar.Value = Math.Clamp(percent, 0, 100);
                var text = total > 0
                    ? $"正在下载 {read / 1024.0 / 1024.0:F1} / {total / 1024.0 / 1024.0:F1} MB({percent}%)"
                    : $"正在下载 {read / 1024.0 / 1024.0:F1} MB";
                statusText.Text = text;
                status(text);
            }).ConfigureAwait(true);
        }
        catch (Exception ex)
        {
            allowClose = true;
            dialog.Hide();
            CrashLog.Write("update.download", ex);
            return false;
        }
        allowClose = true;
        dialog.Hide();
        return true;
    }

    private static FrameworkElement BuildNotes(string notes)
    {
        var text = new TextBlock
        {
            Text = notes.Trim(),
            FontSize = 12,
            TextWrapping = TextWrapping.Wrap,
            IsTextSelectionEnabled = true,
        };
        var scroll = new ScrollViewer
        {
            MaxHeight = 240,
            Content = text,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
        };
        return scroll;
    }

    private static SolidColorBrush MutedBrush()
    {
        if (Application.Current?.Resources.TryGetValue("TextFillColorSecondaryBrush", out var res) == true
            && res is SolidColorBrush brush)
        {
            return brush;
        }
        return new SolidColorBrush(Windows.UI.Color.FromArgb(0xFF, 0xC5, 0xC5, 0xC5));
    }
}
