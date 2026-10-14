import Foundation

// The JSON the `ladder` tool prints. The app never parses `.ladder` text: every type here mirrors a command's output
// (`ladder projects`, `ladder export --regions`, `ladder check --json`). Fields the app does not use are left out.

// MARK: ladder projects

struct ProjectList: Decodable {
    var root: String
    var repoFile: String?
    var projects: [ProjectEntry]
}

struct ProjectEntry: Decodable, Identifiable, Hashable {
    var name: String
    var path: String          // absolute path of ladder.json
    var title: String
    var tree: String?
    var builds: [BuildEntry]?
    var links: [String: String]?   // alias -> absolute path of the linked ladder.json
    var error: String?

    var id: String { path }
    var folder: String { (path as NSString).deletingLastPathComponent }

    struct BuildEntry: Decodable, Hashable {
        var name: String
        var lang: String
        var files: [String]
    }
}

// MARK: ladder export --regions

struct ExportDoc: Decodable {
    var title: String?
    var treeFile: String?
    var steps: [Step]
    var data: [DataBlock]
    var rules: [String: String]
    var vocabulary: [Capability]
    var builds: [Build]?
    var check: CheckReport?      // with --regions: the check report the regions' problems came from
}

struct Step: Decodable, Identifiable, Hashable {
    var id: String
    var title: String
    var parent: String?
    var children: [String]
    var depth: Int
    var inputs: String
    var outputs: String
    var effects: String
    var how: [String]
    var notes: [String]
    var compare: [String]
    var reads: [String]
    var writes: [String]
    var calls: [String]
    var uses: [String]
    var hash: String
    var line: Int
    var reviewHash: String?   // what a person approves; `ladder edit --expect` refuses if the step is no longer this
    var approvedBy: String?
    var approvedAt: String?

    var isLeaf: Bool { children.isEmpty }

    /// Notes that wait for a person: unanswered questions, differences and decisions, and answers that say the
    /// behavior is a bug (the English still has to change: SPEC, "Answering a note").
    var openNotes: [Note] { notes.compactMap(Note.init).filter(\.isOpen) }

    /// Every piece of English in the step, for search.
    var searchText: String {
        ([id, title, "in: " + inputs, "out: " + outputs, "effects: " + effects] + how + notes + uses + calls + reads
            + writes + compare).joined(separator: "\n")
    }

    /// `calls:` lines parsed into (link alias, step ids): "api [api.1.2]" or "api [api.1] [api.2]".
    var callTargets: [(alias: String, ids: [String])] {
        calls.map { line in
            let alias = line.split(separator: " ").first.map(String.init) ?? ""
            return (alias, Self.bracketed(line))
        }
    }

    static func bracketed(_ text: String) -> [String] {
        var out: [String] = []
        var rest = Substring(text)
        while let open = rest.firstIndex(of: "["), let close = rest[open...].firstIndex(of: "]") {
            let inner = rest[rest.index(after: open)..<close]
            if !inner.isEmpty, !inner.hasPrefix("[") { out.append(String(inner)) }
            rest = rest[rest.index(after: close)...]
        }
        return out
    }
}

struct Note: Hashable {
    enum Kind: String { case question = "QUESTION", differs = "DIFFERS", decision = "DECISION", answered = "ANSWERED", plain }
    var kind: Kind
    var text: String

    init?(_ raw: String) {
        let t = raw.trimmingCharacters(in: .whitespaces)
        for k in [Kind.question, .differs, .decision, .answered] where t.hasPrefix(k.rawValue + ":") {
            kind = k
            text = String(t.dropFirst(k.rawValue.count + 1)).trimmingCharacters(in: .whitespaces)
            return
        }
        kind = .plain
        text = t
    }

    var isOpen: Bool {
        switch kind {
        case .question, .differs, .decision: true
        case .answered: text.lowercased().hasPrefix("bug")
        case .plain: false
        }
    }

    /// The Home kind: the note's word, or "ANSWERED bug" for an answer the English does not reflect yet.
    var homeKind: String { kind == .answered ? "ANSWERED bug" : kind.rawValue }
}

struct DataBlock: Decodable, Identifiable, Hashable {
    var name: String
    var fields: [Field]
    var rules: [String]
    var notes: [String]
    var id: String { name }

    struct Field: Decodable, Hashable {
        var name: String
        var description: String
    }
}

struct Capability: Decodable, Identifiable, Hashable {
    var name: String
    var inputs: String?
    var outputs: String?
    var id: String { name }
}

