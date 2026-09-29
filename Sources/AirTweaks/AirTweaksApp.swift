import SwiftUI
import AppKit

@main
struct AirTweaksApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var device = DeviceManager()
    @StateObject private var log = LogStore.shared

    var body: some Scene {
        Window("AirTweaks", id: "main") {
            ContentView()
                .environmentObject(device)
                .environmentObject(log)
                .frame(minWidth: 960, minHeight: 640)
                .task { await device.start() }
        }
        .windowToolbarStyle(.unified(showsTitle: true))
        .defaultSize(width: 1120, height: 760)
        .commands { CommandGroup(replacing: .newItem) { } }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)

        NSSetUncaughtExceptionHandler { exc in
            FatalAlert.show(title: "airtweaks crashed",
                            message: "\(exc.name.rawValue): \(exc.reason ?? "")")
        }

        if ResourceLocator.isBundledApp, ResourceLocator.bundledBackend == nil {
            FatalAlert.show(
                title: "airtweaks can't start",
                message: """
                the bundled backend binary is missing from this app.
                the app package is corrupt — re-download airtweaks.
                """
            )
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

enum FatalAlert {
    static func show(title: String, message: String) {
        DispatchQueue.main.async {
            let alert = NSAlert()
            alert.alertStyle = .critical
            alert.messageText = title
            alert.informativeText = message
            alert.addButton(withTitle: "quit")
            alert.runModal()
            NSApp.terminate(nil)
        }
    }
}
