import AppKit
import Foundation
import Observation

/// Where the main pane is.
enum Route: Hashable {
    case home
    case project(String)                         // ladder.json path
    case step(project: String, id: String)
    case data(project: String, name: String)
    case file(String, line: Int?)                // absolute path
}

/// One Ladder project as the tool reports it.
struct ProjectState: Identifiable {
    var entry: ProjectEntry
    var export: ExportDoc?
    var report: CheckReport?
    var attention = ProjectAttention()
    var error: String?
    var loading = false

    var id: String { entry.path }
    var steps: [String: Step] { Dictionary((export?.steps ?? []).map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a }) }
    var roots: [Step] { (export?.steps ?? []).filter { $0.parent == nil } }

    /// Regions in every build that carry a step's tag, with the build and file they are in.
    func regions(for step: String) -> [(build: Build, file: BuildFile, region: Region)] {
        var out: [(Build, BuildFile, Region)] = []
        for b in export?.builds ?? [] {
            for f in b.files { for r in f.regions where r.steps.contains(step) { out.append((b, f, r)) } }
        }
        return out
    }
}

/// The open repository: its projects, what the tool says about each, and the files git knows. Everything here is
/// rebuilt from the repo through the tool; quitting loses nothing (SPEC: "Files and git are the truth").
@Observable @MainActor
final class RepoStore {
    var root: URL?
    var repoFile: String?
    var projects: [ProjectState] = []
    var files: [String] = []                     // repo-relative paths from git
    /// Where the main pane is. Every change (sidebar, a link in the English, Home, search) is recorded, so Back
    /// returns to the screen before it, like a browser.
    var route: Route? = .home {
        didSet {
            guard !navigating, let old = oldValue, route != nil, route != old else { return }
            backStack.append(old)
            if backStack.count > 200 { backStack.removeFirst() }
            forwardStack.removeAll()
        }
    }
    private(set) var backStack: [Route] = []
    private(set) var forwardStack: [Route] = []
    @ObservationIgnored private var navigating = false

    var canGoBack: Bool { !backStack.isEmpty }
    var canGoForward: Bool { !forwardStack.isEmpty }

    func goBack() {
        guard let target = backStack.popLast() else { return }
        if let current = route { forwardStack.append(current) }
        move(to: target)
    }

    func goForward() {
        guard let target = forwardStack.popLast() else { return }
        if let current = route { backStack.append(current) }
        move(to: target)
    }

    private func move(to target: Route) {
        navigating = true
        route = target
        navigating = false
    }

    /// A short name for a screen, for the Back and Forward buttons' tooltips.
    func describe(_ r: Route) -> String {
        switch r {
        case .home: return "Home"
        case .project(let p): return project(p)?.entry.title ?? "project"
        case .step(let p, let id): return "\(id) \(project(p)?.steps[id]?.title ?? "")"
        case .data(_, let name): return "data \(name)"
        case .file(let path, _): return (path as NSString).lastPathComponent
        }
    }
    var toolPath: String?
    var toolVersion: String?
    var error: String?
    var loading = false
    var since: String = ""                       // compare with a git ref instead of the last approval
    var searchShown = false
    var snapshotEditing = false                  // --snapshot: open the step page in edit mode

    @ObservationIgnored private var watcher: FileWatcher?
    @ObservationIgnored private var pendingReload: Task<Void, Never>?

    var tool: LadderTool? { toolPath.map(LadderTool.init(path:)) }

    func project(_ path: String) -> ProjectState? { projects.first { $0.entry.path == path } }

    var allItems: [AttentionItem] { projects.flatMap(\.attention.items) }

    // MARK: opening and loading

    func open(_ url: URL) async {
        root = url
        UserDefaults.standard.set(url.path, forKey: "lastRepository")
        NSDocumentController.shared.noteNewRecentDocumentURL(url)
        route = .home
        watcher = FileWatcher(path: url.path) { [weak self] changed in
            Task { @MainActor in self?.filesChanged(changed) }
        }
        await reloadAll()
    }

    func findTool() async {
        toolPath = await LadderTool.locate(setting: UserDefaults.standard.string(forKey: "toolPath"))
        toolVersion = await tool?.version()
    }

