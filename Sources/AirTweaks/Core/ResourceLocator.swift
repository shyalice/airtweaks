import Foundation

enum ResourceLocator {

    static let isBundledApp: Bool = {
        Bundle.main.bundleURL.pathExtension == "app"
    }()

    static let repoRoot: URL? = {
        if let res = Bundle.main.resourceURL,
           FileManager.default.fileExists(atPath: res.appendingPathComponent("Python/features").path) {
            return res
        }
        let exe = Bundle.main.executableURL ?? URL(fileURLWithPath: CommandLine.arguments[0])
        var cursor = exe.deletingLastPathComponent()
        for _ in 0..<8 {
            if FileManager.default.fileExists(
                atPath: cursor.appendingPathComponent("Python/features").path
            ) {
                return cursor
            }
            let parent = cursor.deletingLastPathComponent()
            if parent.path == cursor.path { break }
            cursor = parent
        }
        return nil
    }()

    static func pythonFeatureScript(named name: String) -> URL? {
        guard let root = repoRoot else { return nil }
        let url = root.appendingPathComponent("Python/features/\(name).py")
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    static let bundledBackend: URL? = {
        var candidates: [URL] = []
        if let res = Bundle.main.resourceURL {
            candidates.append(res.appendingPathComponent("backend/airtweaks-backend"))
        }
        if let root = repoRoot {
            candidates.append(root.appendingPathComponent(
                "build/backend-dist/airtweaks-backend/airtweaks-backend"))
        }
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0.path) }
    }()
}
