import SwiftUI

struct DiagnosticsView: View {
    @EnvironmentObject private var device: DeviceManager
    @EnvironmentObject private var log: LogStore

    @State private var running: Bool = false
    @State private var lastPayload: [String: Any] = [:]
    @State private var confirmingReboot: Bool = false
    @State private var confirmingShutdown: Bool = false

    var body: some View {
        PageScaffold(
            title: "diagnostics",
            subtitle: "one-shot device queries, reboot and shutdown over usb."
        ) {
            readonly
            destructive
            if !lastPayload.isEmpty { lastResult }
        }
        .confirmationDialog("reboot iphone now?", isPresented: $confirmingReboot) {
            Button("reboot", role: .destructive) { Task { await run("reboot") } }
            Button("cancel", role: .cancel) { }
        }
        .confirmationDialog("shut down iphone?", isPresented: $confirmingShutdown) {
            Button("shutdown", role: .destructive) { Task { await run("shutdown") } }
            Button("cancel", role: .cancel) { }
        }
    }

    private var readonly: some View {
        VStack(alignment: .leading, spacing: Theme.cardSpacing) {
            CardHeader(title: "read-only")
            FlowRow(spacing: 8) {
                action("device info",    "info.circle",       "device_info")
                action("baseband",       "antenna.radiowaves.left.and.right", "baseband_info")
                action("battery",        "battery.100",       "battery")
                action("storage",        "internaldrive",     "storage")
                action("installed apps", "square.stack.3d.up","installed_apps")
            }
        }
        .card()
    }

    private var destructive: some View {
        VStack(alignment: .leading, spacing: Theme.cardSpacing) {
            CardHeader(title: "destructive")
            HStack(spacing: 10) {
                Button(role: .destructive) { confirmingReboot = true } label: {
                    Label("reboot", systemImage: "arrow.triangle.2.circlepath")
                }
                .disabled(device.current == nil || running)

                Button(role: .destructive) { confirmingShutdown = true } label: {
                    Label("shutdown", systemImage: "power")
                }
                .disabled(device.current == nil || running)
                Spacer()
            }
        }
        .card()
    }

    private var lastResult: some View {
        VStack(alignment: .leading, spacing: Theme.cardSpacing) {
            CardHeader(title: "last result")
            ScrollView {
                Text(prettyJSON(lastPayload))
                    .font(Theme.monospaceSmall)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: 360)
        }
        .card()
    }

    private func action(_ label: String, _ icon: String, _ act: String) -> some View {
        Button {
            Task { await run(act) }
        } label: {
            Label(label, systemImage: icon)
        }
        .disabled(device.current == nil || running)
    }

    private func run(_ action: String) async {
        guard let udid = device.current?.udid else { return }
        running = true; defer { running = false }
        do {
            let r = try await AirliftBridge.run(feature: "diagnostics",
                                                input: ["udid": udid, "action": action],
                                                log: log)
            lastPayload = r
            if let ok = r["ok"] as? Bool, ok {
                log.ok("diagnostics", "\(action) ok")
            } else if let err = r["error"] as? String {
                log.error("diagnostics", "\(action): \(err)")
            }
        } catch {
            log.error("diagnostics", "\(action): \(error.localizedDescription)")
        }
    }

    private func prettyJSON(_ d: [String: Any]) -> String {
        (try? JSONSerialization.data(withJSONObject: d,
                                     options: [.prettyPrinted, .sortedKeys]))
            .flatMap { String(data: $0, encoding: .utf8) }
            ?? "\(d)"
    }
}

private struct FlowRow<Content: View>: View {
    let spacing: CGFloat
    @ViewBuilder let content: () -> Content
    init(spacing: CGFloat = 8, @ViewBuilder content: @escaping () -> Content) {
        self.spacing = spacing
        self.content = content
    }
    var body: some View {
        HStack(spacing: spacing) { content() }
    }
}
