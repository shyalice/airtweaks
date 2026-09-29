import SwiftUI

struct Feature: Identifiable, Hashable {
    let id: String
    let title: String
    let subtitle: String
    let systemImage: String
    let section: Section
    let view: () -> AnyView

    enum Section: String, CaseIterable, Identifiable {
        case radio   = "radio"
        case comms   = "comms"
        case media   = "media"
        case power   = "power tools"
        var id: String { rawValue }
    }

    static func == (lhs: Feature, rhs: Feature) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

enum FeatureRegistry {
    static let all: [Feature] = [
        Feature(
            id: "carrier-sim",
            title: "carrier bundle",
            subtitle: "swap the carrier profile on your sim",
            systemImage: "simcard.2",
            section: .radio,
            view: { AnyView(CarrierSimView()) }
        ),
        Feature(
            id: "call-history",
            title: "call history",
            subtitle: "add a fake call to recents",
            systemImage: "phone.badge.plus",
            section: .comms,
            view: { AnyView(CallHistoryView()) }
        ),
        Feature(
            id: "ringtones",
            title: "ringtones",
            subtitle: "push custom .m4r tones",
            systemImage: "waveform",
            section: .media,
            view: { AnyView(RingtonesView()) }
        ),
        Feature(
            id: "diagnostics",
            title: "diagnostics",
            subtitle: "device info, battery, reboot",
            systemImage: "stethoscope",
            section: .power,
            view: { AnyView(DiagnosticsView()) }
        ),
    ]

    static func grouped() -> [(Feature.Section, [Feature])] {
        Feature.Section.allCases.compactMap { section in
            let items = all.filter { $0.section == section }
            return items.isEmpty ? nil : (section, items)
        }
    }
}
