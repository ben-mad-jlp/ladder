import SwiftUI

// Editing, answering notes and approving (SPEC: "Editing the English", "Approval and answering notes"). Every change
// goes through the tool: a dry run first shows the diff and its reach, then the same command writes it.

// MARK: editing a step

/// An edit in progress: the draft and what the header's Cancel and Review change… buttons act on.
@Observable @MainActor
final class EditSession {
    let project: String
    let step: Step
    var draft: StepEdit
    var error: String?
    var working = false
    var review: PendingChange?

    init(project: String, step: Step) {
        self.project = project
        self.step = step
        draft = StepEdit(step)
    }

    var hasChanges: Bool { draft != StepEdit(step) }

    /// Dry-run the change; the review sheet shows the diff and its reach, and saves it on confirm.
    func preview(with tool: LadderTool?) async {
        guard let tool else { return }
        working = true
        defer { working = false }
        error = nil
        let (project, step, draft) = (self.project, self.step, self.draft)
        do {
            let r = try await tool.edit(project, step: step.id, draft, expect: step.reviewHash, dryRun: true)
            review = PendingChange(project: project, step: step.id, title: "Change [\(step.id)] \(step.title)",
                                   preview: r) {
                try await tool.edit(project, step: step.id, draft, expect: step.reviewHash, dryRun: false)
            }
        } catch {
            self.error = error.localizedDescription
        }
    }
}

/// The step's parts as fields: each how-line and note its own row, which can be added, removed and reordered.
/// Cancel and Review change… are in the step page's header while editing.
struct StepEditor: View {
    var project: ProjectState
    @Bindable var session: EditSession

    var body: some View {
        let hints = EnglishHints(project: project)
        VStack(alignment: .leading, spacing: 14) {
            if let error = session.error {
                Label(error, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red).textSelection(.enabled)
            }
            field("Title", text: $session.draft.title, hints: [])
            field("in", text: $session.draft.inputs, hints: hints.check(session.draft.inputs, part: "in"))
            field("out", text: $session.draft.outputs, hints: hints.check(session.draft.outputs, part: "out"))
            field("effects", text: $session.draft.effects, hints: hints.check(session.draft.effects, part: "effects"))
            LineList(title: "How", prefix: ">", lines: $session.draft.how, hints: { hints.check($0, part: "how") })
            LineList(title: "Notes", prefix: "note:", lines: $session.draft.notes, hints: { _ in [] })
            field("uses", text: Binding(get: { self.session.draft.uses.joined(separator: "; ") },
                                         set: { self.session.draft.uses = $0.split(separator: ";").map { $0.trimmingCharacters(in: .whitespaces) } }),
                  hints: hints.checkUses(session.draft.uses))
            LineList(title: "Compare", prefix: "compare:", lines: $session.draft.compare, hints: { hints.checkCompare($0) })
            Text("Small changes only: larger ones go through Claude and the ladder-write skill. Ids, `calls:`, "
                 + "`reads:` and `writes:` are kept as they are.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private func field(_ label: String, text: Binding<String>, hints: [String]) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            GrowingField(placeholder: label, text: text)
            HintList(hints: hints)
        }
    }
}

/// A list of one-line items (how-lines, notes, compare lines) with add, remove and reorder.
struct LineList: View {
    var title: String
    var prefix: String
    @Binding var lines: [String]
    var hints: (String) -> [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Spacer()
                Button { lines.append("") } label: { Label("Add", systemImage: "plus") }
                    .buttonStyle(.borderless).font(.caption)
            }
            ForEach(lines.indices, id: \.self) { i in
                VStack(alignment: .leading, spacing: 2) {
                    HStack(alignment: .top, spacing: 6) {
                        Text(prefix).font(.callout.monospaced()).foregroundStyle(.tertiary).padding(.top, 3)
                        GrowingField(placeholder: "", text: Binding(get: { i < lines.count ? lines[i] : "" },
                                                                    set: { if i < lines.count { lines[i] = $0 } }))
                        Button { lines.swapAt(i, i - 1) } label: { Image(systemName: "arrow.up") }
                            .disabled(i == 0).help("Move up")
                        Button { lines.swapAt(i, i + 1) } label: { Image(systemName: "arrow.down") }
                            .disabled(i == lines.count - 1).help("Move down")
                        Button { lines.remove(at: i) } label: { Image(systemName: "minus.circle") }
                            .help("Remove")
                    }
                    .buttonStyle(.borderless)
                    if i < lines.count { HintList(hints: hints(lines[i])).padding(.leading, 30) }
                }
            }
        }
    }
}

/// A text box that wraps and grows with its text. Each part of a step is one line in the .ladder file, so a typed
/// line break becomes a space. (A rounded-border TextField on macOS stays one line high and scrolls sideways.)
struct GrowingField: View {
    var placeholder: String
    @Binding var text: String
    @FocusState private var focused: Bool

