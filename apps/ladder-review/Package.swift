// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "LadderReview",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "LadderReview", targets: ["LadderReview"])],
    targets: [
        .executableTarget(name: "LadderReview", path: "Sources/LadderReview"),
        .testTarget(name: "LadderReviewTests", dependencies: ["LadderReview"], path: "Tests/LadderReviewTests"),
    ]
)
