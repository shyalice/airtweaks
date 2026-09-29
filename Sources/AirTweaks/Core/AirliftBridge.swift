import Foundation

enum AirliftBridge {

    struct BridgeError: Error, LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    struct Event {
        let type: String
        let payload: [String: Any]
    }

    @discardableResult
    static func run(feature: String,
                    input: [String: Any],
                    log: LogStore = .shared,
                    onEvent: @escaping (Event) -> Void = { _ in }
    ) async throws -> [String: Any] {
        let stdinJSON = try JSONSerialization.data(withJSONObject: input, options: [])

        let p = Process()
        if let bundled = ResourceLocator.bundledBackend {
            p.executableURL = bundled
            p.arguments = [feature]
        } else if !ResourceLocator.isBundledApp,
                  let scriptURL = ResourceLocator.pythonFeatureScript(named: feature) {
            p.executableURL = URL(fileURLWithPath: ToolResolver.python3)
            p.arguments = [scriptURL.path]
        } else {
            throw BridgeError(message:
                "bundled backend missing for feature '\(feature)'. reinstall airtweaks.")
        }
        p.environment = ToolResolver.enrichedEnvironment()

        let stdin = Pipe(); let stdout = Pipe(); let stderr = Pipe()
        p.standardInput = stdin; p.standardOutput = stdout; p.standardError = stderr

        try p.run()
        try stdin.fileHandleForWriting.write(contentsOf: stdinJSON)
        try stdin.fileHandleForWriting.close()

        let stdoutBuffer = StreamBuffer()
        let stderrBuffer = StreamBuffer()
        let resultBox = ResultBox()

        stdout.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty { return }
            for line in stdoutBuffer.append(data) {
                guard let obj = try? JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any]
                else { continue }
                let type = obj["type"] as? String ?? "log"
                if type == "log" {
                    let level = LogStore.Level(rawValue: (obj["level"] as? String) ?? "info") ?? .info
                    let msg = obj["message"] as? String ?? ""
                    log.log(level, feature, msg)
                }
                if type == "result" { resultBox.set(obj) }
                onEvent(Event(type: type, payload: obj))
            }
        }
        stderr.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if !data.isEmpty { _ = stderrBuffer.append(data) }
        }

        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            p.terminationHandler = { _ in cont.resume() }
        }

        let finalOut = stdout.fileHandleForReading.readDataToEndOfFile()
        if !finalOut.isEmpty {
            for line in stdoutBuffer.append(finalOut) {
                guard let obj = try? JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any]
                else { continue }
                let type = obj["type"] as? String ?? "log"
                if type == "result" { resultBox.set(obj) }
                if type == "log" {
                    let level = LogStore.Level(rawValue: (obj["level"] as? String) ?? "info") ?? .info
                    let msg = obj["message"] as? String ?? ""
                    log.log(level, feature, msg)
                }
            }
        }
        let finalErr = stderr.fileHandleForReading.readDataToEndOfFile()
        if !finalErr.isEmpty { _ = stderrBuffer.append(finalErr) }
        stdout.fileHandleForReading.readabilityHandler = nil
        stderr.fileHandleForReading.readabilityHandler = nil

        let stderrDump = stderrBuffer.dumpString()
        if !stderrDump.isEmpty {
            for line in stderrDump.split(separator: "\n") where !line.isEmpty {
                log.warn(feature, "stderr: \(line)")
            }
        }

        let final = resultBox.get()
        if p.terminationStatus != 0 && final["ok"] == nil {
            let hint = stderrDump.isEmpty
                ? "exit \(p.terminationStatus) — no output"
                : "exit \(p.terminationStatus): \(stderrDump.prefix(400))"
            throw BridgeError(message: hint)
        }
        return final
    }
}

private final class ResultBox: @unchecked Sendable {
    private var value: [String: Any] = [:]
    private let lock = NSLock()
    func set(_ v: [String: Any]) { lock.lock(); value = v; lock.unlock() }
    func get() -> [String: Any] { lock.lock(); defer { lock.unlock() }; return value }
}

private final class StreamBuffer: @unchecked Sendable {
    private var buffer = Data()
    private let lock = NSLock()

    func append(_ data: Data) -> [String] {
        lock.lock(); defer { lock.unlock() }
        buffer.append(data)
        var lines: [String] = []
        while let nl = buffer.firstIndex(of: 0x0a) {
            let lineData = buffer[..<nl]
            buffer.removeSubrange(...nl)
            if !lineData.isEmpty,
               let str = String(data: lineData, encoding: .utf8),
               !str.isEmpty {
                lines.append(str)
            }
        }
        return lines
    }

    func dumpString() -> String {
        lock.lock(); defer { lock.unlock() }
        return String(data: buffer, encoding: .utf8) ?? ""
    }
}
