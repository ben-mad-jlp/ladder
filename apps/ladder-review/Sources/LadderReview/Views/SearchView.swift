import SwiftUI

/// Command-K: step ids, words in the English, notes and file names, grouped by kind (SPEC: Search).
/// v1 searches the projects the app has loaded from `ladder export`; the tool's own index (`ladder index`,
/// `ladder search`) is a later addition.
struct SearchView: View {
    @Environment(RepoStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var selected = 0
    @FocusState private var focused: Bool

    struct Hit: Identifiable {
        enum Kind: String { case step = "Steps", note = "Notes", data = "Data", file = "Files" }
        var id: String
        var kind: Kind
        var title: String
        var detail: String
        var route: Route
    }

    var body: some View {
        let hits = search(query)
        VStack(spacing: 0) {
            HStack {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("Step id, words in the English, a file name…  (note:question, kind:file)", text: $query)
                    .textFieldStyle(.plain)
                    .font(.title3)
                    .focused($focused)
                    .onSubmit { open(hits) }
                    .onChange(of: query) { selected = 0 }
                    .onKeyPress(.downArrow) { selected = min(selected + 1, max(hits.count - 1, 0)); return .handled }
                    .onKeyPress(.upArrow) { selected = max(selected - 1, 0); return .handled }
                    .onKeyPress(.escape) { dismiss(); return .handled }
            }
            .padding(12)
            Divider()
            ScrollViewReader { proxy in
                List {
                    ForEach([Hit.Kind.step, .note, .data, .file], id: \.self) { kind in
                        let group = hits.enumerated().filter { $0.element.kind == kind }
                        if !group.isEmpty {
                            Section(kind.rawValue) {
                                ForEach(group, id: \.element.id) { i, hit in
                                    Button { go(hit) } label: {
                                        VStack(alignment: .leading, spacing: 1) {
                                            Text(hit.title).lineLimit(1)
                                            Text(hit.detail).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                                        }
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .contentShape(Rectangle())
                                    }
                                    .buttonStyle(.plain)
                                    .listRowBackground(i == selected ? Color.accentColor.opacity(0.18) : Color.clear)
                                    .id(i)
                                }
                            }
                        }
                    }
                }
                .onChange(of: selected) { proxy.scrollTo(selected) }
            }
            if !query.isEmpty && hits.isEmpty {
                Text("Nothing matches.").foregroundStyle(.secondary).padding()
            }
        }
        .frame(width: 640, height: 460)
        .onAppear { focused = true }
    }

    private func open(_ hits: [Hit]) {
        if hits.indices.contains(selected) { go(hits[selected]) }
    }

    private func go(_ hit: Hit) {
        store.route = hit.route
        dismiss()
    }

    /// Results in display order: an exact id first, then steps, notes, data, files.
    func search(_ raw: String) -> [Hit] {
        var q = raw.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return [] }
        var only: Hit.Kind?
        var noteKind: String?
        for token in q.split(separator: " ") {
            let t = String(token)
            if t.hasPrefix("kind:") {
                only = ["step": .step, "note": .note, "data": .data, "file": .file][String(t.dropFirst(5))]
                q = q.replacingOccurrences(of: t, with: "")
            } else if t.hasPrefix("note:") {
                only = .note
                noteKind = String(t.dropFirst(5)).uppercased()
                q = q.replacingOccurrences(of: t, with: "")
            }
        }
        q = q.trimmingCharacters(in: .whitespaces)
        let lower = q.lowercased()
        var exact: [Hit] = [], steps: [Hit] = [], notes: [Hit] = [], data: [Hit] = []
        for p in store.projects {
            for s in p.export?.steps ?? [] {
                let route = Route.step(project: p.id, id: s.id)
                if only == nil || only == .step {
                    if s.id == q {
                        exact.append(Hit(id: "e\(p.id)\(s.id)", kind: .step, title: "\(s.id)  \(s.title)",
                                         detail: p.entry.title, route: route))
                    } else if !lower.isEmpty, s.searchText.lowercased().contains(lower) {
                        let where_ = s.title.lowercased().contains(lower) ? p.entry.title
                            : (s.searchText.split(separator: "\n").first { $0.lowercased().contains(lower) }.map(String.init) ?? "")
                        steps.append(Hit(id: "s\(p.id)\(s.id)", kind: .step, title: "\(s.id)  \(s.title)",
                                         detail: where_, route: route))
                    }
                }
                if only == nil || only == .note {
                    for n in s.notes.compactMap(Note.init) where n.kind != .plain {
                        if let k = noteKind, !n.kind.rawValue.hasPrefix(k) { continue }
                        if lower.isEmpty || n.text.lowercased().contains(lower) {
                            notes.append(Hit(id: "n\(p.id)\(s.id)\(n.text.hashValue)", kind: .note,
                                             title: "\(n.kind.rawValue): \(n.text)", detail: "\(s.id) \(s.title) · \(p.entry.title)",
                                             route: route))
                        }
                    }
                }
            }
            if only == nil || only == .data, !lower.isEmpty {
                for d in p.export?.data ?? [] {
                    let fields = d.fields.filter { $0.name.lowercased().contains(lower) }
                    if d.name.lowercased().contains(lower) || !fields.isEmpty {
                        data.append(Hit(id: "d\(p.id)\(d.name)", kind: .data, title: "data \(d.name)",
                                        detail: fields.map(\.name).joined(separator: ", ") + " · \(p.entry.title)",
                                        route: .data(project: p.id, name: d.name)))
                    }
                }
            }
        }
        var files: [Hit] = []
        if (only == nil || only == .file), !lower.isEmpty, let root = store.root {
            files = FuzzyMatch.rank(q, store.files, limit: 30).map { rel in
                Hit(id: "f" + rel, kind: .file, title: (rel as NSString).lastPathComponent, detail: rel,
                    route: .file(root.appendingPathComponent(rel).standardizedFileURL.path, line: nil))
            }
        }
        return exact + Array(steps.prefix(60)) + Array(notes.prefix(40)) + Array(data.prefix(20)) + files
    }
}
