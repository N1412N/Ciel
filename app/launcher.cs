using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

class Program
{
    [STAThread]
    static void Main()
    {
        string baseDir = AppContext.BaseDirectory;
        string appDir = File.Exists(Path.Combine(baseDir, "launch_desktop.py"))
            ? baseDir
            : Path.Combine(baseDir, "app");
        string entryPoint = Path.Combine(appDir, "launch_desktop.py");

        if (!File.Exists(entryPoint))
        {
            ShowError("Ciel could not find launch_desktop.py. Reinstall or repair the Ciel app folder.");
            return;
        }

        string python = FindOnPath("pythonw.exe") ?? FindOnPath("python.exe");
        if (python == null)
        {
            ShowError("Python 3.10 or newer is required to run Ciel. Install Python, add it to PATH, then run Ciel again.");
            return;
        }

        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = python,
                Arguments = "\"" + entryPoint + "\"",
                WorkingDirectory = appDir,
                WindowStyle = ProcessWindowStyle.Hidden,
                CreateNoWindow = true,
                UseShellExecute = false
            });
        }
        catch (Exception ex)
        {
            ShowError("Ciel could not start Python.\n\n" + ex.Message);
        }
    }

    static string FindOnPath(string executable)
    {
        string path = Environment.GetEnvironmentVariable("PATH") ?? string.Empty;
        foreach (string directory in path.Split(Path.PathSeparator))
        {
            if (string.IsNullOrWhiteSpace(directory)) continue;
            string candidate = Path.Combine(directory.Trim(), executable);
            if (File.Exists(candidate)) return candidate;
        }
        return null;
    }

    static void ShowError(string message)
    {
        MessageBox.Show(message, "Ciel startup error", MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}
