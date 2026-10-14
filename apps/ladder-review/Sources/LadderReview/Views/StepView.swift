import SwiftUI

/// The step page: the English first; code, links and what needs attention one click away (SPEC: Step page).
struct StepView: View {
    @Environment(RepoStore.self) private var store
    var projectPath: String
    var stepID: String
    @AppStorage("stepTab") private var tab = "english"
    @State private var session: EditSession?
    @State private var answering: AnswerRequest?
    @State private var approving: ApproveRequest?

    var body: some View {
        if let p = store.project(projectPath), let step = p.steps[stepID] {
            VStack(alignment: .leading, spacing: 0) {
                header(p, step)
                Picker("", selection: $tab) {
                    Text("English").tag("english")
                    Text("Code (\(p.regions(for: step.id).count))").tag("code")
                    Text("Links and schema").tag("links")
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .padding(.horizontal)
                .padding(.bottom, 8)
                Divider()
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        switch tab {
                        case "code": StepCodeTab(project: p, step: step)
                        case "links": StepLinksTab(project: p, step: step)
                        default:
                            if let session {
                                StepEditor(project: p, session: session)
                            } else {
                                StepEnglishTab(project: p, step: step) { n in
                                    answering = AnswerRequest(step: step, noteNumber: n, note: Note(raw: step.notes[n - 1]))
                                }
                            }
                        }
                    }
                    .padding()
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .navigationTitle("\(step.id) \(step.title)")
            .onAppear { if store.snapshotEditing { startEditing(p, step) } }
            .sheet(item: Binding(get: { session?.review }, set: { session?.review = $0 })) { change in
                ChangeReviewSheet(change: change) { session = nil }.environment(store)
            }
            .sheet(item: $answering) { req in
                AnswerSheet(project: p, request: req) { startEditing(p, step) }.environment(store)
            }
            .sheet(item: $approving) { req in ApproveSheet(request: req).environment(store) }
            .environment(\.openURL, OpenURLAction { url in follow(url, from: p) })
        } else {
            ContentUnavailableView("Step \(stepID) is not in this project any more", systemImage: "questionmark.circle",
                                   description: Text("It may have been removed or renumbered. Reload, or go Home."))
        }
    }

    private func header(_ p: ProjectState, _ step: Step) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Button(p.entry.title) { store.route = .project(p.id) }.buttonStyle(.link)
                ForEach(ancestors(step, in: p), id: \.id) { a in
                    Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary)
                    Button(a.id) { store.route = .step(project: p.id, id: a.id) }.buttonStyle(.link)
                        .font(.callout.monospaced())
                }
            }
            .font(.callout)
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                let badge = p.attention.badge(for: step.id)
                Text(step.id).font(.title3.monospaced()).foregroundStyle(.secondary)
                Text(step.title).font(.title2.weight(.semibold)).textSelection(.enabled)
                Spacer()
                Label(badge.label, systemImage: badge.symbol).foregroundStyle(badge.color).font(.callout)
                if let session {
                    // While editing, Edit becomes Cancel and Review change…
                    Button("Cancel", role: .cancel) { self.session = nil }
                        .keyboardShortcut(.cancelAction)
                        .help("Leave edit mode without saving")
                    Button {
                        Task { await session.preview(with: store.tool) }
                    } label: { Label("Review change…", systemImage: "doc.text.magnifyingglass") }
                        .keyboardShortcut(.defaultAction)
                        .disabled(!session.hasChanges || session.working)
                        .help("See the diff and what it makes stale, then save")
                } else {
                    Button { startEditing(p, step) } label: { Label("Edit", systemImage: "pencil") }
                        .help("Edit this step's English here; the change is shown with what it makes stale before it is saved")
                    approveMenu(p, step)
                }
                Menu {
                    Button("Open the .ladder file in your editor") {
                        if let t = p.entry.tree { store.openInEditor(t, line: step.line) }
                    }
                } label: { Image(systemName: "ellipsis.circle") }
                    .menuIndicator(.hidden)
                    .fixedSize()
            }
            ForEach(p.attention.byStep[step.id] ?? []) { item in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    BadgeIcon(badge: StepBadge.from(kind: item.kind, level: item.level))
                    Text(item.kind).font(.caption.monospaced().weight(.semibold))
                    Text(item.message).font(.callout).textSelection(.enabled)
                    Spacer(minLength: 0)
                    Text(LocalizedStringKey("→ " + item.resolvedBy)).font(.caption).foregroundStyle(.secondary)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 5)
                .background(StepBadge.from(kind: item.kind, level: item.level).color.opacity(0.08),
                            in: RoundedRectangle(cornerRadius: 6))
            }
        }
        .padding()
    }

    private func startEditing(_ p: ProjectState, _ step: Step) {
        tab = "english"
        session = EditSession(project: p.id, step: step)
    }

    /// Approve this step, this step with its parts, or everything waiting in the project.
    private func approveMenu(_ p: ProjectState, _ step: Step) -> some View {
        let waiting = p.waitingIDs
        let below = descendants(step, in: p).map(\.id).filter { waiting.contains($0) }
        return Menu {
            Button("This step") {
                approving = ApproveRequest(project: p.id, title: "Approve [\(step.id)]", ids: [step.id])
            }
            if !below.isEmpty {
                Button("This step and its \(below.count) waiting part\(below.count == 1 ? "" : "s")") {
                    approving = ApproveRequest(project: p.id, title: "Approve [\(step.id)] and its parts",
                                               ids: [step.id] + below)
                }
            }
            if !waiting.isEmpty {
                Button("Everything waiting in \(p.entry.title) (\(waiting.count))") {
                    approving = ApproveRequest(project: p.id, title: "Approve everything waiting in \(p.entry.title)",
                                               ids: waiting)
                }
            }
        } label: {
            Label("Approve", systemImage: "checkmark.seal")
        }
        .fixedSize()
        .help("Record that you read this English and agree with it (`ladder stamp --steps`)")
    }

    private func descendants(_ step: Step, in p: ProjectState) -> [Step] {
        let steps = p.steps
        var out: [Step] = []
        var queue = step.children
        while !queue.isEmpty {
            let id = queue.removeFirst()
            if let s = steps[id] { out.append(s); queue += s.children }
        }
        return out
    }

    private func ancestors(_ step: Step, in p: ProjectState) -> [Step] {
        var out: [Step] = []
        var cur = step.parent
        let steps = p.steps
        while let id = cur, let s = steps[id] { out.insert(s, at: 0); cur = s.parent }
        return out
    }

    /// Links inside rendered English: ladder://step/<id> and ladder://data/<name> within this project.
    private func follow(_ url: URL, from p: ProjectState) -> OpenURLAction.Result {
        guard url.scheme == "ladder" else { return .systemAction }
        let target = url.pathComponents.dropFirst().joined(separator: "/")
        switch url.host {
        case "step": store.route = .step(project: p.id, id: target)
        case "data": store.route = .data(project: p.id, name: target)
        default: return .discarded
        }
        return .handled
    }
}

