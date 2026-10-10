Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\Lenovo\OneDrive\Documents\Ciel"
WshShell.Run "pythonw launch_desktop.py", 0, False
