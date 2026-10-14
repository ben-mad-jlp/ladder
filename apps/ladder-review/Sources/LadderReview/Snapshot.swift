import AppKit
import SwiftUI

/// `LadderReview <repo> --snapshot <folder>`: after loading, draw the window at a few screens (Home, the first step
/// with something to show, its Code tab, a code file) into PNGs and quit. For checking the app's screens where screen
/// recording is not allowed (CI, a background session); the window draws itself, nothing is captured from the screen.
extension RepoStore {
    func snapshotIfAsked() async {
        let args = CommandLine.arguments
        guard let i = args.firstIndex(of: "--snapshot"), i + 1 < args.count else { return }
        let folder = URL(fileURLWithPath: args[i + 1])
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        while loading || projects.contains(where: \.loading) || projects.isEmpty && error == nil {
            try? await Task.sleep(for: .milliseconds(200))
        }
        let step = projects.lazy.compactMap { p in
            p.attention.items.lazy.compactMap { item in item.nodes.first { p.steps[$0] != nil }.map { (p, $0) } }.first
        }.first
        var shots: [(String, Route, String?)] = [("home", .home, nil)]
        if let (p, id) = step {
            shots.append(("step-english", .step(project: p.id, id: id), "english"))
            shots.append(("step-code", .step(project: p.id, id: id), "code"))
            if let f = p.regions(for: id).first {
                shots.append(("file", .file(f.file.absolute, line: f.region.start), nil))
            }
            shots.append(("step-edit", .step(project: p.id, id: id), "edit"))
        }
        for (name, route, tab) in shots {
            snapshotEditing = tab == "edit"
            if let tab { UserDefaults.standard.set(tab == "edit" ? "english" : tab, forKey: "stepTab") }
            if tab == "edit" { self.route = .home; try? await Task.sleep(for: .milliseconds(300)) }
            self.route = route
            try? await Task.sleep(for: .milliseconds(900))
            guard let window = NSApp.windows.first(where: { $0.isVisible && $0.contentView != nil }),
                  let view = window.contentView,
                  let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { continue }
            view.cacheDisplay(in: view.bounds, to: rep)
            try? rep.representation(using: .png, properties: [:])?.write(to: folder.appendingPathComponent("\(name).png"))
        }
        UserDefaults.standard.set("english", forKey: "stepTab")
        NSApp.terminate(nil)
    }
}