    var body: some View {
        ZStack(alignment: .topLeading) {
            // The invisible copy sizes the box: the editor itself does not report a height that fits its text.
            Text(text.isEmpty ? " " : text + " ")
                .padding(.horizontal, 5)
                .padding(.vertical, 4)
                .opacity(0)
                .frame(maxWidth: .infinity, alignment: .leading)
            if text.isEmpty {
                Text(placeholder).foregroundStyle(.tertiary).padding(.horizontal, 5).padding(.vertical, 4)
                    .allowsHitTesting(false)
            }
            TextEditor(text: Binding(get: { text }, set: { text = $0.replacingOccurrences(of: "\n", with: " ") }))
                .scrollDisabled(true)
                .scrollContentBackground(.hidden)
                .focused($focused)
        }
        .font(.body)
        .fixedSize(horizontal: false, vertical: true)
        .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 5))
        .overlay(RoundedRectangle(cornerRadius: 5)
            .stroke(focused ? Color.accentColor.opacity(0.6) : Color.secondary.opacity(0.35), lineWidth: focused ? 2 : 1))
    }
}

struct HintList: View {
    var hints: [String]
    var body: some View {
        ForEach(hints, id: \.self) { h in
            Label(h, systemImage: "lightbulb").font(.caption).foregroundStyle(.orange)
        }
    }
}

/// Gentle prompts beside a field, never blockers (SPEC: "Hints, never blockers" and "Live checks while typing").
struct EnglishHints {
    var project: ProjectState

