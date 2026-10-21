using KeyNote.App.Services;
using KeyNote.Core.Storage;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace KeyNote.App.Views;

/// 设置页动作:更新检查结果落地 + 备份/VACUUM/CSV 分发。
public sealed partial class SettingsPage
{
    private Border BuildUpdateRow()
    {
        var text = new TextBlock
        {
            FontSize = 12,
            Foreground = new SolidColorBrush(Theme.UiColors.Warning),
            VerticalAlignment = VerticalAlignment.Center,
        };
        var open = new Button { Content = "打开下载页" };
        open.Click += (_, _) =>
        {
            if (UpdateService.LastResult is not { } info) return;
            StatusText.Text = UpdateService.OpenReleasePage(info.ReleaseUrl) ? "已打开下载页" : "打开浏览器失败";
        };
        var panel = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
        panel.Children.Add(text);
        panel.Children.Add(open);

        _updateText = text;
        _updateRow = new Border
        {
            Padding = new Thickness(14, 10, 14, 10),
            Visibility = Visibility.Collapsed,
            Child = panel,
        };
        return _updateRow;
    }

    /// 检查结果落地:状态栏文案 + 新版提示行显隐。
    private void ApplyUpdateResult(UpdateService.UpdateInfo info)
    {
        StatusText.Text = info.Message;
        if (_updateText is not null && info.HasUpdate && info.Latest is not null)
        {
            _updateText.Text = $"发现新版本 v{info.Latest.ToString(3)},可在 Release 页下载安装包";
        }
        if (_updateRow is not null)
        {
            _updateRow.Visibility = info.HasUpdate ? Visibility.Visible : Visibility.Collapsed;
        }
    }

    /// 检查完成回调(后台线程触发 → 切回 UI 线程)。
    private void OnUpdateCompleted(UpdateService.UpdateInfo info)
    {
        DispatcherQueue.TryEnqueue(() => ApplyUpdateResult(info));
    }

    private async void RunAction(string action)
    {
        try
        {
            switch (action)
            {
                case "backup":
                {
                    var path = KeyNoteDb.Backup(_cfg);
                    StatusText.Text = path is null ? "备份失败" : $"已备份:{Path.GetFileName(path)}";
                    break;
                }
                case "vacuum":
                    StatusText.Text = KeyNoteDb.Vacuum() ? "VACUUM 完成" : "VACUUM 失败";
                    break;
                case "csv":
                {
                    var dir = Core.Utils.AppPaths.DataDir();
                    var file = Path.Combine(dir, $"keynote-export-{DateTime.Now:yyyyMMdd-HHmmss}.csv");
                    var rows = KeyNoteDb.ExportCsv(file, 30);
                    StatusText.Text = $"已导出 {rows:N0} 行 → {Path.GetFileName(file)}";
                    break;
                }
                case "update":
                {
                    StatusText.Text = "正在检查更新…";
                    var info = await UpdateService.CheckAsync();
                    ApplyUpdateResult(info);
                    break;
                }
            }
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("settings.action", ex);
            StatusText.Text = "操作失败";
        }
    }

}
