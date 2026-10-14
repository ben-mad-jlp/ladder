import SwiftUI

/// Home: one list across all projects of what needs a person, grouped by level, then kind (SPEC: Home).
struct HomeView: View {
    @Environment(RepoStore.self) private var store
    @State private var showWarnings = false
    @State private var projectFilter: String? = nil

    var body: some View {
        let items = store.allItems.filter { projectFilter == nil || $0.project == projectFilter }
        let shownLevels = AttentionItem.Level.allCases.filter { $0 != .warning || showWarnings }
        // A scroll view, not a List: Home is a report whose rows change as projects load, and an NSTableView
        // updated mid-layout warns of reentrant delegate calls.
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 4) {
                SummaryRow()
                Divider().padding(.bottom, 8)
                if items.filter({ $0.level != .warning }).isEmpty {
                    Label(store.projects.isEmpty ? "No Ladder projects found in this folder."
                          : "Nothing needs you: every project is approved, current and checked.",
                          systemImage: store.projects.isEmpty ? "questionmark.folder" : "checkmark.seal")
                        .foregroundStyle(.secondary)
                }
                ForEach(shownLevels, id: \.self) { level in
                    let group = items.filter { $0.level == level }
                    if !group.isEmpty {
                        HStack(alignment: .firstTextBaseline) {
                            Text("\(level.title) (\(group.count))").font(.headline)
                            Text(LocalizedStringKey(level.caption)).foregroundStyle(.secondary).font(.caption)
                        }
                        .padding(.top, 14)
                        ForEach(kinds(group), id: \.self) { kind in
                            KindGroup(kind: kind, rows: group.filter { $0.kind == kind })
                            Divider()
                        }
                    }
                }
            }
            .padding()
        }
        .toolbar {
            ToolbarItemGroup(placement: .secondaryAction) {
                Picker("Project", selection: $projectFilter) {
                    Text("All projects").tag(String?.none)
                    ForEach(store.projects) { Text($0.entry.title).tag(Optional($0.id)) }
                }
                Toggle("Warnings", isOn: $showWarnings)
            }
        }
        .navigationTitle("What needs you")
    }

    private func kinds(_ items: [AttentionItem]) -> [String] {
        var counts: [String: Int] = [:]
        for i in items { counts[i.kind, default: 0] += 1 }
        return counts.keys.sorted { (counts[$0]!, $1) > (counts[$1]!, $0) }
    }
}

struct SummaryRow: View {
    @Environment(RepoStore.self) private var store
    var body: some View {
        let ps = store.projects
        let by = Dictionary(grouping: ps, by: { $0.report?.status ?? ($0.error != nil ? "error" : "loading") })
        HStack(spacing: 18) {
            stat("\(ps.count)", "projects", .primary)
            stat("\(by["ok"]?.count ?? 0)", "ok", .green)
            stat("\(by["awaiting-approval"]?.count ?? 0)", "awaiting approval", .blue)
            stat("\(by["problems"]?.count ?? 0)", "with problems", .red)
            if let e = by["error"]?.count, e > 0 { stat("\(e)", "unreadable", .orange) }
            Spacer()
            if let v = store.toolVersion {
                Text(v).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .padding(.vertical, 4)
    }

    private func stat(_ n: String, _ label: String, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(n).font(.title2.monospacedDigit().weight(.semibold)).foregroundStyle(color)
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
    }
}

struct KindGroup: View {
    var kind: String
    var rows: [AttentionItem]
    @State private var expanded = true
    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 6) {
                ForEach(rows) { AttentionRow(item: $0) }
            }
            .padding(.vertical, 4)
        } label: {
            KindHeader(kind: kind, count: rows.count, resolvedBy: rows[0].resolvedBy)
        }
    }
}

struct KindHeader: View {
    var kind: String
    var count: Int
    var resolvedBy: String
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(kind).font(.body.monospaced().weight(.medium))
            CountBadge(count: count)
            Spacer()
            Text(LocalizedStringKey("resolved by " + resolvedBy)).font(.caption).foregroundStyle(.secondary)
                .lineLimit(1)
        }
    }
}

