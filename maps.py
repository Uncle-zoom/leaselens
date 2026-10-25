"""Maps: a calm light basemap, the building as a blue pin, 5- and 10-minute walking rings, small labelled amenity circles,
noise sources as distinct SHAPES (square, triangle, diamond) and the owner's other buildings in a toggleable, clustered layer.

Everything here is drawn client-side from data we already hold, so markers and the legend render offline (only the basemap
tiles need the network). Colour is never the only signal: every marker has a letter and a shape, and tooltips give the name
and the walking minutes.
"""
from __future__ import annotations

import html
import json
import math

import folium
from folium import plugins

import icons
import styles
from wording import walk_phrase

WALK_M_PER_MIN = 5000 / 60          # 5 km/h
DETOUR = 1.3                          # walking distance = straight line x 1.3 (same rule as sources/core/walking.py)
RING_MINUTES = (5, 10)
# Calm, keyless gray basemaps. CARTO Positron / Dark Matter were the first choice, but basemaps.cartocdn.com now answers every tile
# with an "API KEY REQUIRED" watermark, so the equivalent Esri light and dark gray canvases are used instead (free, no key).
LIGHT_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
DARK_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
ATTR = 'Tiles &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors'

# category -> (icon name, label, shape class, how many to draw). The icon says WHAT it is; the shape says amenity (circle) vs noise
# (square, triangle, diamond), so colour is never the only signal.
AMENITY = {"grocery": ("cart", "Grocery", "am", 5), "gym": ("dumbbell", "Gym", "am", 3), "park": ("tree", "Park", "am", 3),
           "bus_stop": ("bus", "Bus stop", "am", 5), "train_station": ("train", "Train or subway", "am", 3), "pharmacy": ("plus", "Pharmacy", "am", 2)}
NOISE = {"bar": ("mug", "Bar", "sq", 4), "pub": ("mug", "Pub", "sq", 4), "nightclub": ("music", "Nightclub", "sq", 4),
         "fire_station": ("flame", "Fire station", "tri", 3), "hospital": ("plus", "Hospital", "tri", 3), "rail_line": ("train", "Rail line", "dia", 1)}


def js_safe(text: str) -> str:
    """Make OpenStreetMap-supplied text safe for a map tooltip. folium writes tooltips into JavaScript template literals, so a
    backtick, backslash or ${ in a place name (OpenStreetMap has a park named 'Garden Street Park`') breaks the whole map script,
    and angle brackets would be read as HTML."""
    text = html.escape(str(text or ""), quote=False)
    return text.replace("\\", "/").replace("`", "'").replace("${", "$ {")


def walk_minutes(distance_m: float) -> float:
    return round(distance_m * DETOUR / WALK_M_PER_MIN, 1)


def ring_radius_m(minutes: int) -> float:
    """Straight-line radius whose walking time (x1.3 detour) is `minutes`."""
    return minutes * WALK_M_PER_MIN / DETOUR


def _tok(theme: str, key: str) -> str:
    return styles.TOKENS[theme][key]


