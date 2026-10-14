import Foundation
import XCTest
@testable import LadderReview

/// The app against the real tool: a small sample project is written to a temp folder, the plugin's tool runs on it,
/// and the app decodes what it prints. A change to the tool's JSON that the app cannot read fails here.
final class ToolJSONTests: XCTestCase {
    static let toolPath: String = {
        // apps/ladder-review/Tests/LadderReviewTests/<this file> -> repo root
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        return root.appendingPathComponent("plugins/ladder/tool/ladder.py").path
    }()

    var folder: URL!
    var tool: LadderTool { LadderTool(path: Self.toolPath) }

    override func setUp() async throws {
        folder = FileManager.default.temporaryDirectory.appendingPathComponent("ladder-review-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        _ = try await Shell.run("/usr/bin/env", ["git", "init", "-q", folder.path])
        try write("api/api.ladder", """
            data Alert
              id: the alert's number
              text: what it says

            [api.1] Answer the alerts
              in: GET /alerts
              out: the `Alert` list, newest first
              > answers every `Alert`, newest first
              note: QUESTION: should read alerts be left out?
            """)
        try write("api/ladder.json", #"{"title": "API", "tree": "api.ladder", "builds": [{"name": "ts", "lang": "typescript", "files": ["api.ts"]}]}"#)
        try write("client/client.ladder", """
            [c.1] Show the alerts
              in: nothing
              out: the alerts on screen
              calls: api [api.1]
              > loads the alerts from [api.1] and lists them
            """)
        try write("client/ladder.json", #"{"title": "Client", "tree": "client.ladder", "links": {"api": "../api/ladder.json"}, "builds": [{"name": "ts", "lang": "typescript", "files": ["client.ts"]}]}"#)
        // Tag both builds at the tree's current hashes, then approve.
        for (p, file, id) in [("api", "api.ts", "api.1"), ("client", "client.ts", "c.1")] {
            let pj = folder.appendingPathComponent("\(p)/ladder.json").path
            let hashes = String(decoding: try await tool.run(["hashes", pj], acceptedStatuses: [0]), as: UTF8.self)
            let hash = hashes.split(separator: "\n").first { $0.contains("\(id)@") }!
                .split(separator: "@")[1].prefix(6)
            try write("\(p)/\(file)", "// @node \(id)@\(hash)\nexport const f = () => 1\n// @end\n")
        }
        for p in ["api", "client"] {
            _ = try await tool.run(["stamp", folder.appendingPathComponent("\(p)/ladder.json").path], acceptedStatuses: [0])
        }
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: folder)
    }

    func write(_ rel: String, _ text: String) throws {
        let url = folder.appendingPathComponent(rel)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try text.write(to: url, atomically: true, encoding: .utf8)
    }

    func testProjectsExportAndCheckDecode() async throws {
        let list = try await tool.projects(in: folder.path)
        XCTAssertEqual(list.projects.map(\.name), ["api", "client"])
        let client = list.projects[1]
        XCTAssertEqual(client.links?["api"], list.projects[0].path)

        let export = try await tool.export(list.projects[0].path)
        XCTAssertEqual(export.steps.map(\.id), ["api.1"])
        XCTAssertEqual(export.data.map(\.name), ["Alert"])
        let region = try XCTUnwrap(export.builds?.first?.files.first?.regions.first)
        XCTAssertEqual(region.steps, ["api.1"])
        XCTAssertFalse(region.isStale)

        XCTAssertEqual(export.check?.status, "ok")     // export --regions brings the check report along
        let report = try await tool.check(list.projects[0].path)
        XCTAssertEqual(report.status, "ok")
    }

    func testAnEditedStepShowsOnHomeAndAsABadge() async throws {
        let api = folder.appendingPathComponent("api/api.ladder")
        let text = try String(contentsOf: api, encoding: .utf8).replacingOccurrences(of: "newest first\n  >", with: "oldest first\n  >")
        try text.write(to: api, atomically: true, encoding: .utf8)
        let list = try await tool.projects(in: folder.path)
        let entry = list.projects[0]
        let export = try await tool.export(entry.path)
        let report = try await tool.check(entry.path)
        XCTAssertEqual(report.status, "problems")         // the tagged code is now stale

        let attention = ProjectAttention(project: entry, export: export, report: report)
        let kinds = Set(attention.items.map { "\($0.level):\($0.kind)" })
        XCTAssertTrue(kinds.contains("approval:edited"), "\(kinds)")
        XCTAssertTrue(kinds.contains("problem:stale"), "\(kinds)")
        XCTAssertTrue(kinds.contains("note:QUESTION"), "\(kinds)")
        XCTAssertEqual(attention.badge(for: "api.1"), .stale)  // the code problem outranks the edit
        XCTAssertEqual(export.builds?.first?.files.first?.regions.first?.isStale, true)

        // The client calls the edited step: check says so on the client's side.
        let clientReport = try await tool.check(list.projects[1].path)
        XCTAssertTrue(clientReport.tree.contains { $0.kind == "linked-changed" && $0.nodes == ["c.1"] }
                      || clientReport.warnings.contains { $0.nodes.contains("c.1") },
                      "\(clientReport.tree) \(clientReport.warnings)")
    }
}

final class PureTests: XCTestCase {
    func testNotes() {
        XCTAssertEqual(Note("QUESTION: is 50 inclusive?")?.kind, .question)
        XCTAssertTrue(Note("DIFFERS: web rounds")!.isOpen)
        XCTAssertFalse(Note("ANSWERED: keep as is (Ben, 2026-10-11)")!.isOpen)
        XCTAssertTrue(Note("ANSWERED: bug: should round down (Ben, 2026-10-11)")!.isOpen)
        XCTAssertFalse(Note("the list is never empty")!.isOpen)
    }

    func testBracketedIds() {
        XCTAssertEqual(Step.bracketed("api [api.1.2] [api.3]"), ["api.1.2", "api.3"])
        XCTAssertEqual(Step.bracketed("no ids"), [])
    }

    func testItemNodesSplit() {
        let item = CheckReport.Item(kind: "hand-edited", node: "a.1+a.2", msg: "")
        XCTAssertEqual(item.nodes, ["a.1", "a.2"])
        XCTAssertEqual(CheckReport.Item(kind: "x", node: "a.1, b.2", msg: "").nodes, ["a.1", "b.2"])
    }

    func testFuzzyFileMatch() {
        let files = ["src/hooks/useRequirePermission.ts", "src/permissions/require.ts", "README.md"]
        XCTAssertEqual(FuzzyMatch.rank("reqperm", files, limit: 5).first, "src/hooks/useRequirePermission.ts")
        XCTAssertNil(FuzzyMatch.score("zzz", "README.md"))
    }
}

@MainActor
final class NavigationTests: XCTestCase {
    func testBackAndForwardRetraceTheScreens() {
        let store = RepoStore()
        let a = Route.step(project: "p", id: "ms.1"), b = Route.step(project: "p", id: "ms.2")
        XCTAssertFalse(store.canGoBack)
        store.route = a                       // Home -> ms.1 -> ms.2 (a link in ms.1's English)
        store.route = b
        store.route = b                       // selecting the screen you are on records nothing
        store.goBack()
        XCTAssertEqual(store.route, a)
        store.goBack()
        XCTAssertEqual(store.route, .home)
        XCTAssertFalse(store.canGoBack)
        store.goForward()
        XCTAssertEqual(store.route, a)
        store.route = .data(project: "p", name: "Options")   // a new screen drops the forward history
        XCTAssertFalse(store.canGoForward)
        store.goBack()
        XCTAssertEqual(store.route, a)
    }
}

/// Editing, answering and approving through the tool, as the app's sheets call it.
final class EditThroughToolTests: XCTestCase {
    var folder: URL!
    var pj: String { folder.appendingPathComponent("ladder.json").path }
    var tool: LadderTool { LadderTool(path: ToolJSONTests.toolPath) }

    override func setUp() async throws {
        folder = FileManager.default.temporaryDirectory.appendingPathComponent("ladder-edit-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        _ = try await Shell.run("/usr/bin/env", ["git", "init", "-q", folder.path])
        _ = try await Shell.run("/usr/bin/env", ["git", "-C", folder.path, "config", "user.name", "Pat"])
        try "[a.1] Add one\n  in: a number\n  out: the number plus one\n  > answers the number plus one\n  note: QUESTION: what about NaN?\n"
            .write(to: folder.appendingPathComponent("t.ladder"), atomically: true, encoding: .utf8)
        try "".write(to: folder.appendingPathComponent("c.ts"), atomically: true, encoding: .utf8)
        try #"{"title": "t", "tree": "t.ladder", "builds": [{"name": "code", "lang": "typescript", "files": ["c.ts"]}]}"#
            .write(to: folder.appendingPathComponent("ladder.json"), atomically: true, encoding: .utf8)
    }

    override func tearDown() async throws { try? FileManager.default.removeItem(at: folder) }

    func testEditPreviewThenWrite() async throws {
        let step = try await tool.export(pj).steps[0]
        var change = StepEdit(step)
        change.how = ["answers the number plus two"]
        let preview = try await tool.edit(pj, step: "a.1", change, expect: step.reviewHash, dryRun: true)
        XCTAssertTrue(preview.changed)
        XCTAssertFalse(preview.written)
        XCTAssertTrue(preview.diff.contains("+  > answers the number plus two"))
        let done = try await tool.edit(pj, step: "a.1", change, expect: step.reviewHash, dryRun: false)
        XCTAssertTrue(done.written)
        let reread = try await tool.export(pj).steps[0]
        XCTAssertEqual(reread.how, ["answers the number plus two"])
        // the same change again, against the review hash read before it: refused with the tool's reason
        do {
            _ = try await tool.edit(pj, step: "a.1", change, expect: step.reviewHash, dryRun: true)
            XCTFail("a stale read must be refused")
        } catch let r as Refusal {
            XCTAssertTrue(r.refused.contains("changed since it was read"))
        }
    }

    func testAnswerThenApprove() async throws {
        let step = try await tool.export(pj).steps[0]
        _ = try await tool.answer(pj, step: "a.1", note: 1, "keep as is", plain: false, expect: step.reviewHash, dryRun: false)
        let after = try await tool.export(pj).steps[0]
        XCTAssertTrue(after.notes[0].hasPrefix("ANSWERED: keep as is (Pat, "))
        XCTAssertTrue(after.openNotes.isEmpty)
        let preview = try await tool.approve(pj, ids: ["a.1"], dryRun: true)
        XCTAssertEqual(preview.recorded.map(\.what), ["new"])
        _ = try await tool.approve(pj, ids: ["a.1"], dryRun: false)
        let approved = try await tool.export(pj).steps[0]
        XCTAssertEqual(approved.approvedBy, "Pat")
    }
}
