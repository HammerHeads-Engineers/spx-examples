property appTitle : "SPX Cleanup"
property generatedDirRelativePath : "Library/Application Support/SPX/generated"
property runtimeDirRelativePath : "Library/Application Support/SPX/runtime"

on run
  set homePath to POSIX path of (path to home folder)
  set generatedDir to homePath & generatedDirRelativePath
  set runtimeDir to homePath & runtimeDirRelativePath

  if not my fileOrDirExists(generatedDir) and not my fileOrDirExists(runtimeDir) then
    activate
    display dialog appTitle & " did not find any local SPX runtime files to remove." & return & return & "Expected locations:" & return & generatedDir & return & runtimeDir buttons {"OK"} default button "OK" with icon note
    return
  end if

  activate
  display dialog "SPX Cleanup will stop the local stack, remove generated files, remove the installer runtime, and ask Docker to delete containers, volumes, and images referenced by the generated environment." buttons {"Cancel", "Clean Up"} default button "Clean Up" cancel button "Cancel" with icon caution

  set commandText to "/bin/bash -lc " & quoted form of my cleanupShell(generatedDir, runtimeDir)

  try
    tell application "Terminal"
      activate
      do script commandText
    end tell
  on error errMsg number errNum
    activate
    display dialog "Unable to launch the SPX cleanup command in Terminal." & return & return & errMsg & " (" & errNum & ")" buttons {"OK"} default button "OK" with icon stop
  end try
end run

on cleanupShell(generatedDir, runtimeDir)
  set commandLines to {}
  set end of commandLines to "set -euo pipefail"
  set end of commandLines to "GENERATED_DIR=" & quoted form of generatedDir
  set end of commandLines to "RUNTIME_DIR=" & quoted form of runtimeDir
  set end of commandLines to "echo \"[spx-cleanup] Generated directory: $GENERATED_DIR\""
  set end of commandLines to "echo \"[spx-cleanup] Runtime directory: $RUNTIME_DIR\""
  set end of commandLines to "pkill -f spx-ble-adapter >/dev/null 2>&1 || true"
  set end of commandLines to "if [ -f \"$GENERATED_DIR/docker-compose.generated.yml\" ] && command -v docker >/dev/null 2>&1; then"
  set end of commandLines to "  echo \"[spx-cleanup] Removing Docker resources from generated environment...\""
  set end of commandLines to "  docker compose -f \"$GENERATED_DIR/docker-compose.generated.yml\" --env-file \"$GENERATED_DIR/.env\" down --remove-orphans --volumes --rmi all || true"
  set end of commandLines to "elif [ -f \"$GENERATED_DIR/docker-compose.generated.yml\" ]; then"
  set end of commandLines to "  echo \"[spx-cleanup] Docker CLI not found; skipping Docker cleanup.\""
  set end of commandLines to "fi"
  set end of commandLines to "rm -rf \"$GENERATED_DIR\" \"$RUNTIME_DIR\""
  set end of commandLines to "echo \"[spx-cleanup] Removed local SPX generated and runtime directories.\""
  return my joinLines(commandLines, linefeed)
end cleanupShell

on fileOrDirExists(targetPath)
  try
    do shell script "test -e " & quoted form of targetPath
    return true
  on error
    return false
  end try
end fileOrDirExists

on joinLines(itemsList, delimiter)
  set previousDelimiters to AppleScript's text item delimiters
  set AppleScript's text item delimiters to delimiter
  set joinedText to itemsList as text
  set AppleScript's text item delimiters to previousDelimiters
  return joinedText
end joinLines