def _map_css() -> str:
    L, D = styles.TOKENS["light"], styles.TOKENS["dark"]
    def block(t):
        return (f"--green:{t['green']};--orange:{t['orange']};--red:{t['red']};--onst:{t['on_status']};--card:{t['card']};"
                f"--text:{t['text']};--text2:{t['text2']};--accent:{t['accent_text']};--ind:{t['owner_marker']};--rel:{t['related']};--hair:{t['hairline']};")
    return f"""<style>
:root {{ {block(L)} }}
@media (prefers-color-scheme: dark) {{ :root {{ {block(D)} }} }}
body {{ font-family:{styles.FONT_STACK}; }}
.mk {{ width:24px; height:24px; display:flex; align-items:center; justify-content:center; color:var(--onst);
  border:2px solid var(--card); box-shadow:0 1px 3px rgba(0,0,0,.35); box-sizing:border-box; }}
.mk svg {{ width:14px; height:14px; stroke-width:2.4; }}
.mk.am {{ background:var(--green); border-radius:50%; }}
.mk.sq {{ background:var(--red); border-radius:4px; }}
.mk.tri {{ background:var(--orange); clip-path:polygon(50% 0, 100% 100%, 0 100%); border:0; align-items:flex-end; padding-bottom:2px; width:28px; height:25px; }}
.mk.tri svg {{ width:12px; height:12px; }}
.mk.dia {{ background:var(--red); transform:rotate(45deg); border-radius:3px; width:22px; height:22px; }}
.mk.dia svg {{ transform:rotate(-45deg); width:13px; height:13px; }}
.mk.ow {{ background:var(--ind); border-radius:6px; }}
.mk.rel {{ background:var(--rel); clip-path:polygon(25% 5%, 75% 5%, 100% 50%, 75% 95%, 25% 95%, 0 50%); border:0; width:28px; height:26px; }}
.mk.cl {{ width:34px; height:34px; font:700 13px {styles.FONT_STACK}; }}
.mk.cl.rel {{ width:36px; height:34px; }} .mk.cl.am {{ border-radius:50%; }} .mk.cl.sq {{ border-radius:8px; }} .mk.cl.ow {{ border-radius:10px; }}
.ringlbl {{ font:600 11px {styles.FONT_STACK}; color:var(--accent); background:var(--card); padding:1px 6px; border-radius:99px;
  border:1px solid var(--accent); white-space:nowrap; }}
.leaflet-control-layers {{ border-radius:12px !important; }}
</style>"""


def legend_html(owner: bool = False, owner_only: bool = False, chain: bool = False) -> str:
    """The legend, drawn under the map (not on top of it) so it never hides anything. Same icons and shapes as the markers."""
    def sw(cls, icon_name):
        return f'<span class="lg {cls}">{icons.svg(icon_name)}</span>'
    items = [(f'<span class="lg pin">{icons.svg("building")}</span>', "The building"),
             (sw("am", "cart"), "Amenity (grocery, gym, park, bus, train)"), (sw("sq", "mug"), "Noise: bar, pub, nightclub"),
             (sw("tri", "flame"), "Noise: fire station, hospital"), (sw("dia", "train"), "Noise: rail line"),
             ('<span class="lg ring"></span>', "Walking rings: 5 and 10 minutes")]
    if owner_only:      # the owner map shows just the building and the owner's other buildings
        items = [items[0], (sw("ow", "building"), "Owner's other buildings (a number means several close together; zoom in to open it)")]
    elif owner:
        items.append((sw("ow", "building"), "Owner's other buildings (toggle on the map)"))
    if chain:
        items.append((sw("rel", "link"), "Buildings of companies linked through a shared principal (toggle on the map)"))
    return ('<ul class="ll-legend" aria-label="Map legend">' + "".join(f"<li>{i}<span>{html.escape(t)}</span></li>" for i, t in items) + "</ul>")


def _basemap(m: folium.Map) -> None:
    """Light gray by default; dark gray when the visitor's system is in dark mode. No key needed."""
    light = folium.TileLayer(tiles=LIGHT_TILES, attr=ATTR, name="Light map", max_zoom=19, max_native_zoom=16, control=False)
    dark = folium.TileLayer(tiles=DARK_TILES, attr=ATTR, name="Dark map", max_zoom=19, max_native_zoom=16, control=False, show=False)
    light.add_to(m)
    dark.add_to(m)
    m.get_root().script.add_child(folium.Element(
        "window.addEventListener('load', function () { if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) { "
        f"{m.get_name()}.removeLayer({light.get_name()}); {dark.get_name()}.addTo({m.get_name()}); }} }});"))


def ring_bounds(lat: float, lon: float, minutes: int = 10) -> list[list[float]]:
    """South-west and north-east corners of the box around the `minutes`-minute walking ring."""
    r = ring_radius_m(minutes)
    dlat = r / 111_320
    dlon = r / (111_320 * math.cos(math.radians(lat)))
    return [[lat - dlat, lon - dlon], [lat + dlat, lon + dlon]]


