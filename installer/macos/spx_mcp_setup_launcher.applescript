-- SPDX-License-Identifier: MIT
property appTitle : "SPX MCP Setup"
property setupAppName : "SPX Setup.app"
property payloadDirName : "spx-installer"
property launcherName : "spx-mcp-setup.command"

on run
  set appBundlePath to POSIX path of (path to me)
  set appsDirPath to do shell script "/usr/bin/dirname " & quoted form of appBundlePath
  set launcherPath to appsDirPath & "/" & setupAppName & "/Contents/Resources/" & payloadDirName & "/" & launcherName

  try
    set launcherAlias to POSIX file launcherPath as alias
  on error
    activate
    display dialog appTitle & " could not find the embedded MCP setup launcher." & return & return & "Expected launcher: " & launcherPath & return & return & "Reinstall the latest SPX package if SPX Setup.app is missing." buttons {"OK"} default button "OK" with icon stop
    return
  end try

  try
    do shell script "/usr/bin/open -a Terminal " & quoted form of (POSIX path of launcherAlias)
  on error errMsg number errNum
    activate
    display dialog "Unable to launch the SPX MCP workspace setup in Terminal." & return & return & errMsg & " (" & errNum & ")" buttons {"OK"} default button "OK" with icon stop
  end try
end run
