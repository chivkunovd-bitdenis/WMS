Unicode true
Name "WMS Print"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\WMS Print"
RequestExecutionLevel user
ShowInstDetails show
ShowUninstDetails show

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "WMS Print"
  IfFileExists "$INSTDIR\wms-print.exe" 0 +3
  ExecWait '"$INSTDIR\wms-print.exe" --stop'
  Sleep 1500
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}\*.*"
  WriteUninstaller "$INSTDIR\Uninstall WMS Print.exe"
  CreateDirectory "$SMPROGRAMS\WMS Print"
  CreateShortcut "$SMPROGRAMS\WMS Print\Подключить WMS Print.lnk" "$INSTDIR\wms-print.exe"
  CreateShortcut "$SMPROGRAMS\WMS Print\Удалить WMS Print.lnk" "$INSTDIR\Uninstall WMS Print.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WMSPrint" "DisplayName" "WMS Print"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WMSPrint" "UninstallString" '"$INSTDIR\Uninstall WMS Print.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WMSPrint" "DisplayVersion" "WMS-442"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WMSPrint" "NoModify" 1
  IfFileExists "$LOCALAPPDATA\WMS Print\connection.json" 0 +2
  Exec '"$INSTDIR\wms-print.exe" --run'
SectionEnd

Section "Uninstall"
  ExecWait '"$INSTDIR\wms-print.exe" --uninstall'
  Delete "$SMPROGRAMS\WMS Print\Подключить WMS Print.lnk"
  Delete "$SMPROGRAMS\WMS Print\Удалить WMS Print.lnk"
  RMDir "$SMPROGRAMS\WMS Print"
  Delete "$INSTDIR\Uninstall WMS Print.exe"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WMSPrint"
  ; Private connection state is deliberately retained for recovery after reinstall.
SectionEnd
