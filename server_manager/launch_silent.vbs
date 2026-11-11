Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\Admin\Desktop\BTLMMT\server_manager"
WshShell.Run """C:\Users\Admin\AppData\Local\Programs\Python\Python312\pythonw.exe"" ""C:\Users\Admin\Desktop\BTLMMT\server_manager\scada_daemon.py""", 0, False
