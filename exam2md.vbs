' exam2md - Launcher VBScript
' Salve como exam2md.vbs e clique duas vezes para iniciar
' Pode ser fixado na barra de tarefas / menu iniciar

Option Explicit

Dim objShell, objFSO, scriptPath, workingDir, pythonExe, apiScript

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Diretório onde este script está localizado
scriptPath = objFSO.GetParentFolderName(WScript.ScriptFullName)
workingDir = scriptPath

' Verifica se Python existe
Dim pythonExe
pythonExe = objShell.ExpandEnvironmentStrings("%USERPROFILE%") & "\AppData\Local\Programs\Python\Python312\python.exe"

If Not objFSO.FileExists(pythonExe) Then
    ' Tenta achar no PATH
    On Error Resume Next
    Dim wshExec, output
    Set wshExec = objShell.Exec("where python")
    output = wshExec.StdOut.ReadAll()
    On Error GoTo 0
    If Len(Trim(output)) > 0 Then
        pythonExe = Trim(Split(output, vbCrLf)(0))
    Else
        MsgBox "Python não encontrado!" & vbCrLf & _
               "Instale em: https://python.org/downloads" & vbCrLf & _
               "Marque 'Add Python to PATH' na instalação.", vbCritical, "exam2md - Erro"
        WScript.Quit 1
    End If
End If

' Verifica/cria venv
Dim venvPath, venvPython
venvPath = workingDir & "\.venv"
venvPython = venvPath & "\Scripts\python.exe"

If Not objFSO.FileExists(venvPython) Then
    If MsgBox("Primeira execução: criar ambiente virtual e instalar dependências?" & vbCrLf & _
              "Isso pode levar alguns minutos.", vbYesNo + vbQuestion, "exam2md - Primeira execução") = vbNo Then
        WScript.Quit 0
    End If
    
    Dim cmd
    cmd = "cmd /c cd /d " & workingDir & " && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt"
    objShell.Run cmd, 1, True
End If

' Inicia servidor em background e abre navegador
Dim apiScript
apiScript = workingDir & "\api.py"

If Not objFSO.FileExists(apiScript) Then
    MsgBox "Arquivo api.py não encontrado em: " & apiScript, vbCritical, "exam2md - Erro"
    WScript.Quit 1
End If

' Abre navegador após 2 segundos
Dim navScript
navScript = "cmd /c timeout /t 2 >nul && start """" http://localhost:8000"
objShell.Run navScript, 0, False

' Inicia servidor (bloqueia até fechar)
Dim serverCmd
serverCmd = "cmd /k cd /d " & workingDir & " && " & venvPython & " api.py"
objShell.Run serverCmd, 1, True