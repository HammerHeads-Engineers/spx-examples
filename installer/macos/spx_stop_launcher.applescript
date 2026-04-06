-- SPDX-License-Identifier: MIT
property appTitle : "SPX Stop"
property generatedLauncherRelativePath : "Library/Application Support/SPX/generated/spx-stop.command"

on run
  set homePath to POSIX path of (path to home folder)
  set launcherPath to homePath & generatedLauncherRelativePath

  try
    set launcherAlias to POSIX file launcherPath as alias
  on error
    activate
    display dialog appTitle & " could not find a generated SPX environment." & return & return & "Expected launcher: " & launcherPath & return & return & "Run SPX Setup.app first to generate an environment." buttons {"OK"} default button "OK" with icon stop
    return
  end try

  try
    do shell script "/usr/bin/open -a Terminal " & quoted form of (POSIX path of launcherAlias)
  on error errMsg number errNum
    activate
    display dialog "Unable to launch the SPX stop command in Terminal." & return & return & errMsg & " (" & errNum & ")" buttons {"OK"} default button "OK" with icon stop
  end try
end run
