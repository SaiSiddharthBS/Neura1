# Builds docs/readme/schema.svg: the Neura1 graph schema, grouped, with relationship names on the links.
W, H = 1280, 820
COL = {"supply": "#5b8cff", "demand": "#fbbf24", "people": "#a78bfa", "knowledge": "#22d3ee", "work": "#34d399"}
cards = [  # key, title, x, y, w, h
    ("supply", "PRODUCTS · SUPPLY · STORES", 40, 130, 440, 300),
    ("demand", "DEMAND", 500, 130, 310, 300),
    ("people", "PEOPLE · ORGANISATION", 830, 130, 410, 300),
    ("knowledge", "KNOWLEDGE", 40, 450, 600, 310),
    ("work", "WORK", 660, 450, 580, 310),
]
# name -> (x, y, group, ghost)
N = {
    "Revision": (100, 210, "supply", 0), "Item": (280, 210, "supply", 0), "Quote": (405, 210, "supply", 0),
    "Certification": (100, 300, "supply", 0), "StockMove": (280, 300, "supply", 0), "Supplier": (405, 300, "supply", 0),
    "Receipt": (210, 390, "supply", 0), "PurchaseOrder": (395, 390, "supply", 0),
    "Customer": (565, 210, "demand", 0), "Order": (705, 210, "demand", 0), "Shipment": (565, 300, "demand", 0),
    "Build": (705, 300, "demand", 0), "Revision ·": (635, 390, "supply", 1),
    "Person": (1035, 255, "people", 0), "Team": (905, 205, "people", 0), "Organization": (905, 305, "people", 0),
    "Skill": (1170, 205, "people", 0), "Absence": (1170, 305, "people", 0), "Project": (1035, 385, "people", 0),
    "Source": (115, 530, "knowledge", 0), "Chunk": (300, 530, "knowledge", 0), "Decision": (480, 530, "knowledge", 0),
    "Document": (115, 625, "knowledge", 0), "ActionItem": (480, 625, "knowledge", 0),
    "Alias": (115, 715, "knowledge", 0), "Message": (320, 715, "knowledge", 0),
}
N.update({
    "Investigation": (750, 530, "work", 0), "Action": (940, 530, "work", 0), "Person ·": (1130, 530, "people", 1),
    "Event": (750, 625, "work", 0), "Skill ·": (940, 625, "people", 1), "Brief": (1130, 625, "work", 0),
    "Conversation": (750, 715, "work", 0), "Turn": (940, 715, "work", 0), "Channel": (1130, 715, "work", 0),
})
E = [  # a, b, label
    ("Revision", "Item", "CONTAINS {qty}"), ("Item", "Quote", "← FOR"), ("Revision", "Certification", "← CERTIFIES"),
    ("Item", "StockMove", "← MOVES"), ("Quote", "Supplier", "← QUOTED"), ("StockMove", "Receipt", ""),
    ("Receipt", "PurchaseOrder", "AGAINST"), ("PurchaseOrder", "Supplier", "FROM_SUPPLIER"), ("PurchaseOrder", "Item", ""),
    ("Customer", "Order", "PLACED"), ("Order", "Build", "FULFILLED_BY"), ("Shipment", "Customer", "SHIPPED_TO"),
    ("Build", "Revision ·", "BUILDS"), ("Shipment", "Revision ·", "OF_REV"),
    ("Person", "Team", "MEMBER_OF"), ("Person", "Organization", "HOLDS_ROLE"), ("Person", "Skill", "HAS_SKILL"),
    ("Person", "Absence", "HAS_ABSENCE"), ("Person", "Project", "WORKS_ON"),
    ("Chunk", "Source", "PART_OF"), ("Decision", "Chunk", "EVIDENCED_BY"), ("Document", "Source", "HAS_SOURCE"),
    ("Message", "Source", "PART_OF"), ("ActionItem", "Chunk", "FOUND_IN"),
    ("Investigation", "Action", "PRODUCED"), ("Action", "Person ·", "ASSIGNED_TO"), ("Action", "Skill ·", "NEEDS_SKILL"),
    ("Conversation", "Turn", "HAS_TURN"),
]
STOCK_EDGE_SKIP = {("StockMove", "Receipt")}

def width(name):
    return max(64, int(len(name.rstrip(" ·")) * 8.1) + 30)

