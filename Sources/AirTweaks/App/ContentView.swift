import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var device: DeviceManager
    @EnvironmentObject private var log: LogStore

    @State private var selection: Feature.ID? = FeatureRegistry.all.first?.id
    @State private var showLogs: Bool = true
    @AppStorage("airtweaks.logHeight") private var logHeight: Double = 220

    private let minLog: CGFloat = 90
    private let maxLog: CGFloat = 640

    var body: some View {
        NavigationSplitView {
            SidebarView(selection: $selection)
                .navigationSplitViewColumnWidth(min: 220, ideal: 240, max: 320)
        } detail: {
            VStack(spacing: 0) {
                DeviceStatusBar()
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                Divider()
                detailPanel
                if showLogs {
                    DragSplitter(
                        height: Binding(
                            get: { CGFloat(logHeight) },
                            set: { logHeight = Double($0) }
                        ),
                        minHeight: minLog,
                        maxHeight: maxLog
                    )
                    .frame(height: 3)
                    LogConsole()
                        .frame(height: CGFloat(logHeight))
                }
            }
        }
        .toolbar { toolbar }
    }

    @ViewBuilder private var detailPanel: some View {
        if let id = selection, let feature = FeatureRegistry.all.first(where: { $0.id == id }) {
            feature.view()
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        } else {
            ContentUnavailableView(
                "pick a tweak",
                systemImage: "sidebar.left",
                description: Text("choose a feature from the sidebar.")
            )
        }
    }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItem(placement: .primaryAction) {
            Toggle(isOn: $showLogs) {
                Label("logs", systemImage: "text.and.command.macwindow")
            }
            .help("toggle log console")
        }
    }
}
