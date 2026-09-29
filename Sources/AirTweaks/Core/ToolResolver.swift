import Foundation

enum ToolResolver {

    static var python3: String {
        // dev-mode fallback only; production always uses bundled backend
        for c in ["/opt/homebrew/bin/python3",
                  "/usr/local/bin/python3",
                  "/usr/bin/python3"] {
            if FileManager.default.isExecutableFile(atPath: c) { return c }
        }
        return "/usr/bin/python3"
    }

    static func enrichedEnvironment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        let extras = [
            "/opt/homebrew/bin", "/opt/homebrew/sbin",
            "/usr/local/bin", "/usr/local/sbin",
        ]
        let current = env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        var parts = current.split(separator: ":").map(String.init)
        for e in extras where !parts.contains(e) { parts.append(e) }
        env["PATH"] = parts.joined(separator: ":")
        env["PYTHONUNBUFFERED"] = "1"
        return env
    }
}
