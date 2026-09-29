import SwiftUI

enum Theme {
    static let cornerRadius: CGFloat = 12
    static let cardPadding: CGFloat = 16
    static let pagePadding: CGFloat = 20
    static let sectionSpacing: CGFloat = 14
    static let cardSpacing: CGFloat = 12
    static let hairline = Color(nsColor: .separatorColor)
    static let panelBackground = Color(nsColor: .windowBackgroundColor)
    static let capsuleBackground = Color.secondary.opacity(0.15)
    static let monospaceFont = Font.system(.callout, design: .monospaced)
    static let monospaceSmall = Font.system(.caption, design: .monospaced)
}

extension View {
    func card(padding: CGFloat = Theme.cardPadding) -> some View {
        self
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.panelBackground)
            .overlay(
                RoundedRectangle(cornerRadius: Theme.cornerRadius, style: .continuous)
                    .stroke(Theme.hairline, lineWidth: 0.5)
            )
            .clipShape(RoundedRectangle(cornerRadius: Theme.cornerRadius, style: .continuous))
    }

    // legacy alias — TODO: drop once all callers migrate
    func groupedCard(padding: CGFloat = Theme.cardPadding) -> some View {
        card(padding: padding)
    }

    func statusCapsule(color: Color = .secondary) -> some View {
        self
            .font(.caption.weight(.medium))
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Theme.capsuleBackground, in: Capsule())
    }
}

struct PageHeader: View {
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.title2.weight(.semibold))
            Text(subtitle)
                .font(.callout)
                .foregroundStyle(.secondary)
        }
    }
}

struct CardHeader: View {
    let title: String
    var trailing: AnyView? = nil

    var body: some View {
        HStack {
            Text(title).font(.subheadline.weight(.semibold))
            Spacer()
            if let trailing { trailing }
        }
    }
}

struct PageScaffold<Content: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder let content: () -> Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.sectionSpacing) {
                PageHeader(title: title, subtitle: subtitle)
                content()
            }
            .padding(Theme.pagePadding)
            .frame(maxWidth: .infinity, alignment: .topLeading)
        }
    }
}
