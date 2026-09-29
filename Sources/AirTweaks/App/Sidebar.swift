import SwiftUI

struct SidebarView: View {
    @Binding var selection: Feature.ID?

    var body: some View {
        List(selection: $selection) {
            ForEach(FeatureRegistry.grouped(), id: \.0) { section, features in
                Section(section.rawValue) {
                    ForEach(features) { feature in
                        NavigationLink(value: feature.id) {
                            Label {
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(feature.title).font(.body)
                                    Text(feature.subtitle)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }
                            } icon: {
                                Image(systemName: feature.systemImage)
                                    .foregroundStyle(.tint)
                            }
                            .padding(.vertical, 2)
                        }
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("airtweaks")
    }
}
