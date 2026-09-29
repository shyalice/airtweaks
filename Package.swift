// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "AirTweaks",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "AirTweaks", targets: ["AirTweaks"]),
    ],
    targets: [
        .executableTarget(
            name: "AirTweaks",
            path: "Sources/AirTweaks"
        ),
    ]
)
