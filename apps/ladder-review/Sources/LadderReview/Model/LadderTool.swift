import Foundation

/// Runs the `ladder` tool and decodes its JSON. The tool is the only thing that reads `.ladder` files, runs checks or
/// writes Ladder files; the app is a front end to it (SPEC: "The tool holds the logic").
struct LadderTool: Sendable {
    /// What to run: a `ladder` executable, or the plugin's `tool/ladder.py` (run through python3).
    var path: String

    struct Failure: LocalizedError {
        var command: String
        var status: Int32
        var stderr: String
        var errorDescription: String? {
            "`\(command)` failed (exit \(status))" + (stderr.isEmpty ? "" : ":\n" + stderr)
        }
    }

    struct Output: Sendable {
        var status: Int32
        var stdout: Data
        var stderr: String
    }

    /// The tool's arguments for one command, through python3 when `path` is the Python file.
    func invocation(_ args: [String]) -> (executable: String, arguments: [String]) {
        if path.hasSuffix(".py") { return ("/usr/bin/env", ["python3", path] + args) }
        return (path, args)
    }

    /// Run `ladder <args>`. Exit codes 0, 1 and 3 are answers (ok, problems, awaiting approval), not failures;
    /// anything else, or no output, throws.
    func run(_ args: [String], in folder: String? = nil, acceptedStatuses: Set<Int32> = [0, 1, 3]) async throws -> Data {
        let (exe, arguments) = invocation(args)
        let out = try await Shell.run(exe, arguments, in: folder)
        guard acceptedStatuses.contains(out.status), !out.stdout.isEmpty else {
            throw Failure(command: (["ladder"] + args).joined(separator: " "), status: out.status, stderr: out.stderr)
        }
        return out.stdout
    }

