import SwiftUI
import Combine

final class LogStore: ObservableObject {
    static let shared = LogStore()

    enum Level: String, CaseIterable, Identifiable {
        case debug, info, ok, warn, error
        var id: String { rawValue }

        var symbol: String {
            switch self {
            case .debug: return "ant"
            case .info:  return "info.circle"
            case .ok:    return "checkmark.circle"
            case .warn:  return "exclamationmark.triangle"
            case .error: return "xmark.octagon"
            }
        }

        var color: Color {
            switch self {
            case .debug: return .secondary
            case .info:  return .primary
            case .ok:    return .green
            case .warn:  return .orange
            case .error: return .red
            }
        }
    }

    struct Entry: Identifiable, Hashable {
        let id = UUID()
        let time: Date
        let level: Level
        let source: String
        let message: String
    }

    @Published private(set) var entries: [Entry] = []

    private let capacity = 5_000

    func log(_ level: Level, _ source: String, _ message: String) {
        let entry = Entry(time: Date(), level: level, source: source, message: message)
        DispatchQueue.main.async {
            self.entries.append(entry)
            if self.entries.count > self.capacity {
                self.entries.removeFirst(self.entries.count - self.capacity)
            }
        }
    }

    func clear() { DispatchQueue.main.async { self.entries.removeAll() } }

    func debug(_ src: String, _ msg: String) { log(.debug, src, msg) }
    func info(_ src: String, _ msg: String)  { log(.info,  src, msg) }
    func ok(_ src: String, _ msg: String)    { log(.ok,    src, msg) }
    func warn(_ src: String, _ msg: String)  { log(.warn,  src, msg) }
    func error(_ src: String, _ msg: String) { log(.error, src, msg) }

    static func format(_ e: Entry) -> String {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let level = e.level.rawValue.uppercased().padding(toLength: 5, withPad: " ", startingAt: 0)
        return "\(iso.string(from: e.time)) \(level) [\(e.source)] \(e.message)"
    }
}