    func check(_ text: String, part: String) -> [String] {
        var out: [String] = []
        // in:/out: lines declare the names a step works with; elsewhere a backticked name should be one of those,
        // a data block or one of its fields.
        if part != "in" && part != "out" {
            let steps = project.export?.steps ?? []
            let known = Set((project.export?.data ?? []).flatMap { [$0.name] + $0.fields.map(\.name) }
                            + steps.flatMap { backticked($0.inputs) + backticked($0.outputs) })
            for name in backticked(text) where !known.contains(name) && !known.contains(String(name.split(separator: ".").first ?? "")) {
                out.append("`\(name)` is not a data field or a name any step's in:/out: declares")
            }
        }
        let lower = text.lowercased()
        if lower.range(of: #"\b(up to|limit|max(imum)?|min(imum)?|at most|at least)\b[^.]*\d"#, options: .regularExpression) != nil,
           lower.range(of: #"inclusive|exclusive|or more|or fewer|or less"#, options: .regularExpression) == nil {
            out.append("Is the limit inclusive?")
        }
        if part == "out" && lower.contains("list") {
            out.append("The same list, or a new one?")
        }
        if lower.range(of: #"\bnothing\b"#, options: .regularExpression) != nil && part != "in" {
            out.append("\"Nothing\": left off, or set to null?")
        }
        return out
    }

    func checkUses(_ uses: [String]) -> [String] {
        let known = Set((project.export?.vocabulary ?? []).map(\.name))
        return uses.filter { !$0.isEmpty && !known.contains($0) }.map { "'\($0)' is not a capability in the vocabulary" }
    }

    func checkCompare(_ line: String) -> [String] {
        let ok = [#"^ignore\s+.+$"#, #"^any order$"#, #"^.+\s+in any order$"#, #"^numbers within\s+[0-9.]+$"#,
                  #"^any timing$"#, #"^final result only$"#]
        let clauses = line.split(separator: ";").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        return clauses.filter { c in !ok.contains { c.range(of: $0, options: [.regularExpression, .caseInsensitive]) != nil } }
            .map { "compare: '\($0)' is not understood (ignore <fields>; any order; <field> in any order; numbers within <n>; any timing; final result only)" }
    }

    private func backticked(_ text: String) -> [String] {
        text.split(separator: "`", omittingEmptySubsequences: false).enumerated()
            .filter { $0.offset % 2 == 1 }.map { String($0.element) }.filter { !$0.isEmpty }
    }
}

// MARK: reviewing a change before it is written

/// A change the tool has dry-run: shown with its diff and reach, written only on confirm.
struct PendingChange: Identifiable {
    var id = UUID()
    var project: String
    var step: String
    var title: String
    var preview: EditResult
    var commit: () async throws -> EditResult
}

struct ChangeReviewSheet: View {
    @Environment(RepoStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    var change: PendingChange
    var onSaved: () -> Void
    @State private var error: String?
    @State private var working = false

    var body: some View {
        let r = change.preview
        VStack(alignment: .leading, spacing: 12) {
            Text(change.title).font(.title3.weight(.semibold))
            if !r.changed {
                Label("Nothing changes: the file already says this.", systemImage: "equal.circle")
            } else {
                DiffView(diff: r.diff)
                ReachSummary(result: r)
            }
            if let error {
                Label(error, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red).textSelection(.enabled)
            }
            HStack {
                Spacer()
                Button("Cancel", role: .cancel) { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Save") { Task { await save() } }
                    .keyboardShortcut(.defaultAction)
                    .disabled(!r.changed || working)
            }
        }
        .padding(20)
        .frame(width: 720)
        .frame(minHeight: 300)
    }

    private func save() async {
        working = true
        defer { working = false }
        do {
            _ = try await change.commit()
            await store.reload(change.project)
            dismiss()
            onSaved()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

/// What a change reaches, before it is saved (SPEC: "Reach before save").
struct ReachSummary: View {
    var result: EditResult
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if result.stale.isEmpty {
                Label(result.codeChanged ? "No tagged code yet: nothing goes stale."
                      : "Wording that is not part of the code's hash: no code goes stale.",
                      systemImage: "checkmark.circle").foregroundStyle(.green)
            } else {
                let builds = Set(result.stale.map(\.build))
                Label("This makes \(result.stale.count) code region\(result.stale.count == 1 ? "" : "s") stale in "
                      + "\(builds.count) build\(builds.count == 1 ? "" : "s"): "
                      + result.stale.map { "\($0.build) \(($0.file as NSString).lastPathComponent):\($0.line)" }
                        .joined(separator: ", "),
                      systemImage: "clock.badge.exclamationmark").foregroundStyle(.orange)
                Text(result.notesOnly
                     ? "Only a note changed: if the code still does what the step says, retag it (Code tab) instead of regenerating."
                     : "Regenerate it (`ladder regen`), or retag it if this is rewording only.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if result.contractChanged {
                Label("The contract (in:/out: or data) changes: @contract regions go stale, and linked trees are told.",
                      systemImage: "arrow.triangle.branch").foregroundStyle(.orange)
            }
            Label("The step will wait for approval again.", systemImage: "person.badge.clock").foregroundStyle(.secondary)
        }
        .font(.callout)
    }
}

/// A unified diff, colored.
struct DiffView: View {
    var diff: String
    var body: some View {
        ScrollView([.vertical, .horizontal]) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(diff.split(separator: "\n", omittingEmptySubsequences: false).enumerated()), id: \.offset) { _, line in
                    let s = String(line)
                    if !s.hasPrefix("---") && !s.hasPrefix("+++") {
                        Text(s.isEmpty ? " " : s)
                            .foregroundStyle(s.hasPrefix("@@") ? Color.secondary : .primary)
                            .padding(.horizontal, 6)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(s.hasPrefix("+") ? Color.green.opacity(0.15) : s.hasPrefix("-") ? Color.red.opacity(0.15) : .clear)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                }
            }
            .font(.system(.callout, design: .monospaced))
            .textSelection(.enabled)
            .padding(.vertical, 6)
        }
        .frame(maxHeight: 320)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 6))
    }
}

// MARK: answering a note

struct AnswerRequest: Identifiable {
    var id = UUID()
    var step: Step
    var noteNumber: Int       // from 1, among the step's notes
    var note: Note
}

/// The note's actions (SPEC: the note table): QUESTION keep as is / it's a bug; DIFFERS one wins / both are fine;
/// DECISION accept / change.
struct AnswerSheet: View {
    @Environment(RepoStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    var project: ProjectState
    var request: AnswerRequest
    var onChangeStep: () -> Void
    @State private var choice = ""
    @State private var detail = ""
    @State private var review: PendingChange?
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Answer the \(request.note.kind.rawValue.lowercased()) on [\(request.step.id)]").font(.title3.weight(.semibold))
            Text(request.note.text).padding(8).frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.purple.opacity(0.08), in: RoundedRectangle(cornerRadius: 6))
                .textSelection(.enabled)
            Picker("Answer", selection: $choice) {
                ForEach(options, id: \.self) { Text($0).tag($0) }
            }
            .pickerStyle(.radioGroup)
            if needsDetail {
                TextField(detailPrompt, text: $detail, axis: .vertical).textFieldStyle(.roundedBorder)
            }
            Text(explanation).font(.caption).foregroundStyle(.secondary)
            if let error {
                Label(error, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red)
            }
            HStack {
                Spacer()
                Button("Cancel", role: .cancel) { dismiss() }.keyboardShortcut(.cancelAction)
                Button(choice == "Change the step" ? "Edit the step" : "Review answer…") { Task { await go() } }
                    .keyboardShortcut(.defaultAction)
                    .disabled(choice.isEmpty || needsDetail && detail.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(20)
        .frame(width: 560)
        .onAppear { choice = options.first ?? "" }
        .sheet(item: $review) { change in
            ChangeReviewSheet(change: change) { dismiss() }.environment(store)
        }
    }

    private var options: [String] {
        switch request.note.kind {
        case .question: ["Keep as is", "It's a bug"]
        case .differs: ["One build wins", "Both are fine"]
        case .decision: ["Accept", "Change the step"]
        default: []
        }
    }

    private var needsDetail: Bool { ["It's a bug", "One build wins"].contains(choice) }
    private var detailPrompt: String { choice == "It's a bug" ? "What it should do" : "Which build wins, and why" }
    private var explanation: String {
        switch choice {
        case "It's a bug": "Written as ANSWERED: bug. The step stays on Home until its how-lines are rewritten and the code regenerated."
        case "Change the step": "Opens the step for editing; the decision note stays until you change it."
        case "Accept", "Both are fine": "The note becomes a plain note."
        default: "Written into the English as an ANSWERED note, with your name and the date; the question stays after it."
        }
    }

    private func go() async {
        if choice == "Change the step" {
            dismiss()
            onChangeStep()
            return
        }
        guard let tool = store.tool else { return }
        let (text, plain): (String, Bool) = switch choice {
        case "Keep as is": ("keep as is", false)
        case "It's a bug": ("bug: " + detail.trimmingCharacters(in: .whitespaces), false)
        case "One build wins": (detail.trimmingCharacters(in: .whitespaces), false)
        case "Both are fine": ("both are intended", true)
        default: ("", true)       // a DECISION accepted
        }
        let p = project.id, s = request.step
        do {
            let r = try await tool.answer(p, step: s.id, note: request.noteNumber, text, plain: plain,
                                          expect: s.reviewHash, dryRun: true)
            review = PendingChange(project: p, step: s.id, title: "Answer on [\(s.id)] \(s.title)", preview: r) {
                try await tool.answer(p, step: s.id, note: request.noteNumber, text, plain: plain,
                                      expect: s.reviewHash, dryRun: false)
            }
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: approving

struct ApproveRequest: Identifiable {
    var id = UUID()
    var project: String
    var title: String
    var ids: [String]
}

/// What will be recorded and what stays open; Confirm runs `ladder stamp --steps` (SPEC: Approve sheet).
struct ApproveSheet: View {
    @Environment(RepoStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    var request: ApproveRequest
    @State private var preview: StampResult?
    @State private var error: String?
    @State private var working = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(request.title).font(.title3.weight(.semibold))
            if let p = preview {
                Text("Will be recorded as approved by \(p.by):").font(.callout)
                List(p.recorded, id: \.self) { r in
                    HStack {
                        Text(r.kind == "data" ? "data \(r.id)" : "[\(r.id)]").font(.callout.monospaced())
                        Text(title(r.id)).lineLimit(1)
                        Spacer()
                        Chip(text: r.what, color: r.what == "unchanged" ? .secondary : .blue)
                    }
                }
                .frame(minHeight: 120, maxHeight: 260)
                if !p.stillOpen.isEmpty {
                    Text("Still waiting after this: \(p.stillOpen.count)").font(.callout).foregroundStyle(.secondary)
                }
            } else if error == nil {
                ProgressView()
            }
            if let error {
                Label(error, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red).textSelection(.enabled)
            }
            HStack {
                Text("Approval says a person read this English and agrees it is what the code should do.")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Cancel", role: .cancel) { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Approve") { Task { await confirm() } }
                    .keyboardShortcut(.defaultAction)
                    .disabled(preview == nil || working)
            }
        }
        .padding(20)
        .frame(width: 620)
        .task { await load() }
    }

    private func title(_ id: String) -> String { store.project(request.project)?.steps[id]?.title ?? "" }

    private func load() async {
        guard let tool = store.tool else { return }
        do { preview = try await tool.approve(request.project, ids: request.ids, dryRun: true) }
        catch { self.error = error.localizedDescription }
    }

    private func confirm() async {
        guard let tool = store.tool else { return }
        working = true
        defer { working = false }
        do {
            _ = try await tool.approve(request.project, ids: request.ids, dryRun: false)
            await store.reload(request.project)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

extension ProjectState {
    /// The step and data ids that wait for approval in this project (new, edited, removed, ...).
    var waitingIDs: [String] {
        var seen = Set<String>()
        let steps = self.steps
        let data = Set((export?.data ?? []).map(\.name))
        return attention.items.filter { $0.level == .approval && $0.kind != "baseline-new" }
            .flatMap { item in item.nodes.filter { steps[$0] != nil || data.contains($0) || item.kind.hasSuffix("removed") } }
            .filter { seen.insert($0).inserted }
    }
}