    func decode<T: Decodable>(_ type: T.Type, _ args: [String], in folder: String? = nil) async throws -> T {
        let data = try await run(args, in: folder)
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw Failure(command: (["ladder"] + args).joined(separator: " "), status: 0,
                          stderr: "unexpected JSON: \(error)")
        }
    }

    func projects(in folder: String) async throws -> ProjectList {
        try await decode(ProjectList.self, ["projects", folder], in: folder)
    }

    /// The project's tree, data, vocabulary and regions, with its check report: one run of the tool per project.
    func export(_ project: String, since: String? = nil) async throws -> ExportDoc {
        var args = ["export", project, "--regions"]
        if let since, !since.isEmpty { args.append("--since=\(since)") }
        return try await decode(ExportDoc.self, args, in: (project as NSString).deletingLastPathComponent)
    }

    func check(_ project: String, since: String? = nil) async throws -> CheckReport {
        var args = ["check", project, "--json"]
        if let since, !since.isEmpty { args.append("--since=\(since)") }
        return try await decode(CheckReport.self, args, in: (project as NSString).deletingLastPathComponent)
    }

    /// Run a command that answers JSON or `{"refused": ...}`; a refusal is thrown with the tool's reason.
    func decodeOrRefusal<T: Decodable>(_ type: T.Type, _ args: [String], in folder: String) async throws -> T {
        let data = try await run(args, in: folder, acceptedStatuses: [0, 1])
        if let r = try? JSONDecoder().decode(Refusal.self, from: data) { throw r }
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw Failure(command: (["ladder"] + args).joined(separator: " "), status: 0, stderr: "unexpected JSON: \(error)")
        }
    }

    /// `ladder edit`: change a step's parts, or with `dryRun` only show the diff and what goes stale.
    func edit(_ project: String, step: String, _ change: StepEdit, expect: String?, dryRun: Bool) async throws -> EditResult {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("ladder-edit-\(UUID().uuidString).json")
        try JSONEncoder().encode(change).write(to: file)
        defer { try? FileManager.default.removeItem(at: file) }
        var args = ["edit", project, step, "--from", file.path, "--json"]
        if let expect { args += ["--expect", expect] }
        if dryRun { args.append("--dry-run") }
        return try await decodeOrRefusal(EditResult.self, args, in: (project as NSString).deletingLastPathComponent)
    }

    /// `ladder answer`: answer note `number` (from 1) of a step.
    func answer(_ project: String, step: String, note number: Int, _ text: String, plain: Bool, expect: String?,
                dryRun: Bool) async throws -> EditResult {
        var args = ["answer", project, step, String(number), text, "--json"]
        if plain { args.append("--plain") }
        if let expect { args += ["--expect", expect] }
        if dryRun { args.append("--dry-run") }
        return try await decodeOrRefusal(EditResult.self, args, in: (project as NSString).deletingLastPathComponent)
    }

    /// `ladder stamp --steps`: approve chosen steps and data blocks.
    func approve(_ project: String, ids: [String], dryRun: Bool) async throws -> StampResult {
        var args = ["stamp", project, "--steps", ids.joined(separator: ","), "--json"]
        if dryRun { args.append("--dry-run") }
        return try await decodeOrRefusal(StampResult.self, args, in: (project as NSString).deletingLastPathComponent)
    }

    /// `ladder retag`: the English was reworded without changing behavior; mark the code current.
    func retag(_ project: String, ids: [String]) async throws {
        _ = try await run(["retag", project, ids.joined(separator: ",")], in: (project as NSString).deletingLastPathComponent,
                          acceptedStatuses: [0])
    }

    func version() async -> String? {
        guard let data = try? await run(["--version"], acceptedStatuses: [0]) else { return nil }
        return String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: finding the tool

    /// Where the tool is, in order: the app's setting, $LADDER_TOOL, `ladder` on the login shell's PATH, then the
    /// newest Ladder plugin Claude Code installed.
    static func locate(setting: String?) async -> String? {
        let fm = FileManager.default
        if let setting, !setting.isEmpty, fm.fileExists(atPath: (setting as NSString).expandingTildeInPath) {
            return (setting as NSString).expandingTildeInPath
        }
        if let env = ProcessInfo.processInfo.environment["LADDER_TOOL"], fm.fileExists(atPath: env) { return env }
        if let out = try? await Shell.run("/bin/zsh", ["-lc", "command -v ladder"]), out.status == 0,
           let p = String(data: out.stdout, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
           !p.isEmpty, fm.isExecutableFile(atPath: p) {
            return p
        }
        return newestPluginTool()
    }

    /// The most recently modified `ladder/tool/ladder.py` under ~/.claude/plugins.
    static func newestPluginTool() -> String? {
        let fm = FileManager.default
        let plugins = (NSHomeDirectory() as NSString).appendingPathComponent(".claude/plugins")
        var best: (String, Date)?
        for rel in fm.enumerator(atPath: plugins)?.allObjects as? [String] ?? []
        where rel.hasSuffix("ladder/tool/ladder.py") {
            let full = (plugins as NSString).appendingPathComponent(rel)
            let date = (try? fm.attributesOfItem(atPath: full)[.modificationDate] as? Date) ?? .distantPast
            if best == nil || date > best!.1 { best = (full, date) }
        }
        return best?.0
    }
}

/// Runs a process with the user's login-shell PATH (an app started from Finder gets a bare PATH without Homebrew's
/// python3 or git), reading stdout and stderr as they come so a large export cannot fill a pipe and hang.
enum Shell {
    private static let loginPath: String = {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/zsh")
        p.arguments = ["-lc", "printf %s \"$PATH\""]
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = FileHandle.nullDevice
        guard (try? p.run()) != nil else { return "/usr/bin:/bin:/usr/sbin:/sbin" }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        let path = String(data: data, encoding: .utf8) ?? ""
        return path.isEmpty ? "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" : path
    }()

    static func run(_ executable: String, _ arguments: [String], in folder: String? = nil) async throws -> LadderTool.Output {
        try await withCheckedThrowingContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                let p = Process()
                p.executableURL = URL(fileURLWithPath: executable)
                p.arguments = arguments
                if let folder { p.currentDirectoryURL = URL(fileURLWithPath: folder) }
                var env = ProcessInfo.processInfo.environment
                env["PATH"] = loginPath
                p.environment = env
                let out = Pipe(), err = Pipe()
                p.standardOutput = out
                p.standardError = err
                p.standardInput = FileHandle.nullDevice
                let errData = LockedData()
                err.fileHandleForReading.readabilityHandler = { h in errData.append(h.availableData) }
                do {
                    try p.run()
                } catch {
                    err.fileHandleForReading.readabilityHandler = nil
                    cont.resume(throwing: error)
                    return
                }
                let stdout = out.fileHandleForReading.readDataToEndOfFile()
                p.waitUntilExit()
                err.fileHandleForReading.readabilityHandler = nil
                errData.append(err.fileHandleForReading.readDataToEndOfFile())
                cont.resume(returning: LadderTool.Output(status: p.terminationStatus, stdout: stdout,
                                                         stderr: String(data: errData.value, encoding: .utf8) ?? ""))
            }
        }
    }

    /// Run a command and ignore its result (opening an editor).
    static func launch(_ executable: String, _ arguments: [String]) {
        Task.detached { _ = try? await run(executable, arguments) }
    }
}

final class LockedData: @unchecked Sendable {
    private var data = Data()
    private let lock = NSLock()
    func append(_ d: Data) { lock.lock(); data.append(d); lock.unlock() }
    var value: Data { lock.lock(); defer { lock.unlock() }; return data }
}