struct Build: Decodable, Identifiable, Hashable {
    var name: String
    var lang: String
    var mode: String
    var tagged: Bool
    var files: [BuildFile]
    var id: String { name }
}

struct BuildFile: Decodable, Hashable {
    var path: String
    var absolute: String
    var exists: Bool
    var lines: Int?
    var regions: [Region]
    var problems: [FileProblem]
}

struct FileProblem: Decodable, Hashable {
    var kind: String
    var line: Int
    var msg: String
}

struct Region: Decodable, Hashable {
    var kind: String          // node, support, contract
    var label: String
    var start: Int
    var end: Int
    var parent: Int?
    var steps: [String]
    var hashes: [String]
    var current: [Bool?]
    var problems: [String]

    var isStale: Bool { current.contains(false) || problems.contains { $0.hasPrefix("stale") } }
}

// MARK: ladder edit, answer, stamp --steps

/// The new parts of a step, as `ladder edit` takes them (and `ladder export` names them).
struct StepEdit: Codable, Equatable {
    var title: String
    var inputs: String
    var outputs: String
    var effects: String
    var how: [String]
    var notes: [String]
    var uses: [String]
    var compare: [String]

    init(_ s: Step) {
        title = s.title; inputs = s.inputs; outputs = s.outputs; effects = s.effects
        how = s.how; notes = s.notes; uses = s.uses; compare = s.compare
    }
}

struct EditResult: Decodable {
    var step: String
    var changed: Bool
    var written: Bool
    var diff: String
    var parts: [String]?
    var codeChanged: Bool
    var contractChanged: Bool
    var notesOnly: Bool
    var stale: [StaleRegion]
    var suggest: String?

    struct StaleRegion: Decodable, Hashable {
        var build: String
        var file: String
        var line: Int
        var steps: [String]
    }
}

struct StampResult: Decodable {
    var recorded: [Recorded]
    var stillOpen: [CheckReport.Item]
    var by: String
    var written: Bool

    struct Recorded: Decodable, Hashable {
        var id: String
        var kind: String
        var what: String
    }
}

/// `{"refused": "..."}`: the tool would not make the change, and says why.
struct Refusal: Decodable, LocalizedError {
    var refused: String
    var errorDescription: String? { refused }
}

// MARK: ladder check --json

struct CheckReport: Decodable {
    var status: String        // ok, problems, awaiting-approval
    var baseline: String?
    var tree: [Item]
    var builds: [BuildReport]
    var warnings: [Item]
    var compare: [CompareRun]
    var mutants: [String: Int]?
    var compared: Bool?
    var nothingCompared: Bool?

    enum CodingKeys: String, CodingKey {
        case status, baseline, tree, builds, warnings, compare, mutants, compared
        case nothingCompared = "nothing_compared"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        status = try c.decode(String.self, forKey: .status)
        baseline = try c.decodeIfPresent(String.self, forKey: .baseline)
        tree = try c.decodeIfPresent([Item].self, forKey: .tree) ?? []
        builds = try c.decodeIfPresent([BuildReport].self, forKey: .builds) ?? []
        warnings = try c.decodeIfPresent([Item].self, forKey: .warnings) ?? []
        compare = try c.decodeIfPresent([CompareRun].self, forKey: .compare) ?? []
        mutants = try c.decodeIfPresent([String: Int].self, forKey: .mutants)
        compared = try c.decodeIfPresent(Bool.self, forKey: .compared)
        nothingCompared = try c.decodeIfPresent(Bool.self, forKey: .nothingCompared)
    }

    /// One line of the report: a tree item, a build problem or a warning.
    struct Item: Decodable, Hashable {
        var kind: String
        var node: String?
        var msg: String
        var file: String?
        var line: Int?
        var level: String?    // tree items: "approval" or "problem" (set by `check --json`)

        /// The step, data block or capability ids the item is about ("a.1,a.2", "a.1, a.2" and a region's "a.1+a.2"
        /// name several).
        var nodes: [String] {
            guard let node else { return [] }
            return node.split(whereSeparator: { $0 == "," || $0 == "+" }).map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }
        }
    }

    struct BuildReport: Decodable, Hashable {
        var name: String
        var lang: String?
        var problems: [Item]
    }

    struct CompareRun: Decodable, Hashable {
        var run: String
        var reference: String
        var missingReference: Bool?
        var builds: [CompareBuild]

        enum CodingKeys: String, CodingKey {
            case run, reference, builds
            case missingReference = "missing_reference"
        }
    }

    struct CompareBuild: Decodable, Hashable {
        var build: String
        var ok: Bool
        var missing: Bool
        var why: String?
    }
}
