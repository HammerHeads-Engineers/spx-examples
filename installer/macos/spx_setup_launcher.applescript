-- SPDX-License-Identifier: MIT
property appTitle : "SPX Setup"
property payloadDirName : "spx-installer"
property launcherName : "spx-setup.command"

on run
  set appBundlePath to POSIX path of (path to me)
  set launcherPath to appBundlePath & "Contents/Resources/" & payloadDirName & "/" & launcherName

  try
    set launcherAlias to POSIX file launcherPath as alias
  on error
    activate
    display dialog appTitle & " could not find the embedded installer launcher." buttons {"OK"} default button "OK" with icon stop
    return
  end try

  try
    do shell script "/usr/bin/open -a Terminal " & quoted form of (POSIX path of launcherAlias)
  on error errMsg number errNum
    activate
    display dialog "Unable to launch the SPX installer in Terminal." & return & return & errMsg & " (" & errNum & ")" buttons {"OK"} default button "OK" with icon stop
  end try
end run
