import SwiftUI

/// The repo as files (from git), with Ladder status on tagged code files (SPEC: Project navigator).
struct FileNavigator: View {
    @Environment(RepoStore.self) private var store
    var filter: String

    struct Node: Identifiable, Hashable {
        var name: String
        var path: String              // repo-relative
        var children: [Node]?
        var id: String { path }
    }

    /// How many steps a code file implements and how many of its regions have a problem.
    struct Status { var steps = 0; var problems = 0 }

    var body: some View {
        let status = fileStatus()
        if filter.isEmpty {
            OutlineGroup(tree(store.files), children: \.children) { node in
                row(node, status: status)
            }
        } else {
            let matches = FuzzyMatch.rank(filter, store.files, limit: 200)
            ForEach(matches, id: \.self) { rel in
                row(Node(name: rel, path: rel, children: nil), status: status)
            }
        }
    }

    @ViewBuilder private func row(_ node: Node, status: [String: Status]) -> some View {
        if node.children != nil {
            Label(node.name, systemImage: "folder")
        } else {
            let abs = absolute(node.path)
            let s = status[abs]
            HStack(spacing: 6) {
                Image(systemName: icon(node.name)).foregroundStyle(.secondary).frame(width: 14)
                Text(node.name).lineLimit(1).truncationMode(.middle)
                Spacer()
                if let s {
                    if s.problems > 0 {
                        Image(systemName: "exclamationmark.circle.fill").foregroundStyle(.orange).font(.caption)
                    }
                    Text("\(s.steps)").font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                        .help("\(s.steps) steps tagged in this file" + (s.problems > 0 ? ", \(s.problems) regions need attention" : ""))
                }
            }
            .tag(Route.file(abs, line: nil))
        }
    }

    private func absolute(_ rel: String) -> String {
        store.root.map { $0.appendingPathComponent(rel).standardizedFileURL.path } ?? rel
    }

    private func icon(_ name: String) -> String {
        if name.hasSuffix(".ladder") { return "list.bullet.indent" }
        if name.hasSuffix(".json") { return "curlybraces" }
        if name.hasSuffix(".md") { return "doc.richtext" }
        return "doc.text"
    }

    private func fileStatus() -> [String: Status] {
        var out: [String: Status] = [:]
        for p in store.projects {
            for b in p.export?.builds ?? [] {
                for f in b.files {
                    var s = out[f.absolute] ?? Status()
                    s.steps += Set(f.regions.flatMap(\.steps)).count
                    s.problems += f.regions.filter { !$0.problems.isEmpty || $0.isStale }.count
                    out[f.absolute] = s
                }
            }
        }
        return out
    }

    private func tree(_ paths: [String]) -> [Node] {
        final class Dir { var dirs: [String: Dir] = [:]; var files: [String] = [] }
        let top = Dir()
        for p in paths {
            var d = top
            let parts = p.split(separator: "/").map(String.init)
            for part in parts.dropLast() {
                if d.dirs[part] == nil { d.dirs[part] = Dir() }
                d = d.dirs[part]!
            }
            if let last = parts.last { d.files.append(last) }
        }
        func build(_ d: Dir, _ prefix: String) -> [Node] {
            let dirs = d.dirs.keys.sorted { $0.localizedStandardCompare($1) == .orderedAscending }.map { name in
                Node(name: name, path: prefix + name, children: build(d.dirs[name]!, prefix + name + "/"))
            }
            let files = d.files.sorted { $0.localizedStandardCompare($1) == .orderedAscending }.map {
                Node(name: $0, path: prefix + $0, children: nil)
            }
            return dirs + files
        }
        return build(top, "")
    }
}

/// Fuzzy file-name matching: every query character in order, scored so matches in the file name, at word starts and
/// in runs rank first (`reqperm` finds `useRequirePermission.ts`).
enum FuzzyMatch {
    static func score(_ query: String, _ candidate: String) -> Int? {
        let q = Array(query.lowercased().filter { !$0.isWhitespace })
        guard !q.isEmpty else { return 0 }
        let c = Array(candidate)
        let lower = Array(candidate.lowercased())
        let nameStart = (candidate.lastIndex(of: "/").map { candidate.distance(from: candidate.startIndex, to: $0) + 1 }) ?? 0
        var qi = 0, score = 0, last = -2
        for (i, ch) in lower.enumerated() where qi < q.count && ch == q[qi] {
            var s = 1
            if i == last + 1 { s += 4 }
            if i >= nameStart { s += 2 }
            if i == 0 || "/_-. ".contains(c[i - 1]) || (c[i].isUppercase && c[i - 1].isLowercase) { s += 3 }
            score += s
            last = i
            qi += 1
        }
        guard qi == q.count else { return nil }
        return score * 100 - candidate.count
    }

    static func rank(_ query: String, _ candidates: [String], limit: Int) -> [String] {
        candidates.compactMap { c in score(query, c).map { (c, $0) } }
            .sorted { $0.1 > $1.1 }
            .prefix(limit)
            .map(\.0)
    }
}
