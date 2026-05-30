// SPDX-License-Identifier: MIT
using System.Diagnostics;

namespace SpxLauncher;

internal static class Program
{
    private const string SpxRootFolderName = "SPX";
    private const string GeneratedDirectoryName = "generated";
    private const string WorkspaceDirectoryName = "workspace";
    private const string PauseOnErrorArgument = "--pause-on-error";

    public static int Main(string[] args)
    {
        var pauseOnError = HasPauseOnError(args);
        try
        {
            return Run(args);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[spx-launcher] {ex.Message}");
            if (pauseOnError)
            {
                PauseBeforeExit();
            }
            return 1;
        }
    }

    private static int Run(string[] args)
    {
        var filteredArgs = args
            .Where(argument => !string.Equals(argument, PauseOnErrorArgument, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        var mode = filteredArgs.Length == 0 ? "setup" : filteredArgs[0].Trim().ToLowerInvariant();
        var extraArgs = filteredArgs.Skip(1).ToArray();
        var installRoot = Path.GetFullPath(AppContext.BaseDirectory);

        return mode switch
        {
            "setup" => RunSetup(installRoot, extraArgs),
            "mcp-setup" => RunMcpSetup(installRoot, extraArgs),
            "start" => RunGeneratedPowerShell("spx-start.ps1"),
            "stop" => RunGeneratedPowerShell("spx-stop.ps1"),
            "cleanup" => RunCleanup(),
            "help" or "--help" or "-h" => ShowHelp(),
            _ => throw new InvalidOperationException(
                $"Unknown mode '{mode}'. Use one of: setup, mcp-setup, start, stop, cleanup."
            ),
        };
    }

    private static int ShowHelp()
    {
        Console.WriteLine("Usage: SpxLauncher.exe [setup|mcp-setup|start|stop|cleanup] [--pause-on-error]");
        Console.WriteLine();
        Console.WriteLine("  setup      Generate or refresh the local SPX environment.");
        Console.WriteLine("  mcp-setup  Create or refresh the SPX MCP workspace.");
        Console.WriteLine("  start      Run the generated SPX start script.");
        Console.WriteLine("  stop       Run the generated SPX stop script.");
        Console.WriteLine("  cleanup    Remove the generated SPX environment and Docker resources.");
        Console.WriteLine("  --pause-on-error  Wait for ENTER before closing after an error.");
        return 0;
    }

    private static bool HasPauseOnError(IEnumerable<string> args)
    {
        return args.Any(
            argument => string.Equals(argument, PauseOnErrorArgument, StringComparison.OrdinalIgnoreCase)
        );
    }

    private static void PauseBeforeExit()
    {
        Console.Error.WriteLine();
        Console.Error.Write("[spx-launcher] Press ENTER to close...");
        _ = Console.ReadLine();
    }

    private static int RunSetup(string installRoot, IReadOnlyList<string> extraArgs)
    {
        var scriptPath = Path.Combine(installRoot, "spx-install.ps1");
        EnsureFileExists(scriptPath, "Missing installed script 'spx-install.ps1'. Reinstall SPX.");
        var pythonExecutable = ResolvePythonExecutable();

        var arguments = new List<string>
        {
            "-ExecutionPolicy",
            "Bypass",
            "-NoProfile",
            "-File",
            scriptPath,
        };

        if (extraArgs.Count == 0)
        {
            arguments.Add("generate");
            arguments.Add("--output");
            arguments.Add(GetGeneratedDirectory());
        }
        else
        {
            arguments.AddRange(extraArgs);
        }

        return RunCommand(
            GetPowerShellExecutable(),
            arguments,
            installRoot,
            environment: new Dictionary<string, string>
            {
                ["PYTHON_BIN"] = pythonExecutable,
            }
        );
    }

    private static int RunMcpSetup(string installRoot, IReadOnlyList<string> extraArgs)
    {
        var pythonExecutable = ResolvePythonExecutable();
        var scriptPath = Path.Combine(installRoot, "installer", "mcp_workspace.py");
        EnsureFileExists(scriptPath, "Missing installed script 'installer\\mcp_workspace.py'. Reinstall SPX.");
        var hasSeedEnv = extraArgs.Any(
            argument => string.Equals(argument, "--seed-env", StringComparison.OrdinalIgnoreCase)
        );

        var arguments = new List<string>
        {
            scriptPath,
            "--source-root",
            installRoot,
            "--workspace-dir",
            GetWorkspaceDirectory(),
            "--python",
            pythonExecutable,
            "--server-name",
            "spx",
            "--suggested-work-mode",
            "runtime_mcp",
        };
        if (!hasSeedEnv)
        {
            arguments.Add("--seed-env");
            arguments.Add(GetGeneratedEnvFile());
        }
        arguments.AddRange(extraArgs);

        return RunCommand(pythonExecutable, arguments, installRoot);
    }

    private static int RunGeneratedPowerShell(string scriptName)
    {
        var scriptPath = Path.Combine(GetGeneratedDirectory(), scriptName);
        EnsureFileExists(
            scriptPath,
            $"Missing generated launcher '{scriptName}'. Run SPX Setup first."
        );

        var arguments = new[]
        {
            "-ExecutionPolicy",
            "Bypass",
            "-NoProfile",
            "-File",
            scriptPath,
        };
        return RunCommand(GetPowerShellExecutable(), arguments, GetGeneratedDirectory());
    }

    private static int RunCleanup()
    {
        var generatedDirectory = GetGeneratedDirectory();
        if (!Directory.Exists(generatedDirectory))
        {
            Console.WriteLine("[spx-launcher] No generated SPX environment found.");
            return 0;
        }

        var composePath = Path.Combine(generatedDirectory, "docker-compose.generated.yml");
        var envPath = Path.Combine(generatedDirectory, ".env");
        if (File.Exists(composePath) && TryResolveCommand("docker.exe", out var dockerExecutable))
        {
            Console.WriteLine("[spx-launcher] Removing Docker resources from generated environment...");
            _ = RunCommand(
                dockerExecutable,
                new[]
                {
                    "compose",
                    "-f",
                    composePath,
                    "--env-file",
                    envPath,
                    "down",
                    "--remove-orphans",
                    "--volumes",
                    "--rmi",
                    "all",
                },
                generatedDirectory,
                allowFailure: true
            );
        }

        Directory.Delete(generatedDirectory, recursive: true);
        Console.WriteLine($"[spx-launcher] Removed {generatedDirectory}");
        return 0;
    }

    private static string ResolvePythonExecutable()
    {
        var envPython = Environment.GetEnvironmentVariable("PYTHON_BIN");
        if (!string.IsNullOrWhiteSpace(envPython))
        {
            var resolved = TryResolvePythonExecutable(envPython, Array.Empty<string>());
            if (resolved is not null)
            {
                return resolved;
            }

            throw new InvalidOperationException(
                $"PYTHON_BIN is set to '{envPython}' but is not a working Python 3.10+ interpreter."
            );
        }

        foreach (var candidate in new[]
                 {
                     new PythonCandidate("py", new[] { "-3.12" }),
                     new PythonCandidate("py", new[] { "-3" }),
                     new PythonCandidate("python", Array.Empty<string>()),
                     new PythonCandidate("python3", Array.Empty<string>()),
                 })
        {
            var resolved = TryResolvePythonExecutable(candidate.FileName, candidate.PrefixArguments);
            if (resolved is not null)
            {
                return resolved;
            }
        }

        throw new InvalidOperationException(
            "Python 3.10+ is required for 'mcp-setup'. Install Python 3.12 and retry."
        );
    }

    private static string? TryResolvePythonExecutable(string fileName, IReadOnlyList<string> prefixArguments)
    {
        var versionCheck = new List<string>(prefixArguments)
        {
            "-c",
            "import sys; print(sys.executable); raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)",
        };

        var startInfo = new ProcessStartInfo
        {
            FileName = fileName,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        foreach (var argument in versionCheck)
        {
            startInfo.ArgumentList.Add(argument);
        }

        try
        {
            using var process = Process.Start(startInfo);
            if (process is null)
            {
                return null;
            }

            var stdout = process.StandardOutput.ReadToEnd();
            _ = process.StandardError.ReadToEnd();
            process.WaitForExit();
            if (process.ExitCode != 0)
            {
                return null;
            }

            var executable = stdout
                .Split(new[] { "\r\n", "\n" }, StringSplitOptions.RemoveEmptyEntries)
                .FirstOrDefault();
            return string.IsNullOrWhiteSpace(executable) ? null : executable.Trim();
        }
        catch
        {
            return null;
        }
    }

    private static string GetPowerShellExecutable()
    {
        if (TryResolveCommand("powershell.exe", out var executable))
        {
            return executable;
        }

        if (TryResolveCommand("pwsh.exe", out executable))
        {
            return executable;
        }

        throw new InvalidOperationException("Unable to locate PowerShell on PATH.");
    }

    private static bool TryResolveCommand(string command, out string resolvedPath)
    {
        var pathValue = Environment.GetEnvironmentVariable("PATH") ?? string.Empty;
        foreach (var segment in pathValue.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            var candidate = Path.Combine(segment.Trim(), command);
            if (File.Exists(candidate))
            {
                resolvedPath = candidate;
                return true;
            }
        }

        resolvedPath = string.Empty;
        return false;
    }

    private static string GetGeneratedDirectory()
    {
        return Path.Combine(GetSpxRootDirectory(), GeneratedDirectoryName);
    }

    private static string GetGeneratedEnvFile()
    {
        return Path.Combine(GetGeneratedDirectory(), ".env");
    }

    private static string GetWorkspaceDirectory()
    {
        return Path.Combine(GetSpxRootDirectory(), WorkspaceDirectoryName);
    }

    private static string GetSpxRootDirectory()
    {
        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        return Path.Combine(localAppData, SpxRootFolderName);
    }

    private static void EnsureFileExists(string path, string message)
    {
        if (!File.Exists(path))
        {
            throw new InvalidOperationException(message);
        }
    }

    private static int RunCommand(
        string fileName,
        IEnumerable<string> arguments,
        string workingDirectory,
        bool allowFailure = false,
        IReadOnlyDictionary<string, string>? environment = null
    )
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = fileName,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
        };
        if (environment is not null)
        {
            foreach (var pair in environment)
            {
                startInfo.Environment[pair.Key] = pair.Value;
            }
        }

        foreach (var argument in arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        using var process = Process.Start(startInfo);
        if (process is null)
        {
            throw new InvalidOperationException($"Failed to launch {fileName}.");
        }

        process.WaitForExit();
        if (!allowFailure && process.ExitCode != 0)
        {
            throw new InvalidOperationException(
                $"{Path.GetFileName(fileName)} failed with exit code {process.ExitCode}."
            );
        }

        return process.ExitCode;
    }

    private sealed record PythonCandidate(string FileName, IReadOnlyList<string> PrefixArguments);
}
