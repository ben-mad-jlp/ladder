import SwiftUI

/// A code file, read-only, with its tagged regions outlined and labeled by step (SPEC: Project navigator). Selecting
/// a region's label opens that step.
struct CodeFileView: View {
    @Environment(RepoStore.self) private var store
    var path: String
    var line: Int?

    var body: some View {
        let lines = SourceCache.lines(path)
        let regions = store.regions(inFile: path)
        let owner = innermost(regions.map(\.region), count: lines.count)
        let starts = Dictionary(regions.enumerated().map { ($0.element.region.start, $0.offset) },
                                uniquingKeysWith: { a, _ in a })
        VStack(spacing: 0) {
            HStack {
                Text(store.relative(path)).font(.callout.monospaced()).textSelection(.enabled)
                Spacer()
                if regions.isEmpty {
                    Text("no Ladder regions").font(.caption).foregroundStyle(.secondary)
                } else {
                    Text("\(Set(regions.flatMap(\.region.steps)).count) steps in \(regions.count) regions")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Button { store.openInEditor(path, line: line) } label: {
                    Label("Open in editor", systemImage: "arrow.up.forward.app")
                }
            }
            .padding(8)
            Divider()
            if lines.isEmpty {
                ContentUnavailableView("Cannot read this file", systemImage: "doc.questionmark",
                                       description: Text("It may be binary, missing, or not UTF-8."))
            } else {
                ScrollViewReader { proxy in
                    ScrollView([.vertical, .horizontal]) {
                        LazyVStack(alignment: .leading, spacing: 0) {
                            ForEach(1...lines.count, id: \.self) { n in
                                VStack(alignment: .leading, spacing: 0) {
                                    if let ri = starts[n] { regionLabel(regions[ri]) }
                                    lineRow(n, lines[n - 1], region: owner[n - 1].map { regions[$0] })
                                }
                                .id(n)
                            }
                        }
                        .padding(.vertical, 6)
                        .font(.system(.callout, design: .monospaced))
                        .textSelection(.enabled)
                    }
                    .onAppear {
                        if let line { proxy.scrollTo(line, anchor: .center) }
                    }
                }
            }
        }
        .navigationTitle((path as NSString).lastPathComponent)
    }

    private func lineRow(_ n: Int, _ text: String, region: (project: ProjectState, build: Build, region: Region)?) -> some View {
        HStack(alignment: .top, spacing: 0) {
            Text("\(n)").foregroundStyle(.tertiary).frame(width: 48, alignment: .trailing).padding(.trailing, 8)
            Rectangle().fill(region.map { color($0.region) } ?? .clear).frame(width: 3)
            Text(text.isEmpty ? " " : text).padding(.leading, 8).fixedSize()
                .foregroundStyle(n == line ? Color.accentColor : .primary)
        }
        .background(n == line ? Color.accentColor.opacity(0.08) : .clear)
    }

    private func regionLabel(_ r: (project: ProjectState, build: Build, region: Region)) -> some View {
        HStack(spacing: 6) {
            Spacer().frame(width: 59)
            if r.region.kind == "node" {
                ForEach(r.region.steps, id: \.self) { id in
                    Button {
                        store.route = .step(project: r.project.id, id: id)
                    } label: {
                        Text("\(id) \(r.project.steps[id]?.title ?? "(not in the tree)")")
                            .lineLimit(1)
                            .fixedSize()
                    }
                    .buttonStyle(.link)
                }
            } else {
                Text(r.region.kind == "support" ? "support: \(r.region.label)" : r.region.label)
                    .foregroundStyle(.secondary)
            }
            if r.region.isStale { Chip(text: "stale", color: .orange) }
            ForEach(r.region.problems.filter { !$0.hasPrefix("stale") }, id: \.self) { Chip(text: $0, color: .orange) }
            Text(r.build.name).foregroundStyle(.tertiary)
        }
        .font(.caption)
        .padding(.top, 6)
        .padding(.bottom, 2)
    }

    private func color(_ r: Region) -> Color {
        if r.isStale || !r.problems.isEmpty { return .orange }
        switch r.kind {
        case "node": return .blue.opacity(0.6)
        case "contract": return .purple.opacity(0.6)
        default: return .secondary.opacity(0.4)
        }
    }

    /// The innermost region each line belongs to (regions nest; a later, narrower one wins).
    private func innermost(_ regions: [Region], count: Int) -> [Int?] {
        var owner = [Int?](repeating: nil, count: count)
        var width = [Int](repeating: .max, count: count)
        for (i, r) in regions.enumerated() {
            let lo = max(r.start, 1), hi = min(r.end, count)
            guard lo <= hi else { continue }
            for n in lo...hi where r.end - r.start < width[n - 1] {
                owner[n - 1] = i
                width[n - 1] = r.end - r.start
            }
        }
        return owner
    }
}
