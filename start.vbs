' 静默启动 — 无 CMD 弹窗，完全后台运行
' 双击此文件即可启动 apiKeyConfig 服务
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
WshShell.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)

On Error Resume Next
WshShell.Run "pythonw.exe app.py --no-browser", 0, False
If Err.Number <> 0 Then
    WshShell.Run "python.exe app.py --no-browser", 0, False
End If