// MARK: English

struct StepEnglishTab: View {
    var project: ProjectState
    var step: Step
    var answer: (Int) -> Void = { _ in }

    var body: some View {
        let text = EnglishText(project: project)
        VStack(alignment: .leading, spacing: 14) {
            Grid(alignment: .topLeading, horizontalSpacing: 12, verticalSpacing: 6) {
                if !step.inputs.isEmpty { row("in", text.render(step.inputs)) }
                if !step.outputs.isEmpty { row("out", text.render(step.outputs)) }
                if !step.effects.isEmpty { row("effects", text.render(step.effects)) }
                if !step.uses.isEmpty { row("uses", AttributedString(step.uses.joined(separator: "; "))) }
            }
            if !step.how.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(Array(step.how.enumerated()), id: \.offset) { i, line in
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text("\(i + 1).").font(.callout.monospacedDigit()).foregroundStyle(.tertiary)
                                .frame(width: 24, alignment: .trailing)
                            Text(text.render(line)).textSelection(.enabled)
                        }
                    }
                }
            }
            if !step.children.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Parts").font(.headline)
                    let steps = project.steps
                    ForEach(step.children.compactMap { steps[$0] }) { c in
                        StepLinkRow(project: project, step: c)
                    }
                }
            }
            if !step.notes.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Notes").font(.headline)
                    ForEach(Array(step.notes.enumerated()), id: \.offset) { i, raw in
                        NoteCard(note: Note(raw: raw), text: text, answer: { answer(i + 1) })
                    }
                }
            }
            if !step.compare.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Compare").font(.headline)
                    ForEach(step.compare, id: \.self) { Text($0).font(.callout.monospaced()) }
                    Text("How results are compared between builds; not part of the step's hash.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            HStack {
                Text("hash \(step.hash)")
                Text("line \(step.line)")
                if let by = step.approvedBy {
                    Text("approved by \(by)" + (step.approvedAt.map { " on \($0.prefix(10))" } ?? ""))
                }
            }
            .font(.caption.monospaced())
            .foregroundStyle(.tertiary)
        }
    }

    private func row(_ label: String, _ value: AttributedString) -> some View {
        GridRow {
            Text(label + ":").font(.callout.monospaced()).foregroundStyle(.secondary)
            Text(value).textSelection(.enabled)
        }
    }
}