struct AttentionRow: View {
    @Environment(RepoStore.self) private var store
    var item: AttentionItem

    var body: some View {
        Button(action: go) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(item.projectName).font(.caption).foregroundStyle(.secondary).frame(width: 110, alignment: .leading)
                    .lineLimit(1).truncationMode(.head)
                if !item.nodes.isEmpty {
                    Text(item.nodes.prefix(3).map { "[\($0)]" }.joined(separator: " ")
                         + (item.nodes.count > 3 ? " +\(item.nodes.count - 3)" : ""))
                        .font(.caption.monospaced())
                }
                Text(item.message).lineLimit(3).foregroundStyle(.primary)
                Spacer(minLength: 0)
                if let f = item.file {
                    Text("\((f as NSString).lastPathComponent)\(item.line.map { ":\($0)" } ?? "")")
                        .font(.caption.monospaced()).foregroundStyle(.secondary)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .textSelection(.enabled)
    }

    private func go() {
        guard let p = store.project(item.project) else { return }
        if let n = item.nodes.first(where: { p.steps[$0] != nil }) {
            store.route = .step(project: p.id, id: n)
        } else if let n = item.nodes.first(where: { name in p.export?.data.contains { $0.name == name } ?? false }) {
            store.route = .data(project: p.id, name: n)
        } else if let f = item.file {
            store.route = .file(f, line: item.line)
        } else {
            store.route = .project(p.id)
        }
    }
}

/// A project's overview: its builds and their files, and its own Home items.
struct ProjectView: View {
    @Environment(RepoStore.self) private var store
    var path: String
    @State private var approving: ApproveRequest?

    var body: some View {
        if let p = store.project(path) {
            List {
                Section("Project") {
                    LabeledContent("Settings", value: store.relative(p.entry.path))
                    if let t = p.entry.tree { LabeledContent("English", value: store.relative(t)) }
                    LabeledContent("Status", value: p.report?.status ?? (p.loading ? "checking…" : "not checked"))
                    if let b = p.report?.baseline { LabeledContent("Compared with", value: b) }
                    LabeledContent("Steps", value: "\(p.export?.steps.count ?? 0)")
                    if let links = p.entry.links, !links.isEmpty {
                        LabeledContent("Links", value: links.keys.sorted().joined(separator: ", "))
                    }
                    if let e = p.error { Text(e).foregroundStyle(.red).textSelection(.enabled) }
                    let waiting = p.waitingIDs
                    if !waiting.isEmpty {
                        Button("Approve everything waiting (\(waiting.count))…") {
                            approving = ApproveRequest(project: p.id, title: "Approve everything waiting in \(p.entry.title)",
                                                       ids: waiting)
                        }
                    }
                }
                ForEach(p.export?.builds ?? []) { b in
                    Section("Build \(b.name) (\(b.lang)\(b.mode.isEmpty ? "" : ", " + b.mode))") {
                        ForEach(b.files, id: \.path) { f in
                            Button {
                                store.route = .file(f.absolute, line: nil)
                            } label: {
                                HStack {
                                    Image(systemName: f.exists ? "doc.text" : "doc.badge.ellipsis")
                                    Text(f.path).font(.body.monospaced())
                                    Spacer()
                                    if !f.exists { Text("missing").foregroundStyle(.red) }
                                    Text("\(f.regions.filter { $0.kind == "node" }.count) regions")
                                        .foregroundStyle(.secondary).font(.caption)
                                }
                            }
                            .buttonStyle(.plain)
                            .disabled(!f.exists)
                        }
                    }
                }
                let items = p.attention.items.sorted { $0.level < $1.level }
                if !items.isEmpty {
                    Section("Needs attention") {
                        ForEach(items) { AttentionRow(item: $0) }
                    }
                }
            }
            .navigationTitle(p.entry.title)
            .sheet(item: $approving) { req in ApproveSheet(request: req).environment(store) }
        } else {
            ContentUnavailableView("Project not found", systemImage: "questionmark.folder")
        }
    }
}
