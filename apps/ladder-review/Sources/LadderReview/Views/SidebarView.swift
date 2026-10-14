import SwiftUI

struct SidebarView: View {
    @Environment(RepoStore.self) private var store
    @AppStorage("sidebarMode") private var mode = "ladder"
    @State private var filter = ""

    var body: some View {
        @Bindable var store = store
        VStack(spacing: 0) {
            Picker("", selection: $mode) {
                Text("Ladder").tag("ladder")
                Text("Files").tag("files")
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            List(selection: $store.route) {
                if mode == "ladder" {
                    Label {
                        HStack {
                            Text("Home")
                            Spacer()
                            let n = store.allItems.filter { $0.level != .warning }.count
                            if n > 0 { CountBadge(count: n) }
                        }
                    } icon: { Image(systemName: "house") }
                    .tag(Route.home)
                    ForEach(store.projects) { p in
                        ProjectSection(project: p, filter: filter)
                    }
                } else {
                    FileNavigator(filter: filter)
                }
            }
            .listStyle(.sidebar)
        }
        .searchable(text: $filter, placement: .sidebar, prompt: mode == "ladder" ? "Filter steps" : "Filter files")
    }
}

struct CountBadge: View {
    var count: Int
    var body: some View {
        Text("\(count)")
            .font(.caption2.monospacedDigit().weight(.semibold))
            .padding(.horizontal, 6)
            .padding(.vertical, 1)
            .background(.quaternary, in: Capsule())
    }
}

struct ProjectSection: View {
    @Environment(RepoStore.self) private var store
    var project: ProjectState
    var filter: String

    var body: some View {
        // A plain Section: the sidebar list style already offers Show/Hide on hover, and a Section bound to
        // isExpanded made the outline table warn of reentrant delegate calls while projects loaded.
        Section {
            Label("Overview", systemImage: "doc.text.magnifyingglass").tag(Route.project(project.id))
            if let error = project.error, project.export == nil {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.secondary).lineLimit(3)
            }
            if filter.isEmpty {
                ForEach(project.roots) { s in StepOutline(project: project, step: s) }
            } else {
                let f = filter.lowercased()
                ForEach((project.export?.steps ?? []).filter { $0.searchText.lowercased().contains(f) }) { s in
                    StepRow(project: project, step: s).tag(Route.step(project: project.id, id: s.id))
                }
            }
            if let data = project.export?.data, !data.isEmpty, filter.isEmpty {
                DisclosureGroup {
                    ForEach(data) { d in
                        Label(d.name, systemImage: "tablecells").tag(Route.data(project: project.id, name: d.name))
                    }
                } label: {
                    Label("Data", systemImage: "square.stack.3d.up")
                }
            }
        } header: {
            HStack {
                StatusDot(status: project.report?.status)
                Text(project.entry.title)
            }
            .help(project.entry.name)
        }
    }
}

/// A step and its children, collapsible.
struct StepOutline: View {
    var project: ProjectState
    var step: Step

    var body: some View {
        let steps = project.steps
        if step.children.isEmpty {
            StepRow(project: project, step: step).tag(Route.step(project: project.id, id: step.id))
        } else {
            DisclosureGroup {
                ForEach(step.children.compactMap { steps[$0] }) { c in StepOutline(project: project, step: c) }
            } label: {
                StepRow(project: project, step: step, below: project.attention.worstBelow(step, steps: steps))
            }
            .tag(Route.step(project: project.id, id: step.id))
        }
    }
}

struct StepRow: View {
    var project: ProjectState
    var step: Step
    var below: StepBadge = .ok

    var body: some View {
        let badge = project.attention.badge(for: step.id)
        HStack(spacing: 6) {
            BadgeIcon(badge: badge)
            Text(step.id).font(.caption.monospaced()).foregroundStyle(.secondary)
            Text(step.title).lineLimit(1)
            if below < .ok {
                Spacer(minLength: 0)
                Circle().fill(below.color).frame(width: 6, height: 6)
                    .help("a part below is \(below.label)")
            }
        }
        .help("\(step.id) \(step.title): \(badge.label)" + (below < .ok ? "; a part below is \(below.label)" : ""))
    }
}

struct BadgeIcon: View {
    var badge: StepBadge
    var body: some View {
        Image(systemName: badge.symbol)
            .foregroundStyle(badge.color)
            .font(.caption)
            .frame(width: 14)
    }
}

extension StepBadge {
    var color: Color {
        switch self {
        case .problem: .red
        case .stale, .handEdited: .orange
        case .edited, .new: .blue
        case .note: .purple
        case .warning: .yellow
        case .ok: .secondary.opacity(0.6)
        }
    }
}

struct StatusDot: View {
    var status: String?
    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 8, height: 8)
            .help(status ?? "not checked yet")
    }
    var color: Color {
        switch status {
        case "ok": .green
        case "awaiting-approval": .blue
        case "problems": .red
        default: .gray
        }
    }
}
