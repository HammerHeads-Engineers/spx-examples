property appTitle : "SPX Uninstall"
property packageId : "com.hammerheadsengineers.spx.installer"
property supportDirRelativePath : "Library/Application Support/SPX"
property generatedDirRelativePath : "Library/Application Support/SPX/generated"
property workspaceRelativePath : "Documents/SPX Codex Workspace"

on run
  set homePath to POSIX path of (path to home folder)
  set appBundlePath to POSIX path of (path to me)
  set appsDirPath to do shell script "/usr/bin/dirname " & quoted form of appBundlePath
  set supportDir to homePath & supportDirRelativePath
  set generatedDir to homePath & generatedDirRelativePath
  set workspaceDir to homePath & workspaceRelativePath
  set removeWorkspace to false
  set uninstallMessage to "SPX Uninstall will stop the local stack, remove generated SPX files, delete the installed SPX apps, and forget the macOS package receipt."

  activate
  if my fileOrDirExists(workspaceDir) then
    set workspaceChoice to button returned of (display dialog uninstallMessage & return & return & "Choose whether to keep the installer-managed workspace:" & return & workspaceDir buttons {"Cancel", "Keep Workspace", "Remove Workspace"} default button "Keep Workspace" cancel button "Cancel" with icon caution)
    set removeWorkspace to workspaceChoice is "Remove Workspace"
  else
    display dialog uninstallMessage buttons {"Cancel", "Uninstall"} default button "Uninstall" cancel button "Cancel" with icon caution
  end if

  try
    do shell script "/bin/bash -lc " & quoted form of my cleanupShell(supportDir, generatedDir, workspaceDir, removeWorkspace)
    do shell script "/bin/bash -lc " & quoted form of my uninstallShell(appsDirPath, packageId) with administrator privileges
    activate
    if removeWorkspace then
      display dialog appTitle & " removed the installed SPX tools and the installer-managed workspace." buttons {"OK"} default button "OK" with icon note
    else
      display dialog appTitle & " removed the installed SPX tools." & return & return & "The installer-managed workspace was left in place." buttons {"OK"} default button "OK" with icon note
    end if
  on error errMsg number errNum
    if errNum is -128 then
      return
    end if

    activate
    display dialog "Unable to uninstall SPX." & return & return & errMsg & " (" & errNum & ")" buttons {"OK"} default button "OK" with icon stop
  end try
end run

on cleanupShell(supportDir, generatedDir, workspaceDir, removeWorkspace)
  set commandLines to {}
  set end of commandLines to "set -euo pipefail"
  set end of commandLines to "SUPPORT_DIR=" & quoted form of supportDir
  set end of commandLines to "GENERATED_DIR=" & quoted form of generatedDir
  set end of commandLines to "WORKSPACE_DIR=" & quoted form of workspaceDir
  set end of commandLines to "REMOVE_WORKSPACE=" & (my boolToFlag(removeWorkspace))
  set end of commandLines to "pkill -f spx-ble-adapter >/dev/null 2>&1 || true"
  set end of commandLines to "if [ -f \"$GENERATED_DIR/docker-compose.generated.yml\" ] && command -v docker >/dev/null 2>&1; then"
  set end of commandLines to "  docker compose -f \"$GENERATED_DIR/docker-compose.generated.yml\" --env-file \"$GENERATED_DIR/.env\" down --remove-orphans --volumes --rmi all || true"
  set end of commandLines to "fi"
  set end of commandLines to "rm -rf \"$SUPPORT_DIR\""
  set end of commandLines to "if [ \"$REMOVE_WORKSPACE\" = 1 ]; then"
  set end of commandLines to "  rm -rf \"$WORKSPACE_DIR\""
  set end of commandLines to "fi"
  return my joinLines(commandLines, linefeed)
end cleanupShell

on uninstallShell(appsDirPath, packageId)
  set commandLines to {}
  set end of commandLines to "set -euo pipefail"
  set end of commandLines to "APPS_DIR=" & quoted form of appsDirPath
  set end of commandLines to "PACKAGE_ID=" & quoted form of packageId
  set end of commandLines to "for app_name in 'SPX Setup.app' 'SPX MCP Setup.app' 'SPX Start.app' 'SPX Stop.app' 'SPX Cleanup.app' 'SPX Uninstall.app'; do"
  set end of commandLines to "  rm -rf \"$APPS_DIR/$app_name\""
  set end of commandLines to "done"
  set end of commandLines to "if [ \"$(/usr/bin/basename \"$APPS_DIR\")\" = 'SPX Tools' ]; then"
  set end of commandLines to "  rmdir \"$APPS_DIR\" 2>/dev/null || true"
  set end of commandLines to "fi"
  set end of commandLines to "pkgutil --forget \"$PACKAGE_ID\" >/dev/null 2>&1 || true"
  return my joinLines(commandLines, linefeed)
end uninstallShell

on fileOrDirExists(targetPath)
  try
    do shell script "test -e " & quoted form of targetPath
    return true
  on error
    return false
  end try
end fileOrDirExists

on boolToFlag(flagValue)
  if flagValue then
    return "1"
  end if
  return "0"
end boolToFlag

on joinLines(itemsList, delimiter)
  set previousDelimiters to AppleScript's text item delimiters
  set AppleScript's text item delimiters to delimiter
  set joinedText to itemsList as text
  set AppleScript's text item delimiters to previousDelimiters
  return joinedText
end joinLines