out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
       'aria-label="The Neura1 graph schema: products, supply and stores; demand; people and organisation; knowledge; and work, with the relationships between them.">',
       '<defs><clipPath id="c"><rect width="1280" height="820" rx="28"/></clipPath>'
       '<radialGradient id="g" cx="50%" cy="0%" r="70%"><stop offset="0" stop-color="#3b6cff" stop-opacity=".28"/><stop offset="1" stop-color="#3b6cff" stop-opacity="0"/></radialGradient>'
       '<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#fff" fill-opacity=".05"/></pattern>'
       '<style>.t{font-family:Inter,"SF Pro Display",-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}'
       '.m{font-family:"JetBrains Mono","SF Mono",Menlo,Consolas,monospace}</style></defs>',
       '<g clip-path="url(#c)"><rect width="1280" height="820" fill="#05060b"/><rect width="1280" height="820" fill="url(#g)"/>'
       '<rect width="1280" height="820" fill="url(#dots)"/>',
       '<g class="t"><text x="64" y="70" font-size="13" letter-spacing="3.2" font-weight="700" fill="#9db4ff">THE GRAPH</text>'
       '<text x="64" y="104" font-size="27" font-weight="700" fill="#fff" letter-spacing="-.5">One company, one graph: records, knowledge and work, linked.</text></g>']
for key, title, x, y, w, h in cards:
    c = COL[key]
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="20" fill="{c}" fill-opacity=".05" stroke="{c}" stroke-opacity=".3"/>'
               f'<text class="t" x="{x + 20}" y="{y + 28}" font-size="11.5" letter-spacing="2.2" font-weight="700" fill="{c}">{title}</text>')
for a, b, label in E:
    if (a, b) in STOCK_EDGE_SKIP:
        continue
    (x1, y1, _, _), (x2, y2, _, _) = N[a], N[b]
    out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#c7d2fe" stroke-opacity=".35" stroke-width="1.3"/>')
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        vertical = abs(x1 - x2) < 10
        lw = len(label) * 6.2 + 12
        if vertical:
            out.append(f'<rect x="{mx + 6}" y="{my - 9}" width="{lw}" height="17" rx="5" fill="#05060b" fill-opacity=".85"/>'
                       f'<text class="m" x="{mx + 12}" y="{my + 3.5}" font-size="10" fill="#aab6d6">{label}</text>')
        else:
            out.append(f'<rect x="{mx - lw / 2}" y="{my - 9}" width="{lw}" height="17" rx="5" fill="#05060b" fill-opacity=".9"/>'
                       f'<text class="m" x="{mx}" y="{my + 3.5}" font-size="10" text-anchor="middle" fill="#aab6d6">{label}</text>')
for name, (x, y, group, ghost) in N.items():
    c = COL[group]
    w = width(name)
    label = name.rstrip(" ·")
    if ghost:
        out.append(f'<rect x="{x - w / 2}" y="{y - 15}" width="{w}" height="30" rx="15" fill="#05060b" stroke="{c}" stroke-opacity=".55" stroke-dasharray="3 3"/>'
                   f'<text class="t" x="{x}" y="{y + 4.5}" font-size="12.5" text-anchor="middle" fill="{c}" fill-opacity=".9">{label}</text>')
    else:
        out.append(f'<rect x="{x - w / 2}" y="{y - 15}" width="{w}" height="30" rx="15" fill="#0d1120" stroke="{c}" stroke-opacity=".7"/>'
                   f'<circle cx="{x - w / 2 + 14}" cy="{y}" r="4" fill="{c}"/>'
                   f'<text class="t" x="{x + 6}" y="{y + 4.5}" font-size="13" font-weight="600" text-anchor="middle" fill="#eef2ff">{label}</text>')
notes = [
    (60, 788, "Chunk —MENTIONS→ any record, —SAID_BY→ Person; vector + full-text indexed. Decision —ABOUT / INSTEAD_OF→ Item, —APPLIES_TO→ Revision."),
    (60, 806, "PurchaseOrder —ORDERS→ Item · Person —OWNS→ Item, Build, Customer · —LEADS→ Project · —BACKS_UP→ Person · Event —ON→ any record."),
]
out.append('<g class="m" font-size="11" fill="#8590aa">' + "".join(f'<text x="{x}" y="{y}">{t}</text>' for x, y, t in notes) + '</g>')
out.append('<rect x=".5" y=".5" width="1279" height="819" rx="27.5" fill="none" stroke="#fff" stroke-opacity=".12"/></g></svg>')
open("/Users/sai/Documents/Projects/Neura1-GraphHacks/docs/readme/schema.svg", "w").write("\n".join(out))
print("ok")
