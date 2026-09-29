import Foundation
import SwiftUI

@MainActor
final class DeviceManager: ObservableObject {
    struct DeviceInfo: Equatable, Identifiable, Hashable {
        var udid: String
        var name: String
        var productType: String
        var productVersion: String
        var buildVersion: String
        var connection: Connection

        enum Connection: String, Equatable, Hashable {
            case usb
            case network
            case other

            init(raw: String) {
                switch raw.uppercased() {
                case "USB": self = .usb
                case "NETWORK": self = .network
                default: self = .other
                }
            }
            var label: String {
                switch self {
                case .usb: return "USB"
                case .network: return "Net"
                case .other: return "?"
                }
            }
        }

        /// composite id — same udid may appear twice (usb + network)
        var id: String { "\(udid)#\(connection.rawValue)" }
    }

    @Published private(set) var devices: [DeviceInfo] = []
    @Published var selectedID: DeviceInfo.ID? = nil
    @Published private(set) var lastPollError: String?

    var current: DeviceInfo? {
        if let id = selectedID, let hit = devices.first(where: { $0.id == id }) { return hit }
        return devices.first
    }

    private var pollTask: Task<Void, Never>?

    func start() async {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.pollOnce()
                try? await Task.sleep(nanoseconds: 3_000_000_000)
            }
        }
    }

    func stop() { pollTask?.cancel() }

    func pollOnce() async {
        do {
            let r = try await AirliftBridge.run(feature: "usbmux",
                                                input: ["action": "list"])
            let raw = (r["devices"] as? [[String: Any]]) ?? []
            let list: [DeviceInfo] = raw.compactMap { d in
                guard let udid = d["udid"] as? String, !udid.isEmpty else { return nil }
                return DeviceInfo(
                    udid: udid,
                    name: d["name"] as? String ?? "iPhone",
                    productType: d["product_type"] as? String ?? "?",
                    productVersion: d["product_version"] as? String ?? "?",
                    buildVersion: d["build_version"] as? String ?? "?",
                    connection: .init(raw: d["connection"] as? String ?? "?")
                )
            }
            let sorted = list.sorted {
                if $0.udid != $1.udid { return $0.udid < $1.udid }
                return connectionRank($0.connection) < connectionRank($1.connection)
            }
            devices = sorted
            if let sel = selectedID, !sorted.contains(where: { $0.id == sel }) {
                selectedID = sorted.first?.id
            }
            if selectedID == nil { selectedID = sorted.first?.id }
            lastPollError = nil
        } catch {
            devices = []
            selectedID = nil
            lastPollError = error.localizedDescription
        }
    }

    private func connectionRank(_ c: DeviceInfo.Connection) -> Int {
        switch c { case .usb: return 0; case .network: return 1; case .other: return 2 }
    }
}
