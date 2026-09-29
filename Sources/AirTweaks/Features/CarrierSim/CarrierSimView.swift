import SwiftUI

struct CarrierSimView: View {
    @EnvironmentObject private var device: DeviceManager
    @EnvironmentObject private var log: LogStore

    struct Donor: Identifiable, Hashable {
        let id: String
    }

    @State private var donors: [Donor] = []
    @State private var selected: String = ""
    @State private var customName: String = ""
    @State private var useCustom: Bool = false
    @State private var filterText: String = ""
    @State private var running: Bool = false
    @State private var lastActionSummary: String = ""

    private var effectiveDonor: String {
        useCustom
            ? customName.trimmingCharacters(in: .whitespacesAndNewlines)
            : selected
    }

    private var filteredDonors: [Donor] {
        guard !filterText.isEmpty else { return donors }
        let q = filterText.lowercased()
        return donors.filter { $0.id.lowercased().contains(q) }
    }

    var body: some View {
        PageScaffold(
            title: "carrier bundle",
            subtitle: "attach any apple-signed carrier profile to your sim by planting an imsi symlink."
        ) {
            donorPicker
            actionRow
            if !lastActionSummary.isEmpty { summaryLine }
            explainer
        }
        .task { if donors.isEmpty { await loadDonors() } }
    }

    private var donorPicker: some View {
        VStack(alignment: .leading, spacing: Theme.cardSpacing) {
            CardHeader(
                title: "donor bundle",
                trailing: AnyView(
                    HStack(spacing: 8) {
                        Text("\(donors.count) bundles").statusCapsule()
                        Button {
                            Task { await loadDonors() }
                        } label: {
                            Label("refresh", systemImage: "arrow.clockwise")
                        }
                        .disabled(running)
                        .buttonStyle(.borderless)
                    }
                )
            )
            Toggle(isOn: $useCustom) {
                Text(useCustom ? "custom bundle name" : "pick from local list").font(.callout)
            }
            .toggleStyle(.switch)
            .controlSize(.small)

            if useCustom {
                TextField("e.g. Telus_PublicMobile_ca.bundle", text: $customName)
                    .textFieldStyle(.roundedBorder)
                    .font(Theme.monospaceFont)
            } else {
                HStack(spacing: 10) {
                    TextField("filter", text: $filterText)
                        .textFieldStyle(.roundedBorder)
                        .frame(maxWidth: 220)
                    Picker("", selection: $selected) {
                        ForEach(filteredDonors) { d in
                            Text(d.id).tag(d.id)
                        }
                    }
                    .pickerStyle(.menu)
                    .labelsHidden()
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .card()
    }

    private var actionRow: some View {
        HStack(spacing: 10) {
            Button {
                Task { await run("status") }
            } label: {
                Label("status", systemImage: "info.circle")
            }
            .disabled(device.current == nil || running)

            Button {
                Task { await run("check") }
            } label: {
                Label("check", systemImage: "checkmark.shield")
            }
            .disabled(running)

            Spacer()

            Button(role: .destructive) {
                Task { await run("restore") }
            } label: {
                Label("restore", systemImage: "arrow.uturn.backward")
            }
            .disabled(device.current == nil || running)

            Button {
                Task { await run("apply") }
            } label: {
                if running {
                    ProgressView().controlSize(.small).frame(minWidth: 100)
                } else {
                    Label("apply", systemImage: "arrow.down.circle")
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(device.current == nil || running || effectiveDonor.isEmpty)
        }
        .padding(.horizontal, 4)
    }

    private var summaryLine: some View {
        Text(lastActionSummary)
            .font(.callout)
            .foregroundStyle(.secondary)
            .padding(.horizontal, 4)
    }

    private var explainer: some View {
        VStack(alignment: .leading, spacing: 8) {
            CardHeader(title: "what each action does")
            bullet("apply", "plant imsi→donor symlinks, then trigger a commcenter re-scan.")
            bullet("restore", "strip our imsi symlinks so commcenter falls back to the stock bundle.")
            bullet("status", "print the active bundle per sim (from coretelephony).")
            bullet("check", "offline preflight: bundled trigger integrity + framework load.")
        }
        .card()
    }

    private func bullet(_ head: String, _ body: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(head)
                .font(.callout.weight(.semibold))
                .frame(width: 60, alignment: .leading)
            Text(body)
                .font(.callout)
                .foregroundStyle(.secondary)
        }
    }

    private func loadDonors() async {
        running = true; defer { running = false }
        do {
            let r = try await AirliftBridge.run(
                feature: "carrier_sim",
                input: ["action": "list_donors"],
                log: log
            )
            let raw = (r["donors"] as? [[String: Any]]) ?? []
            donors = raw.compactMap { d in
                guard let file = d["file"] as? String else { return nil }
                return Donor(id: file)
            }
            if selected.isEmpty, let first = donors.first { selected = first.id }
            log.ok("carrier_sim", "loaded \(donors.count) bundles")
        } catch {
            log.error("carrier_sim", error.localizedDescription)
        }
    }

    private func run(_ action: String) async {
        running = true; defer { running = false }
        var input: [String: Any] = ["action": action]
        if let udid = device.current?.udid { input["udid"] = udid }
        if action == "apply" || action == "check" { input["donor"] = effectiveDonor }
        do {
            let r = try await AirliftBridge.run(feature: "carrier_sim", input: input, log: log)
            let ok = (r["ok"] as? Bool) ?? false
            if ok {
                lastActionSummary = "\(action) → ok"
                log.ok("carrier_sim", lastActionSummary)
            } else {
                let err = (r["error"] as? String) ?? "no error message"
                lastActionSummary = "\(action) → failed: \(err)"
                log.error("carrier_sim", lastActionSummary)
            }
        } catch {
            lastActionSummary = "\(action) → \(error.localizedDescription)"
            log.error("carrier_sim", lastActionSummary)
        }
    }
}
