// Ladder runtime for C# builds (hand-written support code, never generated).
// Tracing (Trace.Step / Span), canonical JSON for comparisons, a fixable clock, and small data helpers.
// Copy into the project (e.g. Ladder/LadderRuntime.cs) when a build traces steps from inside the code.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;

namespace Ladder;

// Data access is not part of this runtime: with EF Core, generated steps use the DbContext the
// build profile names (see the vocabulary binding for "save data" / "find data").

public static class Clock
{
    static long? _fixed;
    public static void Fix(long unixSeconds) => _fixed = unixSeconds;
    public static long Now() => _fixed ?? DateTimeOffset.UtcNow.ToUnixTimeSeconds();
}

public static class Http
{
    public static Dictionary<string, object?> Response(int status, object? body) =>
        Data.Obj(("status", (long)status), ("body", body));
}

public static class Data
{
    public static Dictionary<string, object?> Obj(params (string Key, object? Value)[] pairs)
    {
        var d = new Dictionary<string, object?>();
        foreach (var (k, v) in pairs) d[k] = v;
        return d;
    }

    /// <summary>JSON text to plain values: Dictionary, List, string, long, double, bool, null.</summary>
    public static object? FromJson(string text)
    {
        using var doc = JsonDocument.Parse(text);
        return Plain(doc.RootElement);
    }

    static object? Plain(JsonElement e) => e.ValueKind switch
    {
        JsonValueKind.Object => e.EnumerateObject().ToDictionary(p => p.Name, p => Plain(p.Value)),
        JsonValueKind.Array => e.EnumerateArray().Select(Plain).ToList(),
        JsonValueKind.String => e.GetString(),
        JsonValueKind.Number => e.TryGetInt64(out var l) ? (object)l : e.GetDouble(),   // keep whole numbers as long
        JsonValueKind.True => true,
        JsonValueKind.False => false,
        _ => null,
    };

    /// <summary>JSON with sorted keys and no spaces; identical to Python's
    /// json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).</summary>
    public static string Canonical(object? v)
    {
        var sb = new StringBuilder();
        Write(sb, v);
        return sb.ToString();
    }

    static void Write(StringBuilder sb, object? v)
    {
        switch (v)
        {
            case null: sb.Append("null"); break;
            case bool b: sb.Append(b ? "true" : "false"); break;
            case string s: WriteString(sb, s); break;
            case int or long or short or byte: sb.Append(Convert.ToInt64(v).ToString(CultureInfo.InvariantCulture)); break;
            case double or float or decimal:
                var d = Convert.ToDouble(v);
                sb.Append(d == Math.Floor(d) && Math.Abs(d) < 1e15 ? ((long)d).ToString(CultureInfo.InvariantCulture) + ".0"
                                                                    : d.ToString("R", CultureInfo.InvariantCulture));
                break;
            case IDictionary dict:
                sb.Append('{');
                var first = true;
                foreach (var k in dict.Keys.Cast<object>().Select(k => k.ToString()!).OrderBy(k => k, StringComparer.Ordinal))
                {
                    if (!first) sb.Append(',');
                    first = false;
                    WriteString(sb, k);
                    sb.Append(':');
                    Write(sb, dict[k]);
                }
                sb.Append('}');
                break;
            case IEnumerable list:
                sb.Append('[');
                var f = true;
                foreach (var x in list) { if (!f) sb.Append(','); f = false; Write(sb, x); }
                sb.Append(']');
                break;
            default: WriteString(sb, v.ToString() ?? ""); break;
        }
    }

    static void WriteString(StringBuilder sb, string s)
    {
        sb.Append('"');
        foreach (var c in s)
        {
            switch (c)
            {
                case '"': sb.Append("\\\""); break;
                case '\\': sb.Append("\\\\"); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                case '\b': sb.Append("\\b"); break;
                case '\f': sb.Append("\\f"); break;
                default:
                    if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                    else sb.Append(c);
                    break;
            }
        }
        sb.Append('"');
    }

    /// <summary>One short phrase per value; same rules as the Python runtime.</summary>
    public static string Describe(object? v)
    {
        switch (v)
        {
            case null: return "nothing";
            case bool b: return b ? "yes" : "no";
            case int or long or short or byte: return Convert.ToInt64(v).ToString(CultureInfo.InvariantCulture);
            case double or float or decimal:
                var d = Convert.ToDouble(v);
                return d == Math.Floor(d) ? ((long)d).ToString(CultureInfo.InvariantCulture) : d.ToString("F2", CultureInfo.InvariantCulture);
            case string s: return "'" + (s.Length > 40 ? s[..37] + "..." : s) + "'";
            case IDictionary dict:
                return string.Join(", ", dict.Keys.Cast<object>().Select(k => k.ToString()!).OrderBy(k => k, StringComparer.Ordinal)
                    .Select(k => $"{k}={Nested(dict[k])}"));
            case IEnumerable list:
                var items = list.Cast<object?>().ToList();
                var desc = $"{items.Count} items";
                if (items.Count > 0 && items[0] is IDictionary fd && fd.Contains("title")) desc += $", first {Describe(fd["title"])}";
                else if (items.Count > 0 && items[0] is int or long) desc += $", first {Describe(items[0])}";
                return desc;
            default: return v.GetType().Name;
        }
    }

    static string Nested(object? v) => v switch
    {
        string => Describe(v),
        IDictionary => "{...}",
        IEnumerable l => $"{l.Cast<object?>().Count()} items",
        _ => Describe(v),
    };
}

public static class Trace
{
    record Event(string Step, string Ev, double Ms, string Info, string? Data);
    static readonly List<Event> Events = new();
    static readonly System.Diagnostics.Stopwatch Clock = System.Diagnostics.Stopwatch.StartNew();
    [ThreadStatic] static bool _off;

    /// <summary>Serving real traffic: trace nothing (keeps memory flat).</summary>
    public static bool Enabled { get; set; } = true;

    internal static void Add(string step, string ev, string info, string? data)
    {
        if (!Enabled || _off) return;
        lock (Events) Events.Add(new Event(step, ev, Math.Round(Clock.Elapsed.TotalMilliseconds, 2), info, data));
    }

    public static Span Step(string id, params object?[] args) => new(id, args);

    public static void Reset() { lock (Events) Events.Clear(); Clock.Restart(); }

    public static void Save(string path)
    {
        var sb = new StringBuilder();
        lock (Events)
            foreach (var e in Events)
            {
                var d = Data.Obj(("step", e.Step), ("ev", e.Ev), ("ms", e.Ms), ("info", e.Info));
                if (e.Data != null) d["data"] = e.Data;
                sb.Append(Data.Canonical(d)).Append('\n');
            }
        File.WriteAllText(path, sb.ToString());
    }
}

public sealed class Span : IDisposable
{
    readonly string _id;
    bool _closed;

    internal Span(string id, object?[] args)
    {
        _id = id;
        Trace.Add(id, "enter", string.Join(", ", args.Select(Data.Describe)), null);
    }

    public T Result<T>(T value)
    {
        Trace.Add(_id, "exit", Data.Describe(value), Data.Canonical(value));
        _closed = true;
        return value;
    }

    public void Done() { Trace.Add(_id, "exit", "done", "null"); _closed = true; }

    public void Dispose()
    {
        if (!_closed) Trace.Add(_id, "exit", "crashed", "crashed");
    }
}
