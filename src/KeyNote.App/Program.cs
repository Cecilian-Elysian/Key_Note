using System;

namespace KeyNote.App;

/// 程序入口(DISABLE_XAML_GENERATED_MAIN):先做单实例/静默参数,再起 XAML。
public static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        global::WinRT.ComWrappersSupport.InitializeComWrappers();
        Microsoft.UI.Xaml.Application.Start(_ =>
        {
            var app = new App();
            app.OnArgs(args);
        });
    }
}
