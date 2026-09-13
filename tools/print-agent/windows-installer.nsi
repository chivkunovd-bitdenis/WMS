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
  IfFileExists "$INSTDIR\wms-print.exe" 0 fresh_install
  ExecWait '"$INSTDIR\wms-print.exe" --stop --wait-stop' $0
  StrCmp $0 "0" +2
  Abort "WMS Print did not stop; the previous version was kept."
  RMDir /r "$INSTDIR.previous"
  Rename "$INSTDIR" "$INSTDIR.previous"
  IfErrors 0 +2
  Abort "The previous WMS Print folder could not be preserved."
fresh_install:
  SetOutPath "$INSTDIR"
  ClearErrors
  File /r "${PAYLOAD}\*.*"
  IfErrors install_rollback
  WriteUninstaller "$INSTDIR\Uninstall WMS Print.exe"
  CreateDirectory "$SMPROGRAMS\WMS Print"
  CreateShortcut "$SMPROGRAMS\WMS Print\Подключить WMS Print.lnk" "$INSTDIR\wms-print-setup.exe"
  CreateShortcut "$SMPROGRAMS\WMS Print\Удалить WMS Print.lnk" "$INSTDIR\Uninstall WMS Print.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WMSPrint" "DisplayName" "WMS Print"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WMSPrint" "UninstallString" '"$INSTDIR\Uninstall WMS Print.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WMSPrint" "DisplayVersion" "WMS-442"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WMSPrint" "NoModify" 1
  IfFileExists "$LOCALAPPDATA\WMS Print\connection.json" 0 +2
  ExecWait '"$INSTDIR\wms-print-setup.exe" --ensure-autostart' $0
  StrCmp $0 "0" start_succeeded
  RMDir /r "$INSTDIR"
  IfFileExists "$INSTDIR.previous\wms-print.exe" 0 +2
  Rename "$INSTDIR.previous" "$INSTDIR"
  Abort "The background task did not start; the previous WMS Print version was restored."
start_succeeded:
  RMDir /r "$INSTDIR.previous"
  Goto install_done
install_rollback:
  RMDir /r "$INSTDIR"
  IfFileExists "$INSTDIR.previous\wms-print.exe" 0 +2
  Rename "$INSTDIR.previous" "$INSTDIR"
  Abort "Installation failed; the previous WMS Print version was restored."
install_done:
SectionEnd

Section "Uninstall"
  ExecWait '"$INSTDIR\wms-print-setup.exe" --uninstall'
  Delete "$SMPROGRAMS\WMS Print\Подключить WMS Print.lnk"
  Delete "$SMPROGRAMS\WMS Print\Удалить WMS Print.lnk"
  RMDir "$SMPROGRAMS\WMS Print"
  Delete "$INSTDIR\Uninstall WMS Print.exe"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WMSPrint"
  ; Private connection state is deliberately retained for recovery after reinstall.
SectionEnd
