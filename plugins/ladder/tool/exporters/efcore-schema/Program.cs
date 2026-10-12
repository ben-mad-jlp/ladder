// Ladder schema exporter for EF Core: writes the "json" schema kind that `ladder schema` reads,
// for projects whose migrations are not EF migrations (no ModelSnapshot.cs).
//
// It builds each DbContext's model offline (no database connection is opened) and writes
// tables, columns, types, keys and navigations.
//
//   dotnet run --project <this folder> -p:ModelsProject=<path to the project with the DbContexts> \
//       -- --context QbsDbContext --out ladder/auth/api/schemas/qbs.json [--context Other --out other.json]
//
// The context is constructed with DbContextOptions<T> configured for the provider the models project
// already references (SQL Server, PostgreSQL or SQLite), using a dummy connection string.
// A context that only has a parameterless constructor is constructed with that one.

using System.Reflection;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Metadata;

var pairs = new List<(string Context, string Out)>();
for (int i = 0; i < args.Length; i++)
{
    if (args[i] == "--context" && i + 1 < args.Length)
        pairs.Add((args[++i], ""));
    else if (args[i] == "--out" && i + 1 < args.Length && pairs.Count > 0)
        pairs[^1] = (pairs[^1].Context, args[++i]);
}
if (pairs.Count == 0 || pairs.Any(p => p.Out == ""))
{
    Console.Error.WriteLine("usage: --context <DbContext class name> --out <file.json> [--context ... --out ...]");
    return 2;
}

// Load every assembly next to this program, so the models project and its provider are visible.
foreach (var dll in Directory.GetFiles(AppContext.BaseDirectory, "*.dll"))
{
    try { Assembly.LoadFrom(dll); } catch { /* native or unrelated */ }
}
var types = AppDomain.CurrentDomain.GetAssemblies()
    .SelectMany(a => { try { return a.GetTypes(); } catch (ReflectionTypeLoadException e) { return e.Types.OfType<Type>(); } })
    .ToList();

foreach (var (contextName, outPath) in pairs)
{
    var ctxType = types.FirstOrDefault(t => typeof(DbContext).IsAssignableFrom(t) && !t.IsAbstract
                                            && (t.Name == contextName || t.FullName == contextName));
    if (ctxType == null)
    {
        Console.Error.WriteLine($"no DbContext named {contextName}; found: " +
            string.Join(", ", types.Where(t => typeof(DbContext).IsAssignableFrom(t) && !t.IsAbstract).Select(t => t.Name)));
        return 1;
    }
    using var ctx = Create(ctxType, types);
    IModel model;
    try { model = ctx.GetService<IDesignTimeModel>().Model; }
    catch { model = ctx.Model; }

    var entities = new List<object>();
    foreach (var e in model.GetEntityTypes().OrderBy(x => x.ClrType.Name))
    {
        if (e.IsOwned() && e.GetTableName() == e.FindOwnership()?.PrincipalEntityType.GetTableName())
            continue;   // owned types stored in their owner's table show as the owner's columns
        var table = e.GetTableName() ?? e.GetViewName();
        var schema = e.GetSchema() ?? e.GetViewSchema();
        var store = table != null ? StoreObjectIdentifier.Create(e, e.GetTableName() != null ? StoreObjectType.Table : StoreObjectType.View) : null;
        entities.Add(new
        {
            name = e.ClrType.IsGenericType ? e.ShortName() : e.ClrType.Name,
            table = schema != null ? $"{schema}.{table}" : (table ?? e.ShortName()),
            keys = e.FindPrimaryKey()?.Properties.Select(p => p.Name).ToList() ?? new List<string>(),
            properties = e.GetProperties().Select(p => new
            {
                name = p.Name,
                column = store is { } so ? (p.GetColumnName(so) ?? p.Name) : p.Name,
                type = SafeColumnType(p),
                required = !p.IsNullable,
                maxLength = p.GetMaxLength(),
                // set by the database: identity keys and columns with a SQL default
                generated = (p.ValueGenerated == ValueGenerated.OnAdd && p.IsPrimaryKey() && p.ClrType != typeof(Guid))
                            || p.GetDefaultValueSql() != null,
            }).ToList(),
            navigations = e.GetNavigations().Select(n => (object)new
            {
                name = n.Name,
                target = n.TargetEntityType.ClrType.Name,
                many = n.IsCollection,
                foreignKey = string.Join(", ", n.ForeignKey.Properties.Select(p => p.Name)),
                through = "",
            }).Concat(e.GetSkipNavigations().Select(n => (object)new
            {
                name = n.Name,
                target = n.TargetEntityType.ClrType.Name,
                many = n.IsCollection,
                foreignKey = "",
                through = n.JoinEntityType.ClrType.IsGenericType ? n.JoinEntityType.ShortName() : n.JoinEntityType.ClrType.Name,
            })).ToList(),
        });
    }
    Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outPath))!);
    File.WriteAllText(outPath, JsonSerializer.Serialize(new { context = ctxType.Name, entities },
        new JsonSerializerOptions { WriteIndented = true }));
    Console.WriteLine($"{ctxType.Name}: {entities.Count} entities -> {outPath}");
}
return 0;

static string SafeColumnType(IProperty p)
{
    try { return p.GetColumnType(); }
    catch { return p.ClrType.Name; }
}

static DbContext Create(Type ctxType, List<Type> types)
{
    var withOptions = ctxType.GetConstructors().FirstOrDefault(c =>
        c.GetParameters().Length == 1 && typeof(DbContextOptions).IsAssignableFrom(c.GetParameters()[0].ParameterType));
    if (withOptions == null)
    {
        var bare = ctxType.GetConstructor(Type.EmptyTypes)
            ?? throw new InvalidOperationException($"{ctxType.Name} has neither a (DbContextOptions) nor a parameterless constructor");
        return (DbContext)bare.Invoke(null);
    }
    var builderType = typeof(DbContextOptionsBuilder<>).MakeGenericType(ctxType);
    var builder = (DbContextOptionsBuilder)Activator.CreateInstance(builderType)!;
    UseProvider(builder, types);
    return (DbContext)withOptions.Invoke(new object[] { builder.Options });
}

static void UseProvider(DbContextOptionsBuilder builder, List<Type> types)
{
    // The provider the models project references; the connection string is never opened.
    var candidates = new (string Method, string Conn)[]
    {
        ("UseSqlServer", "Server=ladder-schema-export;Database=none;Trusted_Connection=True"),
        ("UseNpgsql", "Host=ladder-schema-export;Database=none"),
        ("UseSqlite", "Data Source=:memory:"),
    };
    foreach (var (method, conn) in candidates)
    {
        var m = types.Where(t => t.IsAbstract && t.IsSealed)
            .SelectMany(t => t.GetMethods(BindingFlags.Public | BindingFlags.Static))
            .FirstOrDefault(x => x.Name == method && !x.IsGenericMethod && x.GetParameters().Length >= 2
                                 && x.GetParameters()[0].ParameterType == typeof(DbContextOptionsBuilder)
                                 && x.GetParameters()[1].ParameterType == typeof(string));
        if (m == null)
            continue;
        var ps = m.GetParameters();
        var call = new object?[ps.Length];
        call[0] = builder;
        call[1] = conn;
        for (int i = 2; i < ps.Length; i++)
            call[i] = ps[i].HasDefaultValue ? ps[i].DefaultValue : null;
        m.Invoke(null, call);
        return;
    }
    throw new InvalidOperationException("no EF Core relational provider found (UseSqlServer, UseNpgsql or UseSqlite)");
}
