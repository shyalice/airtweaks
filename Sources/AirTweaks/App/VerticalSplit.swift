import SwiftUI
import AppKit

/// thin resize-splitter — NSView handles cursor + mouse tracking via a modal
/// event loop so drag never fights swiftui state re-render.
struct DragSplitter: NSViewRepresentable {
    @Binding var height: CGFloat
    let minHeight: CGFloat
    let maxHeight: CGFloat

    func makeNSView(context: Context) -> Splitter {
        let v = Splitter()
        v.minHeight = minHeight
        v.maxHeight = maxHeight
        v.getCurrentHeight = { height }
        v.setHeight = { newValue in
            DispatchQueue.main.async { height = newValue }
        }
        return v
    }

    func updateNSView(_ nsView: Splitter, context: Context) {
        nsView.minHeight = minHeight
        nsView.maxHeight = maxHeight
        nsView.getCurrentHeight = { height }
    }

    final class Splitter: NSView {
        var minHeight: CGFloat = 60
        var maxHeight: CGFloat = 800
        var getCurrentHeight: (() -> CGFloat)?
        var setHeight: ((CGFloat) -> Void)?

        override init(frame frameRect: NSRect) {
            super.init(frame: frameRect)
            wantsLayer = true
            layer?.backgroundColor = NSColor.separatorColor.cgColor
        }
        required init?(coder: NSCoder) { fatalError() }

        override func resetCursorRects() {
            super.resetCursorRects()
            addCursorRect(bounds, cursor: .resizeUpDown)
        }

        override func mouseDown(with event: NSEvent) {
            guard let window else { return }
            let startMouseY = window.mouseLocationOutsideOfEventStream.y
            let startHeight = getCurrentHeight?() ?? 200
            var currentEvent: NSEvent? = event
            while let e = currentEvent, e.type != .leftMouseUp {
                if e.type == .leftMouseDragged {
                    let curY = window.mouseLocationOutsideOfEventStream.y
                    // window Y grows upward; log is at bottom, so dragging UP = grow log
                    var next = startHeight + (curY - startMouseY)
                    next = min(max(next, minHeight), maxHeight)
                    setHeight?(next)
                }
                currentEvent = window.nextEvent(matching: [.leftMouseUp, .leftMouseDragged],
                                                until: .distantFuture,
                                                inMode: .eventTracking,
                                                dequeue: true)
            }
        }
    }
}
