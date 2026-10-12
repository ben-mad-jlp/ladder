# EF Core schema exporter

For projects whose database changes are not EF migrations (no `ModelSnapshot.cs` to point
`"kind": "efcore-snapshot"` at). It builds each DbContext's model offline, without opening a
database connection, and writes Ladder's `"kind": "json"` schema.

```
dotnet run --project <plugin>/tool/exporters/efcore-schema \
    -p:ModelsProject=/abs/path/to/the/project/with/your/DbContexts.csproj \
    -- --context QbsDbContext --out ladder/auth/api/schemas/qbs.json \
       --context ReportsDbContext --out ladder/auth/api/schemas/reports.json
```

- Add `-p:LadderTargetFramework=net9.0` (or the models project's framework) if it is not net8.0. (Not
  `-p:TargetFramework`: NuGet's restore drops that one and the build fails with NU1201.)
- A context whose constructor takes more than the options (a per-year archive context) gets the rest
  from `--ctor-arg name=value` after its `--context`, for example `--ctor-arg year=2025`.
- The models project must reference its provider (SQL Server, PostgreSQL or SQLite); the exporter
  configures it with a dummy connection string that is never opened. A context with only a
  parameterless constructor is created with that one; its `OnConfiguring` must not connect.
- Re-run it after every schema change (it is quick), and commit the JSON: `ladder check` then
  shows steps whose referenced columns changed (`ladder check --since=<git ref>` before the first stamp).