struct StepLinkRow: View {
    @Environment(RepoStore.self) private var store
    var project: ProjectState
    var step: Step
    var body: some View {
        Button {
            store.route = .step(project: project.id, id: step.id)
        } label: {
            HStack(spacing: 6) {
                BadgeIcon(badge: project.attention.badge(for: step.id))
                Text(step.id).font(.callout.monospaced()).foregroundStyle(.secondary)
                Text(step.title)
                if project.id != store.route.flatMap(currentProject) {
                    Text(project.entry.title).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .buttonStyle(.plain)
    }

    private func currentProject(_ r: Route) -> String? {
        if case .step(let p, _) = r { return p }
        return nil
    }
}

struct NoteCard: View {
    var note: Note
    var text: EnglishText
    var answer: (() -> Void)? = nil

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if note.kind != .plain {
                Text(note.kind == .answered ? "ANSWERED" : note.kind.rawValue)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(note.isOpen ? Color.purple : Color.secondary)
            }
            Text(text.render(note.text)).textSelection(.enabled)
            Spacer(minLength: 0)
            if let answer, note.isOpen, note.kind != .answered {
                Button("Answer…", action: answer).controlSize(.small)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(note.isOpen ? Color.purple.opacity(0.08) : Color.secondary.opacity(0.06),
                    in: RoundedRectangle(cornerRadius: 6))
    }
}

extension Note {
    init(raw: String) { self = Note(raw)! }
}

/// Renders a line of Ladder English: backticked names stay code, and `[id]` of a step in the project and a data block's
/// name become links (SPEC: "field names in backticks link to their data block").
struct EnglishText {
    var project: ProjectState

    func render(_ line: String) -> AttributedString {
        var out = AttributedString()
        let steps = project.steps
        let blocks = Dictionary((project.export?.data ?? []).map { ($0.name, $0) }, uniquingKeysWith: { a, _ in a })
        let fieldOwner: [String: String] = {
            var m: [String: String] = [:]
            for d in project.export?.data ?? [] { for f in d.fields where m[f.name] == nil { m[f.name] = d.name } }
            return m
        }()
        var rest = Substring(line)
        while !rest.isEmpty {
            guard let i = rest.firstIndex(where: { $0 == "`" || $0 == "[" }) else {
                out += AttributedString(String(rest))
                break
            }
            out += AttributedString(String(rest[..<i]))
            let opener = rest[i]
            let closer: Character = opener == "`" ? "`" : "]"
            let after = rest.index(after: i)
            guard let j = rest[after...].firstIndex(of: closer) else {
                out += AttributedString(String(rest[i...]))
                break
            }
            let inner = String(rest[after..<j])
            if opener == "`" {
                var code = AttributedString(inner)
                code.font = .body.monospaced()
                let head = String(inner.split(separator: ".").first ?? "")
                if let owner = blocks[head] != nil ? head : fieldOwner[inner] ?? fieldOwner[head] {
                    code.link = URL(string: "ladder://data/\(owner)")
                } else {
                    code.backgroundColor = .secondary.opacity(0.12)
                }
                out += code
            } else if steps[inner] != nil {
                var ref = AttributedString("[\(inner)]")
                ref.font = .body.monospaced()
                ref.link = URL(string: "ladder://step/\(inner)")
                out += ref
            } else {
                out += AttributedString("[\(inner)]")
            }
            rest = rest[rest.index(after: j)...]
        }
        return out
    }
}

// MARK: Code

struct StepCodeTab: View {
    @Environment(RepoStore.self) private var store
    var project: ProjectState
    var step: Step

    var body: some View {
        let regions = project.regions(for: step.id)
        if regions.isEmpty {
            Label(step.isLeaf ? "No build has a region tagged with this step." :
                    "A parent step: its parts carry the code. Open a part, or a file from the project overview.",
                  systemImage: "doc.text.magnifyingglass")
                .foregroundStyle(.secondary)
        }
        ForEach(Array(regions.enumerated()), id: \.offset) { _, r in
            RegionCard(build: r.build, file: r.file, region: r.region, step: step)
        }
    }
}

struct RegionCard: View {
    @Environment(RepoStore.self) private var store
    @State private var confirmRetag = false
    @State private var retagError: String?
    var build: Build
    var file: BuildFile
    var region: Region
    var step: Step

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Text(build.name).font(.callout.weight(.semibold))
                Text(build.lang).font(.caption).foregroundStyle(.secondary)
                Button("\(store.relative(file.absolute)):\(region.start)–\(region.end)") {
                    store.route = .file(file.absolute, line: region.start)
                }
                .buttonStyle(.link)
                .font(.callout.monospaced())
                if region.steps.count > 1 {
                    Text("shared with " + region.steps.filter { $0 != step.id }.joined(separator: ", "))
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if region.isStale {
                    Chip(text: "stale", color: .orange)
                    Button("Retag…") { confirmRetag = true }
                        .controlSize(.small)
                        .help("The English was only reworded and this code still does what it says: mark it current")
                }
                ForEach(region.problems.filter { !$0.hasPrefix("stale") }, id: \.self) { Chip(text: $0, color: .orange) }
                if !region.isStale && region.problems.isEmpty { Chip(text: "current", color: .green) }
                Button { store.openInEditor(file.absolute, line: region.start) } label: {
                    Image(systemName: "arrow.up.forward.app")
                }
                .help("Open in editor")
            }
            .padding(8)
            if let retagError { Text(retagError).foregroundStyle(.red).font(.caption).padding(.horizontal, 8) }
            Divider()
            CodeLines(path: file.absolute, from: region.start, to: region.end)
        }
        .confirmationDialog("Retag [\(step.id)]?", isPresented: $confirmRetag) {
            Button("Retag: the code still does what the English says") { Task { await retag() } }
        } message: {
            Text("Only when the English was reworded without changing behavior (a clearer sentence, an answered note). "
                 + "If behavior changed, regenerate instead (`ladder regen`).")
        }
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.separator))
    }
}

