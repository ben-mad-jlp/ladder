import Foundation

/// One thing on Home: what needs a person, why it is there, and what resolves it (SPEC: Home).
struct AttentionItem: Identifiable, Hashable {
    enum Level: Int, CaseIterable, Comparable {
        case problem, approval, note, warning
        static func < (a: Level, b: Level) -> Bool { a.rawValue < b.rawValue }
        var title: String {
            switch self {
            case .problem: "Problems"
            case .approval: "Waiting for approval"
            case .note: "Open notes"
            case .warning: "Warnings"
            }
        }
        var caption: String {
            switch self {
            case .problem: "block: `ladder check` exits 1"
            case .approval: "a person reviews the English, then `ladder stamp`"
            case .note: "QUESTION:, DIFFERS: and DECISION: notes in the English"
            case .warning: "inform; do not fail the check"
            }
        }
    }

    var id: String
    var project: String          // ladder.json path
    var projectName: String
    var level: Level
    var kind: String
    var nodes: [String]
    var message: String
    var file: String?            // absolute
    var line: Int?

    var resolvedBy: String { Self.resolution[kind] ?? Self.fallback(level) }

    static func fallback(_ level: Level) -> String {
        switch level {
        case .problem: "fix what the message says, then run `ladder check`"
        case .approval: "review the English, then approve (`ladder stamp`)"
        case .note: "answering it in the English"
        case .warning: "nothing blocks; read the message"
        }
    }

    /// What resolves each kind (SPEC: the Home table).
    static let resolution: [String: String] = [
        "edited": "approving it", "new": "approving it", "removed": "approving it", "baseline-new": "approving it",
        "parent-changed": "re-reading the step under its parent, then approving",
        "rule-changed": "re-reading the steps that cite the rule, then approving",
        "capability-changed": "re-reading the steps that use it, then approving",
        "data-new": "approving it", "data-edited": "approving it; regenerate @contract regions",
        "data-removed": "approving it", "compare-edited": "approving the looser or stricter comparison",
        "stale": "regenerating (`ladder regen`), or `ladder retag` if the English was only reworded",
        "stale-contract": "regenerating the @contract region",
        "hand-edited": "describing it in the English, accepting it (`ladder accept`), or discarding it",
        "exports-changed": "accepting it (`ladder accept --exports`)",
        "missing": "generating code for the step", "missing-file": "fixing the path in ladder.json",
        "untagged": "tagging the code, or giving it a step", "unknown-step": "fixing the tag or the tree",
        "linked-changed": "re-reading this step, then approving",
        "has-callers": "updating the callers' English, or telling their owner",
        "schema-changed": "re-reading the step", "test-failed": "fixing the claim or the code, then `ladder test`",
        "test-stale": "running `ladder test`", "test-not-run": "running `ladder test`",
        "type-drift": "editing that file by hand, or giving it a build",
        "comparison": "investigating; often a note or an English fix",
        "QUESTION": "answering it: keep as is, or it's a bug", "DIFFERS": "naming which build wins, or both are fine",
        "DECISION": "accepting it, or changing the step",
        "ANSWERED bug": "rewriting the how-lines (ladder-write), then regenerating",
    ]
}

/// The worst thing about a step, shown as its badge in the tree.
enum StepBadge: Int, Comparable {
    case problem, stale, handEdited, edited, new, note, warning, ok
    static func < (a: StepBadge, b: StepBadge) -> Bool { a.rawValue < b.rawValue }

    var label: String {
        switch self {
        case .problem: "problem"
        case .stale: "stale"
        case .handEdited: "hand-edited"
        case .edited: "edited"
        case .new: "new"
        case .note: "open note"
        case .warning: "warning"
        case .ok: "approved"
        }
    }
    var symbol: String {
        switch self {
        case .problem: "exclamationmark.octagon.fill"
        case .stale: "clock.badge.exclamationmark"
        case .handEdited: "hand.raised.fill"
        case .edited: "pencil.circle.fill"
        case .new: "plus.circle.fill"
        case .note: "questionmark.bubble.fill"
        case .warning: "exclamationmark.triangle"
        case .ok: "checkmark.circle"
        }
    }

    static func from(kind: String, level: AttentionItem.Level) -> StepBadge {
        switch kind {
        case "stale", "stale-contract": .stale
        case "hand-edited": .handEdited
        case "new", "baseline-new": .new
        default:
            switch level {
            case .problem: .problem
            case .approval: .edited
            case .note: .note
            case .warning: .warning
            }
        }
    }
}

/// Everything one project's check and export say needs attention, as Home items and per-step badges.
struct ProjectAttention {
    var items: [AttentionItem] = []
    var byStep: [String: [AttentionItem]] = [:]

    func badge(for step: String) -> StepBadge {
        byStep[step]?.map { StepBadge.from(kind: $0.kind, level: $0.level) }.min() ?? .ok
    }

    /// The worst badge among a step's descendants, so a collapsed parent still shows what is under it.
    func worstBelow(_ step: Step, steps: [String: Step]) -> StepBadge {
        var worst = StepBadge.ok
        var queue = step.children
        while let id = queue.popLast() {
            worst = min(worst, badge(for: id))
            queue += steps[id]?.children ?? []
        }
        return worst
    }

    init() {}

    init(project: ProjectEntry, export: ExportDoc?, report: CheckReport?) {
        let folder = project.folder
        func absolute(_ f: String?) -> String? {
            guard let f, !f.isEmpty else { return nil }
            return f.hasPrefix("/") ? f : (folder as NSString).appendingPathComponent(f)
        }
        var out: [AttentionItem] = []
        func add(_ level: AttentionItem.Level, _ kind: String, _ nodes: [String], _ msg: String,
                 file: String? = nil, line: Int? = nil) {
            out.append(AttentionItem(id: "\(project.path)#\(out.count)", project: project.path, projectName: project.name,
                                     level: level, kind: kind, nodes: nodes, message: msg, file: file, line: line))
        }
        if let report {
            for t in report.tree {
                add(t.level == "approval" ? .approval : .problem, t.kind, t.nodes, t.msg)
            }
            for b in report.builds {
                for p in b.problems {
                    add(.problem, p.kind, p.nodes, "\(b.name): \(p.msg)", file: absolute(p.file), line: p.line)
                }
            }
            for run in report.compare {
                if run.missingReference == true {
                    add(.problem, "comparison", [], "run '\(run.run)': no reference trace from \(run.reference)")
                }
                for b in run.builds where !b.ok && !b.missing && report.mutants?[b.build] == nil {
                    add(.problem, "comparison", [], "run '\(run.run)': \(b.build) differs from \(run.reference) "
                        + "(details: `ladder check`)")
                }
            }
            for (m, caught) in (report.mutants ?? [:]) where caught == 0 {
                add(.problem, "comparison", [], "mutant \(m) was not caught by any run")
            }
            for w in report.warnings { add(.warning, w.kind, w.nodes, w.msg) }
        }
        for s in export?.steps ?? [] {
            for n in s.openNotes { add(.note, n.homeKind, [s.id], n.text) }
        }
        items = out
        for item in out { for n in item.nodes { byStep[n, default: []].append(item) } }
    }
}