def _responsive(m: folium.Map, bounds: list[list[float]] | None = None) -> None:
    """A map drawn while its tab or panel is hidden measures 0 x 0. Re-measure when its box changes. A timer is more reliable than a
    resize event: browsers do not always send one to an iframe that was hidden. folium writes the map's own code after this element,
    so wait for the page to load first."""
    name = m.get_name()
    # Watch the box ourselves (not Leaflet's cached size: Leaflet also re-measures on a window resize, which would hide the change from us).
    # When the width or height changes, re-measure; for the first two changes also re-fit `bounds`, so the view still fits after the
    # iframe was first measured at the wrong size (a hidden tab, a closed expander).
    refit = (f" if (fitted < 2) {{ fitted++; {name}.fitBounds({json.dumps(bounds)}, {{padding: [20, 20]}}); }}" if bounds else "")
    m.get_root().script.add_child(folium.Element(
        "window.addEventListener('load', function () { var fitted = 0, lw = 0, lh = 0; setInterval(function () { var c = " + name + ".getContainer();"
        " if (c.clientWidth && (c.clientWidth !== lw || c.clientHeight !== lh)) { lw = c.clientWidth; lh = c.clientHeight; "
        + name + ".invalidateSize();" + refit + " } }, 400); });"))


def _icon(icon_name: str, cls: str, size=(24, 24)) -> folium.DivIcon:
    return folium.DivIcon(html=f'<div class="mk {cls}" aria-hidden="true">{icons.svg(icon_name)}</div>', icon_size=size,
                          icon_anchor=(size[0] // 2, size[1] // 2), class_name="")


def _cluster(cls: str, radius: int = 40):
    """Nearby markers merge into one numbered bubble (same shape as the markers it hides) that opens when you zoom in."""
    js = ("function (c) { return L.divIcon({html: '<div class=\"mk " + cls + " cl\"><span>' + c.getChildCount() + '</span></div>', "
          "className: '', iconSize: [34, 34]}); }")
    return plugins.MarkerCluster(icon_create_function=js, options={"maxClusterRadius": radius, "showCoverageOnHover": False})


def _routed(walking: dict | None) -> dict[tuple, float]:
    """(name, lat, lon) -> routed minutes when walking.py has them."""
    out = {}
    for r in (walking or {}).get("results", []):
        out[(r.get("name"), round(r["lat"], 5), round(r["lon"], 5))] = r["walk_min"]
    return out


def _pin_tip(p: dict) -> str:
    extra = f" · via {p['company']}" if p.get("company") else ""
    return js_safe(f"{p['address']} · {p['owner']}{extra} · {p['match_type']} ({p['confidence']} confidence)")


def build_block_map(lat: float, lon: float, places=None, walking: dict | None = None, owner_pins: list[dict] | None = None,
                    owner_total: int | None = None, chain_pins: list[dict] | None = None, chain_total: int | None = None) -> folium.Map:
    m = folium.Map(location=[lat, lon], zoom_start=14, tiles=None, control_scale=True, zoom_control=True)
    m.get_root().header.add_child(folium.Element(_map_css()))
    _basemap(m)
    bounds = ring_bounds(lat, lon, max(RING_MINUTES))
    m.fit_bounds(bounds, padding=(20, 20))                    # open zoomed to fit the 10-minute walking ring
    for minutes in RING_MINUTES:
        r = ring_radius_m(minutes)
        folium.Circle([lat, lon], radius=r, color="#0071E3", weight=1.5, dash_array="6 6", fill=False,
                      tooltip=f"About {minutes} minutes on foot").add_to(m)
        folium.Marker([lat + r / 111_320, lon], icon=folium.DivIcon(html=f'<span class="ringlbl">{minutes} min walk</span>', icon_size=(70, 18),
                                                                    icon_anchor=(35, 9), class_name=""), interactive=False).add_to(m)
    routed = _routed(walking)
    if places is not None and places.ok:
        # nearby markers merge into numbered bubbles: one cluster for amenities, one for noise sources
        clusters = {"am": _cluster("am").add_to(m), "noise": _cluster("sq").add_to(m)}
        per: dict[str, int] = {}
        for p in places.data["results"]:
            spec = AMENITY.get(p["category"]) or NOISE.get(p["category"])
            if not spec:
                continue
            icon_name, label, cls, keep = spec
            per[p["category"]] = per.get(p["category"], 0) + 1
            if per[p["category"]] > keep:
                continue
            minutes = routed.get((p["name"], round(p["lat"], 5), round(p["lon"], 5)), walk_minutes(p["distance_m"]))
            name = p["name"] or label
            size = (28, 25) if cls == "tri" else (22, 22) if cls == "dia" else (24, 24)
            folium.Marker([p["lat"], p["lon"]], icon=_icon(icon_name, cls, size),
                          tooltip=js_safe(f"{name} · {label} · {walk_phrase(minutes, p['distance_m'])}")).add_to(clusters["am" if cls == "am" else "noise"])
    if owner_pins:
        fg = folium.FeatureGroup(name=f"Owner's other buildings ({len(owner_pins)} of {owner_total or len(owner_pins)})", show=False)
        cluster = _cluster("ow", 45).add_to(fg)
        for p in owner_pins:
            folium.Marker([p["lat"], p["lon"]], icon=_icon("building", "ow"),
                          tooltip=_pin_tip(p)).add_to(cluster)
        fg.add_to(m)
    if chain_pins:
        fg2 = folium.FeatureGroup(name=f"Related companies' buildings ({len(chain_pins)} of {chain_total or len(chain_pins)})", show=False)
        cl2 = _cluster("rel", 45).add_to(fg2)
        for p in chain_pins:
            folium.Marker([p["lat"], p["lon"]], icon=_icon("link", "rel", (28, 26)), tooltip=_pin_tip(p)).add_to(cl2)
        fg2.add_to(m)
    if owner_pins or chain_pins:
        folium.LayerControl(collapsed=False, position="topright").add_to(m)
    # added last and lifted above everything else, so the building is never hidden under another marker
    folium.Marker([lat, lon], tooltip="The building", z_index_offset=2000, icon=folium.Icon(color="blue", icon="home", prefix="fa")).add_to(m)
    _responsive(m, bounds)
    return m


def build_parcel_map(lat: float, lon: float, located: list[dict], total: int | None = None,
                     chain_pins: list[dict] | None = None, chain_total: int | None = None) -> folium.Map:
    """The building and the owner's other buildings, clustered (used inside 'Who owns this building?')."""
    m = folium.Map(location=[lat, lon], zoom_start=13, tiles=None, control_scale=True)
    m.get_root().header.add_child(folium.Element(_map_css()))
    _basemap(m)
    cluster = _cluster("ow", 45).add_to(m)
    for p in located:
        folium.Marker([p["lat"], p["lon"]], icon=_icon("building", "ow"), tooltip=_pin_tip(p)).add_to(cluster)
    if chain_pins:
        fg = folium.FeatureGroup(name=f"Related companies' buildings ({len(chain_pins)} of {chain_total or len(chain_pins)})", show=True)
        cl2 = _cluster("rel", 45).add_to(fg)
        for p in chain_pins:
            folium.Marker([p["lat"], p["lon"]], icon=_icon("link", "rel", (28, 26)), tooltip=_pin_tip(p)).add_to(cl2)
        fg.add_to(m)
        folium.LayerControl(collapsed=False, position="topright").add_to(m)
    folium.Marker([lat, lon], tooltip="This building", z_index_offset=2000, icon=folium.Icon(color="blue", icon="home", prefix="fa")).add_to(m)
    bounds = None
    if located or chain_pins:
        pts = [[lat, lon]] + [[p["lat"], p["lon"]] for p in (located or []) + (chain_pins or [])]
        bounds = [[min(p[0] for p in pts), min(p[1] for p in pts)], [max(p[0] for p in pts), max(p[1] for p in pts)]]
        m.fit_bounds(bounds, padding=(30, 30))
    _responsive(m, bounds)          # re-fits once the iframe has its real size (it can first be measured while hidden)
    return m


# kept so older call sites keep working
def build_map(lat: float, lon: float, places=None, radius_m: int = 800) -> folium.Map:
    return build_block_map(lat, lon, places)
