import SwiftUI

struct CallHistoryView: View {
    @EnvironmentObject private var device: DeviceManager
    @EnvironmentObject private var log: LogStore

    @State private var phoneNumber: String = ""
    @State private var displayName: String = ""
    @State private var direction: Direction = .incoming
    @State private var answered: Bool = false
    @State private var durationSec: Int = 0
    @State private var minutesAgo: Int = 5
    @State private var isoCountry: String = ""
    @State private var serviceProvider: String = "com.apple.Telephony"
    @State private var running: Bool = false

    enum Direction: String, CaseIterable, Identifiable {
        case incoming, outgoing
        var id: String { rawValue }
        var label: String { rawValue }
    }

    var body: some View {
        PageScaffold(
            title: "call history",
            subtitle: "insert a fake entry into recents. survives reboot; the phone app shows it as a real call."
        ) {
            entryForm
            actionRow
        }
    }

    private var entryForm: some View {
        VStack(alignment: .leading, spacing: Theme.cardSpacing) {
            CardHeader(title: "call details")
            row("phone number") {
                TextField("+1234567890", text: $phoneNumber)
                    .textFieldStyle(.roundedBorder)
                    .font(Theme.monospaceFont)
            }
            row("contact name (optional)") {
                TextField("blank to show raw number", text: $displayName)
                    .textFieldStyle(.roundedBorder)
            }
            row("iso country") {
                TextField("us", text: $isoCountry)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 80)
            }
            Divider().padding(.vertical, 2)
            row("direction") {
                Picker("", selection: $direction) {
                    ForEach(Direction.allCases) { d in Text(d.label).tag(d) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(width: 220)
            }
            row("answered") {
                Toggle(isOn: $answered) { EmptyView() }
                    .toggleStyle(.switch)
            }
            if answered {
                row("duration (sec)") {
                    Stepper("\(durationSec)", value: $durationSec, in: 0...36000, step: 15)
                }
            }
            row("minutes ago") {
                Stepper("\(minutesAgo)", value: $minutesAgo, in: 0...60*24*7)
            }
            row("service") {
                Picker("", selection: $serviceProvider) {
                    Text("cellular").tag("com.apple.Telephony")
                    Text("facetime video").tag("com.apple.FaceTime")
                    Text("facetime audio").tag("com.apple.FaceTime.Audio")
                }
                .pickerStyle(.menu)
                .labelsHidden()
                .frame(width: 220)
            }
        }
        .card()
    }

    private var actionRow: some View {
        HStack {
            Button {
                Task { await snapshotDB() }
            } label: {
                Label("snapshot db", systemImage: "square.and.arrow.down")
            }
            .disabled(device.current == nil || running)
            Spacer()
            Button {
                Task { await inject() }
            } label: {
                if running {
                    ProgressView().controlSize(.small).frame(minWidth: 140)
                } else {
                    Label("insert call", systemImage: "phone.arrow.down.left")
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(device.current == nil || running || phoneNumber.isEmpty)
        }
        .padding(.horizontal, 4)
    }

    @ViewBuilder private func row<Content: View>(
        _ title: String,
        @ViewBuilder _ content: () -> Content
    ) -> some View {
        HStack(alignment: .center, spacing: 12) {
            Text(title)
                .frame(width: 190, alignment: .leading)
                .foregroundStyle(.secondary)
            content()
            Spacer()
        }
    }

    private func inject() async {
        guard let udid = device.current?.udid else { return }
        running = true; defer { running = false }
        do {
            _ = try await AirliftBridge.run(
                feature: "call_history",
                input: [
                    "udid": udid,
                    "action": "insert",
                    "phone_number": phoneNumber,
                    "display_name": displayName,
                    "direction": direction.rawValue,
                    "answered": answered,
                    "duration_sec": durationSec,
                    "minutes_ago": minutesAgo,
                    "iso_country": isoCountry,
                    "service_provider": serviceProvider,
                ],
                log: log
            )
            log.ok("call_history", "insert done")
        } catch {
            log.error("call_history", error.localizedDescription)
        }
    }

    private func snapshotDB() async {
        guard let udid = device.current?.udid else { return }
        running = true; defer { running = false }
        do {
            let r = try await AirliftBridge.run(
                feature: "call_history",
                input: ["udid": udid, "action": "snapshot"],
                log: log
            )
            if let path = r["saved_to"] as? String {
                log.ok("call_history", "snapshot: \(path)")
            }
        } catch {
            log.error("call_history", error.localizedDescription)
        }
    }
}