extension RegionCard {
    func retag() async {
        guard let tool = store.tool,
              let p = store.projects.first(where: { $0.export?.builds?.contains { $0.files.contains(file) } ?? false })
        else { return }
        do {
            try await tool.retag(p.id, ids: [step.id])
            await store.reload(p.id)
        } catch {
            retagError = error.localizedDescription
        }
    }
}

struct Chip: View {
    var text: String
    var color: Color
    var body: some View {
        Text(text)
            .font(.caption.weight(.medium))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .foregroundStyle(color)
            .background(color.opacity(0.12), in: Capsule())
    }
}

/// A range of lines from a code file, numbered.
struct CodeLines: View {
    var path: String
    var from: Int
    var to: Int

    var body: some View {
        let lines = SourceCache.lines(path)
        let range = max(from, 1)...max(min(to, lines.count), max(from, 1))
        ScrollView(.horizontal) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(range), id: \.self) { n in
                    HStack(alignment: .top, spacing: 10) {
                        Text("\(n)").foregroundStyle(.tertiary).frame(width: 40, alignment: .trailing)
                        Text(n <= lines.count ? lines[n - 1] : "").foregroundStyle(isMarker(lines, n) ? .secondary : .primary)
                    }
                }
            }
            .font(.system(.callout, design: .monospaced))
            .textSelection(.enabled)
            .padding(8)
        }
    }

    private func isMarker(_ lines: [String], _ n: Int) -> Bool {
        n <= lines.count && (lines[n - 1].contains("@node ") || lines[n - 1].contains("@end") || lines[n - 1].contains("@support"))
    }
}

/// Reads code files for display. Cleared on every reload so external edits show.
enum SourceCache {
    @MainActor private static var cache: [String: (Date, [String])] = [:]

