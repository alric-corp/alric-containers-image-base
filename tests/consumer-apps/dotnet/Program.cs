using System.Runtime.InteropServices;

// A real ASP.NET Core service, restored and published without package sources.
var builder = WebApplication.CreateSlimBuilder(args);
builder.WebHost.UseUrls("http://0.0.0.0:8080");
var app = builder.Build();
app.MapGet("/health", () => Results.Json(new { status = "ok" }));
app.MapGet("/ready", () => Results.Json(new { status = "ok" }));
app.MapGet("/info", () => Results.Json(new
{
    status = "ok",
    runtime = "dotnet",
    runtime_version = Environment.Version.ToString(),
    architecture = RuntimeInformation.ProcessArchitecture switch
    {
        Architecture.X64 => "amd64",
        Architecture.Arm64 => "arm64",
        var other => other.ToString().ToLowerInvariant(),
    },
    security = Security.Probe(),
}));
app.Lifetime.ApplicationStopped.Register(() => Console.WriteLine("consumer shutdown complete"));
await app.RunAsync();

internal static class Security
{
    private static bool Writable(string directory)
    {
        string file = Path.Combine(directory, "consumer-write-" + Guid.NewGuid().ToString("N"));
        try
        {
            File.WriteAllText(file, "consumer-app");
            bool valid = File.ReadAllText(file) == "consumer-app";
            File.Delete(file);
            return valid;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    public static Dictionary<string, object> Probe()
    {
        var fields = File.ReadLines("/proc/self/status")
            .Select(line => line.Split(':', 2))
            .Where(parts => parts.Length == 2)
            .ToDictionary(parts => parts[0], parts => parts[1].Trim());
        string path = "/app/certification-root-probe";
        bool readOnly = false;
        string rootError = "write unexpectedly succeeded";
        try
        {
            File.WriteAllText(path, "must fail on read-only root");
            File.Delete(path);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            readOnly = error is IOException
                && error.Message.Contains("Read-only file system", StringComparison.Ordinal);
            rootError = error.Message;
        }
        return new Dictionary<string, object>
        {
            ["uid"] = int.Parse(fields["Uid"].Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries)[1]),
            ["gid"] = int.Parse(fields["Gid"].Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries)[1]),
            ["read_only_root"] = readOnly,
            ["root_write_error"] = rootError,
            ["writable_tmp"] = Writable("/tmp"),
            ["writable_app_work"] = Writable("/app/work"),
            ["cap_eff"] = fields["CapEff"],
            ["no_new_privileges"] = fields["NoNewPrivs"] == "1",
        };
    }
}
