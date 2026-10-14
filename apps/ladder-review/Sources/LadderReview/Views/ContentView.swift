import SwiftUI

struct ContentView: View {
    @Environment(RepoStore.self) private var store

    var body: some View {
        @Bindable var store = store
        NavigationSplitView {
            SidebarView()
                .navigationSplitViewColumnWidth(min: 240, ideal: 300, max: 480)
        } detail: {
            detail
        }
        .navigationTitle(store.root?.lastPathComponent ?? "Ladder Review")
        .navigationSubtitle(subtitle)
        .toolbar {
            ToolbarItemGroup(placement: .navigation) {
                Button { store.goBack() } label: { Label("Back", systemImage: "chevron.left") }
                    .disabled(!store.canGoBack)
                    .help(store.backStack.last.map { "Back to \(store.describe($0))" } ?? "Back")
                Button { store.goForward() } label: { Label("Forward", systemImage: "chevron.right") }
                    .disabled(!store.canGoForward)
                    .help(store.forwardStack.last.map { "Forward to \(store.describe($0))" } ?? "Forward")
            }
            ToolbarItemGroup {
                if store.loading || store.projects.contains(where: \.loading) {
                    ProgressView().controlSize(.small)
                }
                Button { store.route = .home } label: { Label("Home", systemImage: "house") }
                Button { store.searchShown = true } label: { Label("Search", systemImage: "magnifyingglass") }
                    .disabled(store.root == nil)
                Button { Task { await store.reloadAll() } } label: { Label("Reload", systemImage: "arrow.clockwise") }
                    .disabled(store.root == nil)
            }
        }
        .sheet(isPresented: $store.searchShown) {
            SearchView().environment(store)
        }
    }

    private var subtitle: String {
        guard store.root != nil else { return "" }
        // Which approval the review is against (SPEC: Open questions, the baseline answer).
        let bases = Set(store.projects.compactMap { $0.report?.baseline })
        if !store.since.isEmpty { return "since \(store.since)" }
        if bases.count == 1, let b = bases.first { return "since \(b)" }
        return "since approval"
    }

    @ViewBuilder private var detail: some View {
        if store.root == nil {
            WelcomeView()
        } else if let error = store.error {
            ContentUnavailableView {
                Label("Cannot read the repository", systemImage: "exclamationmark.triangle")
            } description: {
                Text(error).textSelection(.enabled)
            } actions: {
                Button("Retry") { Task { await store.reloadAll() } }
                SettingsLink { Text("Settings…") }
            }
        } else {
            switch store.route ?? .home {
            case .home: HomeView()
            case .project(let path): ProjectView(path: path)
            case .step(let project, let id): StepView(projectPath: project, stepID: id).id("\(project)#\(id)")
            case .data(let project, let name): DataBlockView(projectPath: project, name: name)
            case .file(let path, let line): CodeFileView(path: path, line: line).id(path)
            }
        }
    }
}

struct WelcomeView: View {
    @Environment(RepoStore.self) private var store
    var body: some View {
        ContentUnavailableView {
            Label("Ladder Review", systemImage: "list.bullet.indent")
        } description: {
            Text("Open a repository to see what needs you: edited steps, stale code, open notes and checks.")
        } actions: {
            Button("Open Repository…") { store.chooseRepository() }
                .keyboardShortcut(.defaultAction)
        }
    }
}
