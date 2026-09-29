import SwiftUI
import AppKit

struct LogConsole: View {
    @EnvironmentObject private var log: LogStore
    @State private var levelFilter: Set<LogStore.Level> = Set(LogStore.Level.allCases)
    @State private var query: String = ""
    @State private var autoscroll: Bool = true

    private var filtered: [LogStore.Entry] {
        log.entries.filter { entry in
            guard levelFilter.contains(entry.level) else { return false }
            if query.isEmpty { return true }
            let q = query.lowercased()
            return entry.message.lowercased().contains(q)
                || entry.source.lowercased().contains(q)
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            toolbar
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(.regularMaterial)
            Divider()
            LogTextView(entries: filtered, autoscroll: autoscroll)
                .background(Color(nsColor: .textBackgroundColor))
        }
    }

    private var toolbar: some View {
        HStack(spacing: 10) {
            Image(systemName: "text.viewfinder").foregroundStyle(.secondary)
            Text("logs").font(.subheadline.weight(.semibold))
            Text("\(filtered.count)/\(log.entries.count)")
                .font(.caption).foregroundStyle(.secondary)

            TextField("filter", text: $query)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 220)

            ForEach(LogStore.Level.allCases) { lvl in
                Toggle(isOn: Binding(
                    get: { levelFilter.contains(lvl) },
                    set: { on in
                        if on { levelFilter.insert(lvl) } else { levelFilter.remove(lvl) }
                    }
                )) {
                    Image(systemName: lvl.symbol).foregroundStyle(lvl.color)
                }
                .toggleStyle(.button)
                .buttonStyle(.borderless)
                .help(lvl.rawValue)
            }

            Spacer()

            Toggle(isOn: $autoscroll) {
                Label("autoscroll", systemImage: "chevron.down.circle")
            }
            .toggleStyle(.button)
            .buttonStyle(.borderless)

            Button {
                copyAll()
            } label: {
                Label("copy", systemImage: "doc.on.doc")
            }
            .buttonStyle(.borderless)
            .help("copy visible lines")

            Button(role: .destructive) {
                log.clear()
            } label: {
                Label("clear", systemImage: "trash")
            }
            .buttonStyle(.borderless)
        }
    }

    private func copyAll() {
        let text = filtered.map(LogStore.format).joined(separator: "\n")
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}

fileprivate struct LogTextView: NSViewRepresentable {
    let entries: [LogStore.Entry]
    let autoscroll: Bool

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSTextView.scrollableTextView()
        guard let tv = scroll.documentView as? NSTextView else { return scroll }
        tv.isEditable = false
        tv.isSelectable = true
        tv.isRichText = true
        tv.allowsUndo = false
        tv.usesFontPanel = false
        tv.font = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
        tv.textContainerInset = NSSize(width: 8, height: 6)
        tv.backgroundColor = .textBackgroundColor
        tv.drawsBackground = true
        tv.autoresizingMask = [.width]
        tv.textContainer?.widthTracksTextView = true
        tv.textContainer?.containerSize = NSSize(width: 0, height: CGFloat.greatestFiniteMagnitude)
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        guard let tv = scroll.documentView as? NSTextView,
              let storage = tv.textStorage else { return }
        let attributed = NSMutableAttributedString()
        let ts = DateFormatter()
        ts.dateFormat = "HH:mm:ss.SSS"
        for e in entries {
            let time  = ts.string(from: e.time)
            let level = e.level.rawValue.uppercased().padding(toLength: 5, withPad: " ", startingAt: 0)
            let src   = e.source.padding(toLength: 14, withPad: " ", startingAt: 0)

            let line = NSMutableAttributedString()
            line.append(.init(string: "\(time)  ",
                              attributes: [.foregroundColor: NSColor.tertiaryLabelColor]))
            line.append(.init(string: level + "  ",
                              attributes: [.foregroundColor: nsColor(for: e.level),
                                           .font: NSFont.monospacedSystemFont(ofSize: 12, weight: .semibold)]))
            line.append(.init(string: src + "  ",
                              attributes: [.foregroundColor: NSColor.secondaryLabelColor]))
            line.append(.init(string: e.message,
                              attributes: [.foregroundColor: NSColor.labelColor]))
            line.append(.init(string: "\n"))
            attributed.append(line)
        }
        storage.setAttributedString(attributed)
        if autoscroll { tv.scrollToEndOfDocument(nil) }
    }

    private func nsColor(for level: LogStore.Level) -> NSColor {
        switch level {
        case .debug: return .tertiaryLabelColor
        case .info:  return .labelColor
        case .ok:    return .systemGreen
        case .warn:  return .systemOrange
        case .error: return .systemRed
        }
    }
}
