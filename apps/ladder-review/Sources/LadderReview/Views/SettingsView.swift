import SwiftUI

struct SettingsView: View {
    @Environment(RepoStore.self) private var store
    @AppStorage("toolPath") private var toolPath = ""
    @AppStorage("editor") private var editor = "default"

    var body: some View {
        @Bindable var store = store
        Form {
            Section {
                TextField("ladder tool", text: $toolPath, prompt: Text("found automatically"))
                    .onSubmit { Task { store.toolPath = nil; await store.findTool(); await store.reloadAll() } }
                LabeledContent("Using", value: store.toolPath ?? "not found")
                if let v = store.toolVersion { LabeledContent("Version", value: v) }
                Text("A `ladder` executable or the plugin's `tool/ladder.py`. Empty: $LADDER_TOOL, then `ladder` on "
                     + "your shell's PATH, then the newest Ladder plugin under ~/.claude/plugins.")
                    .font(.caption).foregroundStyle(.secondary)
            } header: { Text("Tool") }
            Section {
                TextField("Compare with", text: $store.since, prompt: Text("the last approval"))
                    .onSubmit { Task { await store.reloadAll() } }
                Text("A git ref (like origin/main): `ladder check --since`. Empty: since each project's approval, "
                     + "or its baseline when nothing is approved yet.")
                    .font(.caption).foregroundStyle(.secondary)
            } header: { Text("Review") }
            Section {
                Picker("Open code in", selection: $editor) {
                    Text("Default app").tag("default")
                    Text("Xcode").tag("xcode")
                    Text("VS Code").tag("vscode")
                    Text("Cursor").tag("cursor")
                }
            } header: { Text("Editor") }
        }
        .formStyle(.grouped)
        .frame(width: 520)
    }
}