    @MainActor static func lines(_ path: String) -> [String] {
        let mod = (try? FileManager.default.attributesOfItem(atPath: path)[.modificationDate] as? Date) ?? .distantPast
        if let (d, l) = cache[path], d == mod { return l }
        let text = (try? String(contentsOfFile: path, encoding: .utf8)) ?? ""
        var l = text.components(separatedBy: "\n")
        if l.last == "" { l.removeLast() }
        cache[path] = (mod, l)
        return l
    }
}

// MARK: Links and schema

struct StepLinksTab: View {
    @Environment(RepoStore.self) private var store
    var project: ProjectState
    var step: Step

    var body: some View {
        let callers = store.callers(of: step.id, in: project)
        if step.calls.isEmpty && callers.isEmpty && step.reads.isEmpty && step.writes.isEmpty {
            Label("This step calls no other tree, nothing calls it, and it names no tables.",
                  systemImage: "link").foregroundStyle(.secondary)
        }
        if !step.calls.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Calls").font(.headline)
                ForEach(Array(step.callTargets.enumerated()), id: \.offset) { _, target in
                    ForEach(target.ids, id: \.self) { id in
                        if let (tp, ts) = store.linkTarget(from: project, alias: target.alias, id: id) {
                            ContractCard(project: tp, step: ts)
                        } else {
                            Label("\(target.alias) [\(id)]: not found among the open projects "
                                  + "(check \"links\" in ladder.json)", systemImage: "link.badge.plus")
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        if !callers.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text("Called by").font(.headline)
                ForEach(Array(callers.enumerated()), id: \.offset) { _, c in StepLinkRow(project: c.0, step: c.1) }
            }
        }
        if !step.reads.isEmpty || !step.writes.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text("Schema").font(.headline)
                ForEach(step.reads, id: \.self) { Text("reads: \($0)").font(.callout.monospaced()) }
                ForEach(step.writes, id: \.self) { Text("writes: \($0)").font(.callout.monospaced()) }
                Text("Columns and changes: `ladder schema` and the schema-changed items on Home.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}

/// A linked step's contract: what the caller relies on.
struct ContractCard: View {
    @Environment(RepoStore.self) private var store
    var project: ProjectState
    var step: Step

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            StepLinkRow(project: project, step: step)
            Grid(alignment: .topLeading, horizontalSpacing: 10, verticalSpacing: 2) {
                if !step.inputs.isEmpty { GridRow { k("in"); Text(step.inputs) } }
                if !step.outputs.isEmpty { GridRow { k("out"); Text(step.outputs) } }
                if !step.effects.isEmpty { GridRow { k("effects"); Text(step.effects) } }
            }
            .font(.callout)
            .textSelection(.enabled)
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 6))
    }

    private func k(_ s: String) -> some View { Text(s + ":").font(.callout.monospaced()).foregroundStyle(.secondary) }
}

// MARK: Data blocks

struct DataBlockView: View {
    @Environment(RepoStore.self) private var store
    var projectPath: String
    var name: String

    var body: some View {
        if let p = store.project(projectPath), let d = p.export?.data.first(where: { $0.name == name }) {
            let text = EnglishText(project: p)
            List {
                Section("Fields") {
                    ForEach(d.fields, id: \.name) { f in
                        HStack(alignment: .firstTextBaseline) {
                            Text(f.name).font(.body.monospaced()).frame(minWidth: 140, alignment: .leading)
                            Text(text.render(f.description)).foregroundStyle(.secondary)
                        }
                    }
                }
                if !d.rules.isEmpty {
                    Section("Rules") { ForEach(d.rules, id: \.self) { Text(text.render($0)) } }
                }
                if !d.notes.isEmpty {
                    Section("Notes") { ForEach(d.notes, id: \.self) { NoteCard(note: Note(raw: $0), text: text) } }
                }
                let users = (p.export?.steps ?? []).filter { $0.searchText.contains("`\(d.name)") || $0.searchText.contains(d.name) }
                if !users.isEmpty {
                    Section("Steps that name it") { ForEach(users) { StepLinkRow(project: p, step: $0) } }
                }
            }
            .navigationTitle("data \(d.name)")
            .environment(\.openURL, OpenURLAction { url in
                guard url.scheme == "ladder" else { return .systemAction }
                let target = url.pathComponents.dropFirst().joined(separator: "/")
                store.route = url.host == "step" ? .step(project: p.id, id: target) : .data(project: p.id, name: target)
                return .handled
            })
        } else {
            ContentUnavailableView("No data block \(name)", systemImage: "tablecells")
        }
    }
}
