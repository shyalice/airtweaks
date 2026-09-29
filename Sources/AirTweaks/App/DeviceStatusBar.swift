import SwiftUI

struct DeviceStatusBar: View {
    @EnvironmentObject private var device: DeviceManager

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(device.current == nil ? Color.secondary.opacity(0.5) : Color.green)
                .frame(width: 8, height: 8)
                .shadow(color: device.current == nil ? .clear : .green.opacity(0.5), radius: 4)

            if device.devices.isEmpty {
                Text("no device")
                    .font(.headline)
                    .foregroundStyle(.secondary)
                if let err = device.lastPollError, !err.isEmpty {
                    Text(err.prefix(80))
                        .font(.caption)
                        .foregroundStyle(.orange)
                        .lineLimit(1)
                }
                Spacer()
                Button {
                    Task { await device.pollOnce() }
                } label: {
                    Label("rescan", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.borderless)
                .font(.caption)
            } else {
                devicePicker
                if let d = device.current {
                    Text(d.productType).statusCapsule()
                    Text("iOS \(d.productVersion)").statusCapsule()
                    Text(d.buildVersion).statusCapsule()
                    Spacer()
                    Text(d.udid)
                        .font(Theme.monospaceSmall)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
            }
        }
    }

    @ViewBuilder private var devicePicker: some View {
        if device.devices.count == 1, let only = device.devices.first {
            HStack(spacing: 8) {
                Text(only.name).font(.headline)
                ConnectionBadge(connection: only.connection)
            }
        } else {
            Picker("", selection: Binding(
                get: { device.selectedID ?? device.devices.first?.id ?? "" },
                set: { device.selectedID = $0 }
            )) {
                ForEach(device.devices) { d in
                    HStack(spacing: 6) {
                        Text(d.name)
                        Text("[\(d.connection.label)]").foregroundStyle(.secondary)
                    }
                    .tag(d.id)
                }
            }
            .pickerStyle(.menu)
            .labelsHidden()
            .frame(maxWidth: 280)
        }
    }
}

struct ConnectionBadge: View {
    let connection: DeviceManager.DeviceInfo.Connection

    var body: some View {
        Text(connection.label)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15), in: Capsule())
    }

    private var color: Color {
        switch connection {
        case .usb: return .green
        case .network: return .blue
        case .other: return .secondary
        }
    }
}
