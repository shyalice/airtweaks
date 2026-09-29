import SwiftUI
import UniformTypeIdentifiers

struct RingtonesView: View {
    @EnvironmentObject private var device: DeviceManager
    @EnvironmentObject private var log: LogStore

    @State private var tones: [String] = []
    @State private var loading: Bool = false
    @State private var pushing: Bool = false
    @State private var showPicker: Bool = false
    @State private var lastResult: String = ""

    var body: some View {
        PageScaffold(
            title: "ringtones",
            subtitle: "push custom .m4r/.m4a into the ringtones list. appears in settings after a media rescan."
        ) {
            onDevice
            pushNew
        }
        .fileImporter(
            isPresented: $showPicker,
            allowedContentTypes: [UTType.audio, UTType.mp3, UTType(filenameExtension: "m4r") ?? .audio]
        ) { r in
            if case .success(let url) = r { Task { await push(url) } }
        }
        .task { if tones.isEmpty { await refresh() } }
    }

    private var onDevice: some View {
        VStack(alignment: .leading, spacing: Theme.cardSpacing) {
            CardHeader(
                title: "on device",
                trailing: AnyView(
                    HStack(spacing: 8) {
                        Text("\(tones.count)").statusCapsule()
                        Button {
                            Task { await refresh() }
                        } label: {
                            Label("refresh", systemImage: "arrow.clockwise")
                        }
                        .disabled(loading || device.current == nil)
                        .buttonStyle(.borderless)
                    }
                )
            )
            if loading {
                HStack { ProgressView().controlSize(.small); Text("listing…").foregroundStyle(.secondary) }
            } else if tones.isEmpty {
                Text("no custom ringtones").foregroundStyle(.tertiary).italic()
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(tones, id: \.self) { name in
                        HStack {
                            Image(systemName: "waveform.circle").foregroundStyle(.tint)
                            Text(name).font(Theme.monospaceSmall).textSelection(.enabled)
                            Spacer()
                            Button(role: .destructive) {
                                Task { await delete(name) }
                            } label: {
                                Image(systemName: "trash")
                            }
                            .buttonStyle(.borderless)
                        }
                        .padding(.vertical, 2)
                    }
                }
            }
        }
        .card()
    }

    private var pushNew: some View {
        VStack(alignment: .leading, spacing: Theme.cardSpacing) {
            CardHeader(title: "push new")
            Text("ios ringtones are 30–40 s aac in .m4r. any .m4a renamed to .m4r works; longer clips get truncated.")
                .font(.callout)
                .foregroundStyle(.secondary)
            HStack {
                Spacer()
                Button {
                    showPicker = true
                } label: {
                    if pushing {
                        ProgressView().controlSize(.small).frame(minWidth: 120)
                    } else {
                        Label("choose file…", systemImage: "square.and.arrow.up")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(pushing || device.current == nil)
            }
            if !lastResult.isEmpty {
                Text(lastResult)
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        }
        .card()
    }

    private func refresh() async {
        guard let udid = device.current?.udid else { return }
        loading = true; defer { loading = false }
        do {
            let r = try await AirliftBridge.run(feature: "ringtones",
                                                input: ["udid": udid, "action": "list"],
                                                log: log)
            tones = (r["tones"] as? [String]) ?? []
        } catch {
            log.error("ringtones", "list: \(error.localizedDescription)")
        }
    }

    private func push(_ url: URL) async {
        guard let udid = device.current?.udid else { return }
        pushing = true; defer { pushing = false }
        let name = url.deletingPathExtension().lastPathComponent + ".m4r"
        do {
            let r = try await AirliftBridge.run(
                feature: "ringtones",
                input: ["udid": udid, "action": "push",
                        "source_path": url.path, "remote_name": name],
                log: log
            )
            if let path = r["remote_path"] as? String {
                lastResult = "pushed → \(path)"
                log.ok("ringtones", lastResult)
            } else if let err = r["error"] as? String {
                lastResult = "failed: \(err)"
                log.error("ringtones", lastResult)
            }
            await refresh()
        } catch {
            lastResult = "failed: \(error.localizedDescription)"
            log.error("ringtones", lastResult)
        }
    }

    private func delete(_ name: String) async {
        guard let udid = device.current?.udid else { return }
        pushing = true; defer { pushing = false }
        do {
            _ = try await AirliftBridge.run(feature: "ringtones",
                                            input: ["udid": udid, "action": "delete",
                                                    "remote_name": name],
                                            log: log)
            log.ok("ringtones", "deleted \(name)")
            await refresh()
        } catch {
            log.error("ringtones", "delete: \(error.localizedDescription)")
        }
    }
}
