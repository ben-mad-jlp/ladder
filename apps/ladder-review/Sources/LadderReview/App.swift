import AppKit
import SwiftUI

@main
struct LadderReviewApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @State private var store = RepoStore()

    var body: some Scene {
        Window("Ladder Review", id: "main") {
            ContentView()
                .environment(store)
                .frame(minWidth: 900, minHeight: 560)
                .task { await store.startup() }
        }
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("Open Repository…") { store.chooseRepository() }
                    .keyboardShortcut("o")
            }
            CommandGroup(after: .toolbar) {
                Button("Reload") { Task { await store.reloadAll() } }
                    .keyboardShortcut("r")
                    .disabled(store.root == nil)
                Button("Search…") { store.searchShown = true }
                    .keyboardShortcut("k")
                    .disabled(store.root == nil)
                Button("Home") { store.route = .home }
                    .keyboardShortcut("1")
                Button("Back") { store.goBack() }
                    .keyboardShortcut("[")
                    .disabled(!store.canGoBack)
                Button("Forward") { store.goForward() }
                    .keyboardShortcut("]")
                    .disabled(!store.canGoForward)
            }
        }
        Settings {
            SettingsView().environment(store)
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Started with `swift run`: become a regular app with a Dock icon and a menu bar.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }
}

extension RepoStore {
    /// The repository to open at launch: a folder named on the command line, else the last one opened.
    func startup() async {
        let all = Array(CommandLine.arguments.dropFirst())
        var positional: [String] = []
        var i = 0
        while i < all.count {
            if all[i] == "--tool", i + 1 < all.count {
                UserDefaults.standard.set(all[i + 1], forKey: "toolPath")
                i += 2
            } else if all[i] == "--snapshot" {
                i += 2
            } else if all[i].hasPrefix("-") {
                i += all[i].hasPrefix("-NS") || all[i].hasPrefix("-Apple") ? 2 : 1   // AppKit's own -Key value pairs
            } else {
                positional.append(all[i])
                i += 1
            }
        }
        let path = positional.first.map { ($0 as NSString).expandingTildeInPath }
            ?? UserDefaults.standard.string(forKey: "lastRepository")
        await findTool()
        if let path, FileManager.default.fileExists(atPath: path) {
            await open(URL(fileURLWithPath: path).standardizedFileURL)
        }
        await snapshotIfAsked()
    }

    func chooseRepository() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.prompt = "Open"
        panel.message = "Choose a repository (or a folder) with Ladder projects"
        if panel.runModal() == .OK, let url = panel.url {
            Task { await open(url) }
        }
    }
}