    func reloadAll() async {
        guard let root else { return }
        if toolPath == nil { await findTool() }
        guard let tool else {
            error = "The ladder tool was not found. Set its path in Settings (the plugin's tool/ladder.py, or a "
                + "`ladder` executable), or set LADDER_TOOL."
            return
        }
        loading = true
        defer { loading = false }
        error = nil
        do {
            let list = try await tool.projects(in: root.path)
            repoFile = list.repoFile
            let old = Dictionary(projects.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
            projects = list.projects.map { e in
                var p = old[e.path] ?? ProjectState(entry: e)
                p.entry = e
                return p
            }
        } catch {
            self.error = error.localizedDescription
            return
        }
        files = await gitFiles(root.path)
        await reload(projects.map(\.id))
    }

    /// Reload projects, a few at a time: each is a Python process, and a repository can hold hundreds of projects.
    func reload(_ paths: [String], concurrency: Int = 6) async {
        await withTaskGroup(of: Void.self) { group in
            var next = paths.makeIterator()
            for _ in 0..<concurrency {
                guard let p = next.next() else { break }
                group.addTask { await self.reload(p) }
            }
            while await group.next() != nil {
                if let p = next.next() { group.addTask { await self.reload(p) } }
            }
        }
    }

    func reload(_ path: String) async {
        guard let tool, let i = projects.firstIndex(where: { $0.id == path }) else { return }
        let entry = projects[i].entry
        if let e = entry.error {
            projects[i].error = e
            return
        }
        projects[i].loading = true
        let ex = await Result<ExportDoc, Error>(catching: { try await tool.export(entry.path, since: since) })
        guard let j = projects.firstIndex(where: { $0.id == path }) else { return }
        projects[j].loading = false
        projects[j].export = try? ex.get()
        projects[j].report = projects[j].export?.check
        projects[j].error = ex.failure?.localizedDescription
        projects[j].attention = ProjectAttention(project: entry, export: projects[j].export, report: projects[j].report)
    }

    private func gitFiles(_ folder: String) async -> [String] {
        guard let out = try? await Shell.run("/usr/bin/env", ["git", "-C", folder, "ls-files", "--cached", "--others",
                                                               "--exclude-standard"]),
              out.status == 0, let text = String(data: out.stdout, encoding: .utf8) else {
            return []
        }
        return text.split(separator: "\n").map(String.init)
    }

    /// The app watches the repo; a change to a project's English, settings, lock or code reloads that project
    /// (SPEC: "External changes win"). A new or removed ladder.json reloads everything.
    private func filesChanged(_ paths: [String]) {
        let relevant = paths.filter { !$0.contains("/.git/") && !$0.contains("/.ladder/") && !$0.contains("/node_modules/") }
        guard !relevant.isEmpty else { return }
        pendingReload?.cancel()
        pendingReload = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(400))
            guard !Task.isCancelled, let self else { return }
            if relevant.contains(where: { $0.hasSuffix("/ladder.json") || $0.hasSuffix("/ladder.repo.json") }) {
                await self.reloadAll()
                return
            }
            // Linked projects read each other's trees, so any Ladder change can matter to every project.
            if relevant.contains(where: { $0.hasSuffix(".ladder") || $0.hasSuffix("ladder.lock.json") }) {
                await self.reloadAll()
                return
            }
            let touched = self.projects.filter { p in
                relevant.contains { $0.hasPrefix(p.entry.folder + "/") || self.isBuildFile($0, of: p) }
            }
            await self.reload(touched.map(\.id))
        }
    }

    private func isBuildFile(_ path: String, of p: ProjectState) -> Bool {
        p.export?.builds?.contains { $0.files.contains { $0.absolute == path } } ?? false
    }

    // MARK: lookups across projects

    /// The project and step a `calls:` alias and id point at.
    func linkTarget(from project: ProjectState, alias: String, id: String) -> (ProjectState, Step)? {
        guard let path = project.entry.links?[alias], let target = self.project(path),
              let step = target.steps[id] else { return nil }
        return (target, step)
    }

    /// Steps in other projects whose `calls:` lines name this step.
    func callers(of id: String, in project: ProjectState) -> [(ProjectState, Step)] {
        var out: [(ProjectState, Step)] = []
        for p in projects where p.id != project.id {
            for s in p.export?.steps ?? [] {
                for (alias, ids) in s.callTargets where ids.contains(id) && p.entry.links?[alias] == project.id {
                    out.append((p, s))
                }
            }
        }
        return out
    }

    /// The regions, across all projects, that cover a code file.
    func regions(inFile path: String) -> [(project: ProjectState, build: Build, region: Region)] {
        var out: [(ProjectState, Build, Region)] = []
        for p in projects {
            for b in p.export?.builds ?? [] {
                for f in b.files where f.absolute == path { for r in f.regions { out.append((p, b, r)) } }
            }
        }
        return out
    }

    func relative(_ path: String) -> String {
        guard let root else { return path }
        let base = root.path.hasSuffix("/") ? root.path : root.path + "/"
        return path.hasPrefix(base) ? String(path.dropFirst(base.count)) : path
    }

    // MARK: opening code in an editor

    func openInEditor(_ path: String, line: Int?) {
        let editor = UserDefaults.standard.string(forKey: "editor") ?? "default"
        let line = max(line ?? 1, 1)
        switch editor {
        case "xcode": Shell.launch("/usr/bin/env", ["xed", "--line", String(line), path])
        case "vscode": Shell.launch("/usr/bin/env", ["code", "--goto", "\(path):\(line)"])
        case "cursor": Shell.launch("/usr/bin/env", ["cursor", "--goto", "\(path):\(line)"])
        default: NSWorkspace.shared.open(URL(fileURLWithPath: path))
        }
    }
}

extension Result where Failure == Error {
    init(catching body: () async throws -> Success) async {
        do { self = .success(try await body()) } catch { self = .failure(error) }
    }

    var failure: Error? {
        if case .failure(let e) = self { return e }
        return nil
    }
}
