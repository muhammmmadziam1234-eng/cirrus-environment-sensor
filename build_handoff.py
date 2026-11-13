"""Extract nominal measurements and draw the enclosure handoff from cirrus.blend."""

import argparse
from collections import defaultdict
from html import escape
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parent
ASSEMBLY = "Cirrus | Explode control"
EPSILON = 0.001  # mm. Bias the section to one side of coincident mesh vertices.
SNAP = 0.00002  # mm. Join triangle intersection endpoints.
PALETTE = {
    "paper": "#f5f2eb", "panel": "#eeebe2", "ink": "#242c2c",
    "muted": "#4d5a58", "rule": "#b9bdb3", "oxide": "#8e3e29",
    "rear": "#a1a8a3", "cover": "#455151", "mount": "#66716f",
    "vent": "#a45337", "gasket": "#79a194", "board": "#447664",
    "flex": "#b17436", "rubber": "#363f3e", "metal": "#bac3bf",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def mm(value):
    return round(value, 4)


def between(a, b):
    return (a + b) / 2


def spans(contours, at, along=0):
    """Return the solid intervals on a line through an even-odd mesh section."""
    across = 1 - along
    hits = []
    for loop in contours:
        for a, b in zip(loop, loop[1:] + loop[:1]):
            if (a[across] > at) != (b[across] > at):
                fraction = (at - a[across]) / (b[across] - a[across])
                hits.append(a[along] + fraction * (b[along] - a[along]))
    hits.sort()
    require(len(hits) % 2 == 0, f"Odd profile intersection count at {at}")
    return list(zip(hits[::2], hits[1::2]))


def gaps(intervals):
    return [(a[1], b[0]) for a, b in zip(intervals, intervals[1:])]


class Model:
    def __init__(self):
        scene = bpy.context.scene
        self.root = bpy.data.objects[ASSEMBLY]
        require(abs(self.root["Explode"]) < 1e-6, "Save the model assembled (Explode = 0).")
        require(scene.unit_settings.system == "METRIC", "Expected a metric Blender scene.")
        self.factor = scene.unit_settings.scale_length * 1000
        self.depsgraph = bpy.context.evaluated_depsgraph_get()
        self.inverse = self.root.matrix_world.inverted()
        self.objects = {}
        for obj in bpy.data.collections["CIRRUS · assembly"].all_objects:
            if obj.type != "EMPTY":
                require(obj.parent.parent == self.root, f"Unexpected assembly parent: {obj.name}")
                require(obj.parent.location.length < 1e-5, f"Layer is offset: {obj.name}")
                self.objects[obj.name] = obj
        self.geometry = {}
        self.sections = {}

    def names(self, prefix):
        return sorted(name for name in self.objects if name.startswith(prefix))

    def mesh(self, name, evaluated):
        key = (name, evaluated)
        if key not in self.geometry:
            original = self.objects[name]
            obj = original.evaluated_get(self.depsgraph) if evaluated else original
            mesh = obj.to_mesh() if evaluated else obj.data
            require(isinstance(mesh, bpy.types.Mesh), f"Expected a mesh for {name}")
            try:
                transform = self.inverse @ obj.matrix_world
                points = [tuple((transform @ v.co) * self.factor) for v in mesh.vertices]
                mesh.calc_loop_triangles()
                triangles = [tuple(tri.vertices) for tri in mesh.loop_triangles]
                self.geometry[key] = points, triangles
            finally:
                if evaluated:
                    obj.to_mesh_clear()
        return self.geometry[key]

    def bounds(self, name, axis, evaluated=False):
        points, _ = self.mesh(name, evaluated)
        values = [point[axis] for point in points]
        return min(values), max(values)

    def through(self, name, x, y):
        """Check the evaluated part with a normal ray through its full depth."""
        obj = self.objects[name].evaluated_get(self.depsgraph)
        to_local = obj.matrix_world.inverted() @ self.root.matrix_world
        start = to_local @ Vector((x / self.factor, y / self.factor, 10))
        direction = to_local.to_3x3() @ Vector((0, 0, -1))
        return not obj.ray_cast(start, direction)[0]

    def section(self, name, axis, value, evaluated=True):
        key = (name, axis, value, evaluated)
        if key in self.sections:
            return self.sections[key]
        points, triangles = self.mesh(name, evaluated)
        cut = value + EPSILON
        axes = [i for i in range(3) if i != axis]
        graph = defaultdict(set)
        for tri in triangles:
            vertices = [points[i] for i in tri]
            crossings = []
            for a, b in zip(vertices, vertices[1:] + vertices[:1]):
                if (a[axis] > cut) == (b[axis] > cut):
                    continue
                fraction = (cut - a[axis]) / (b[axis] - a[axis])
                crossings.append(tuple(round((a[i] + fraction * (b[i] - a[i])) / SNAP)
                                       for i in axes))
            if crossings and crossings[0] != crossings[1]:
                a, b = crossings
                graph[a].add(b)
                graph[b].add(a)

        require(all(len(neighbors) == 2 for neighbors in graph.values()),
                f"Section has an open or branched contour: {name} at axis {axis}, {value} mm")
        contours = []
        while graph:
            start = min(graph)
            current, previous = start, None
            contour = []
            while True:
                contour.append(tuple(v * SNAP for v in current))
                following = min(graph.pop(current) - {previous})
                if following == start:
                    break
                previous, current = current, following
            contours.append(contour)
        self.sections[key] = contours
        return contours


FACE = "Cover | molded face"
CLEAT = "Wall cleat | formed plate"
FLOOR = "Rear | molded floor"
BULKHEAD = "Rear | closed electronics bulkhead"
LAND = "Cover | gasket compression land"
GASKET = "Seal | continuous molded silicone"
GROMMET = "Rear | silicone feedthrough"
GRILLE = "Vent cassette | red oxide grille"
SENSOR = "PCB | exposed sensor daughterboard"
FLEX = "Flex | removable sensor interconnect"


def measurements(model):
    bounds = model.bounds
    section = model.section
    wall = bounds(CLEAT, 2)[0]
    rear = bounds(FLOOR, 2)[0]
    front = bounds(FACE, 2)[1]
    vent_y = between(*bounds(GRILLE, 1))
    vent_z = between(*bounds(GRILLE, 2))
    grille = section(GRILLE, 2, vent_z, False)
    slot_x = gaps(spans(grille, vent_y))
    require(len(slot_x) == 13, "Expected 13 grille openings.")
    slot_lengths = []
    slot_bottoms = []
    for a, b in slot_x:
        center = between(a, b)
        slot_y, = gaps(spans(grille, center, along=1))
        require(model.through(GRILLE, center, vent_y), f"Blocked grille slot at x={center}")
        require(model.through(FACE, center, vent_y), f"Face obstructs slot at x={center}")
        slot_lengths.append(mm(slot_y[1] - slot_y[0]))
        slot_bottoms.append(slot_y[0])
    slot_widths = [mm(b - a) for a, b in slot_x]
    require(max(slot_widths) - min(slot_widths) < 0.001, "Grille slot widths differ.")
    window, = gaps(spans(section(FACE, 0, 0, False), 31, along=0))
    bulkhead_y = bounds(BULKHEAD, 1)[1]
    require(bulkhead_y < window[0] < min(slot_bottoms), "Vent openings overlap the bulkhead datum.")
    screen_z = max(bounds(name, 2, True)[1] for name in model.names("Vent cassette | debris screen")
                   if not name.endswith("frame"))
    require(screen_z < bounds(GRILLE, 2)[0], "Screen wire reaches the grille.")
    slit, = gaps(spans(section(GROMMET, 0, 0, False), 19.1, along=1))
    ribbon, = spans(section(FLEX, 0, 0), 19.1, along=1)
    require(slit[0] < ribbon[0] < ribbon[1] < slit[1], "Flex does not fit within the nominal slit.")
    gasket_base, gasket_top = bounds(GASKET, 2)
    land_bottom = bounds(LAND, 2)[0]
    free_height = gasket_top - gasket_base
    land_gap = land_bottom - gasket_base
    require(gasket_base < land_bottom < gasket_top, "Missing nominal gasket squeeze.")
    groove_outer = bounds("Rear | outer gasket rail", 1)[1]
    outer_rail = spans(section("Rear | outer gasket rail", 0, 0, False), 11.8)[-1]
    inner_rail = spans(section("Rear | inner gasket rail", 0, 0, False), 11.8)[-1]
    require(abs(groove_outer - outer_rail[1]) < 0.001, "Unexpected outer rail profile.")
    require(abs(bounds(BULKHEAD, 2)[1] - gasket_base) < 0.001, "Gasket is off its seat.")

    anchor_section = section(CLEAT, 2, between(*bounds(CLEAT, 2)), False)
    x_anchors = gaps(spans(anchor_section, 30.8))
    require(len(x_anchors) == 2, "Expected two columns of anchor slots.")
    x_centers = [between(*slot) for slot in x_anchors]
    y_anchors = gaps(spans(anchor_section, x_centers[0], along=1))
    require(len(y_anchors) == 2, "Expected two rows of anchor slots.")
    y_centers = [between(*slot) for slot in y_anchors]
    for x in x_centers:
        require(gaps(spans(anchor_section, x, along=1)) == y_anchors, "Anchor rows differ.")
        for y in y_centers:
            require(model.through(CLEAT, x, y), f"Blocked anchor slot at ({x}, {y})")
            openings = gaps(spans(anchor_section, y))
            require(openings == x_anchors, "Anchor columns differ.")

    flange_left, flange_right = model.names("Cleat rail | captured flange")
    lips = sorted(model.names("Rear receiver | undercut lip"), key=lambda name: bounds(name, 0))
    walls = sorted(model.names("Rear receiver | wall"), key=lambda name: bounds(name, 0))
    flange_x = bounds(flange_right, 0)
    throat = (bounds(lips[2], 0)[1], bounds(lips[3], 0)[0])
    channel = (bounds(walls[2], 0)[1], bounds(walls[3], 0)[0])
    capture = (throat[0] - flange_x[0], flange_x[1] - throat[1])
    side_play = (flange_x[0] - channel[0], channel[1] - flange_x[1])
    axial = bounds(flange_right, 2)[0] - max(bounds(name, 2)[1] for name in lips)
    lift = bounds(flange_right, 1)[1] - min(bounds(name, 1)[0] for name in lips)
    require(min(*capture, *side_play, axial, lift) > 0, "Invalid rail capture or clearance.")
    require(abs(capture[0] - capture[1]) < 0.001 and abs(side_play[0] - side_play[1]) < 0.001,
            "Receiver is no longer centered on the rail.")
    require(abs(lift - (bounds(flange_left, 1)[1] - bounds(lips[0], 1)[0])) < 0.001,
            "Rail disengagement differs by side.")

    return {
        "units": "mm",
        "envelope": {
            "width": mm(bounds(FACE, 0)[1] - bounds(FACE, 0)[0]),
            "height": mm(bounds(FACE, 1)[1] - bounds(FACE, 1)[0]),
            "body_depth": mm(front - rear),
            "wall_to_face": mm(front - wall),
            "wall_datum_to_rear_floor": mm(rear - wall),
        },
        "vent_and_feedthrough": {
            "slot_count": len(slot_x),
            "slot_width": slot_widths[0],
            "slot_lengths_left_to_right": slot_lengths,
            "bulkhead_to_lowest_grille_opening": mm(min(slot_bottoms) - bulkhead_y),
            "bulkhead_to_cover_window": mm(window[0] - bulkhead_y),
            "grille_to_screen_wire": mm(bounds(GRILLE, 2)[0] - screen_z),
            "feedthrough_slit_height": mm(slit[1] - slit[0]),
            "flex_height_at_feedthrough": mm(ribbon[1] - ribbon[0]),
        },
        "seal": {
            "free_height": mm(free_height),
            "seat_to_land": mm(land_gap),
            "rigid_overlap": mm(gasket_top - land_bottom),
            "nominal_squeeze_percent": mm(100 * (gasket_top - land_bottom) / free_height),
            "rail_channel_width_at_upper_straight": mm(outer_rail[0] - inner_rail[1]),
        },
        "mount": {
            "anchor_count": len(x_centers) * len(y_centers),
            "anchor_width": mm(x_anchors[0][1] - x_anchors[0][0]),
            "anchor_height": mm(y_anchors[0][1] - y_anchors[0][0]),
            "anchor_pitch_x": mm(x_centers[1] - x_centers[0]),
            "anchor_pitch_y": mm(y_centers[1] - y_centers[0]),
            "rail_pitch_x": mm(between(*flange_x) - between(*bounds(flange_left, 0))),
            "flange_width": mm(flange_x[1] - flange_x[0]),
            "receiver_throat_width": mm(throat[1] - throat[0]),
            "capture_per_side": mm(capture[0]),
            "flange_side_clearance_per_side": mm(side_play[0]),
            "flange_to_lip_depth_clearance": mm(axial),
            "upward_slide_to_clear_flange": mm(lift),
        },
    }



class Drawing:
    width, height = 1440, 960

    def __init__(self, title, description):
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>',
            """<style>
text { font-family: Arial, Helvetica, sans-serif; }
.brand { font-size: 16px; font-weight: 700; letter-spacing: 3.3px; }
.title { font-size: 51px; font-weight: 700; letter-spacing: -1.8px; }
.subtitle { font-size: 19px; }
.label { font-size: 19px; font-weight: 700; }
.note { font-size: 16px; }
.small { font-size: 14px; }
.ref { font-size: 15px; font-weight: 700; letter-spacing: 1.4px; }
.dim { font-family: "Courier New", monospace; font-size: 18px; font-weight: 700; }
</style>""",
            f'<defs><pattern id="overlap" width="5" height="5" patternUnits="userSpaceOnUse" '
            f'patternTransform="rotate(40)"><path d="M0 0V5" stroke="{PALETTE["oxide"]}" '
            'stroke-width="2.2"/></pattern></defs>',
        ]
        self.rect(0, 0, self.width, self.height, "paper")

    @staticmethod
    def color(name):
        return PALETTE.get(name, name)

    def add(self, element):
        self.parts.append(element)

    def rect(self, x, y, w, h, fill="none", stroke="none", dash=""):
        self.add(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
                 f'fill="{self.color(fill)}" stroke="{self.color(stroke)}" stroke-dasharray="{dash}"/>')

    def line(self, points, color="muted", width=1, dash=""):
        coords = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        self.add(f'<polyline points="{coords}" fill="none" stroke="{self.color(color)}" '
                 f'stroke-width="{width}" stroke-dasharray="{dash}" stroke-linejoin="round"/>')

    def dot(self, x, y, color="oxide"):
        self.add(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{self.color(color)}" '
                 f'stroke="{self.color("paper")}" stroke-width="0.85"/>')

    def text(self, x, y, text, kind="note", color="ink", anchor="start"):
        self.add(f'<text x="{x:.2f}" y="{y:.2f}" class="{kind}" fill="{self.color(color)}" '
                 f'text-anchor="{anchor}">{escape(str(text))}</text>')

    def path(self, contours, projection, fill, stroke="ink", width=0.8):
        if not contours:
            return
        data = path_data(contours, projection)
        self.add(f'<path d="{data}" fill="{self.color(fill)}" fill-rule="evenodd" '
                 f'stroke="{self.color(stroke)}" stroke-width="{width}" stroke-linejoin="round"/>')

    def clip(self, name, x, y, w, h):
        self.add(f'<clipPath id="{name}"><rect x="{x}" y="{y}" width="{w}" height="{h}"/></clipPath>')
        self.add(f'<g clip-path="url(#{name})">')

    def leader(self, target, elbow, end):
        self.line([target, elbow, end], "oxide", 1.05)
        self.dot(*target)

    def dimension(self, a, b, at, label, vertical=False, label_at=None):
        """Draw a horizontal or vertical dimension with extension lines and ticks."""
        def point(u, v):
            return (v, u) if vertical else (u, v)

        i, j = (1, 0) if vertical else (0, 1)
        for p in (a, b):
            away = 1 if at > p[j] else -1
            self.line([point(p[i], p[j] + 3 * away), point(p[i], at + 6 * away)], "muted")
            self.line([point(p[i] - 3.8, at + 3.8), point(p[i] + 3.8, at - 3.8)], "ink", 1.3)
        self.line([point(a[i], at), point(b[i], at)], "ink", 1.05)
        if label_at:
            self.text(*label_at, label, "dim")
        elif vertical:
            self.text(at - 8, between(a[i], b[i]) + 5, label, "dim", anchor="end")
        else:
            self.text(between(a[i], b[i]), at - 8, label, "dim", anchor="middle")

    def header(self, title, subtitle, sheet):
        self.text(50, 57, "C I R R U S   /   C-01", "brand")
        self.text(1390, 57, f"ENCLOSURE HANDOFF  /  {sheet}", "ref", "oxide", "end")
        self.text(49, 117, title, "title")
        self.text(51, 150, subtitle, "subtitle", "muted")
        self.line([(49, 174), (1391, 174)], "rule")

    def footer(self, text):
        self.line([(49, 913), (1391, 913)], "rule")
        self.text(50, 939, text, "small", "muted")
        self.text(1390, 939, "NOMINAL GEOMETRY  /  MM", "ref", "oxide", "end")

    def finish(self):
        return "\n".join(self.parts + ["</svg>", ""])


def path_data(contours, projection):
    return " ".join("M" + "L".join(f"{x:.2f},{y:.2f}" for x, y in map(projection, contour)) + "Z"
                    for contour in contours)


def profile(x, y, scale, reverse=False):
    if reverse:
        return lambda a: (x + a[1] * scale, y - a[0] * scale)
    return lambda a: (x + a[0] * scale, y - a[1] * scale)


def number(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def section_parts(model):
    parts = [
        (CLEAT, "mount"), (FLOOR, "rear"), ("Rear | perimeter wall", "rear"),
        (BULKHEAD, "rear"), ("Rear | outer gasket rail", "rear"),
        ("Rear | inner gasket rail", "rear"), (GROMMET, "rubber"), (GASKET, "gasket"),
        ("Cover | perimeter skirt", "cover"), (LAND, "cover"), (FACE, "cover"),
        ("Vent cassette | rear retention flange", "vent"), (GRILLE, "vent"),
        ("Vent cassette | debris screen frame", "mount"), ("PCB | main FR-4", "board"),
        (SENSOR, "board"), ("PCB | main MCU package", "rubber"),
        ("Sensing element | metal package", "metal"), ("Main PCB | underside FPC connector", "rubber"),
        ("Sensor PCB | FPC connector", "rubber"), (FLEX, "flex"),
    ]
    parts.extend((name, "mount") for name in model.names("Vent cassette | debris screen weft"))
    return parts


def section_sheet(model, data):
    envelope, vent, seal = (data[key] for key in ("envelope", "vent_and_feedthrough", "seal"))
    d = Drawing("Cirrus C-01 enclosure section",
                "Longitudinal section through the grille, sensor bay, bulkhead feedthrough and main PCB.")
    d.header("Inside the enclosure", "A–A  /  Longitudinal center section through the assembled enclosure", "01 / 02")
    d.text(50, 213, "A–A   ASSEMBLED SECTION", "ref")
    d.text(50, 238, "Wall at left · front face at right", "small", "muted")

    cut = profile(309, 540, 5.06, reverse=True)
    wall_z = model.bounds(CLEAT, 2)[0]
    front_z = model.bounds(FACE, 2)[1]
    low_y, high_y = model.bounds(FACE, 1)
    wall_x = cut((0, wall_z))[0]
    d.line([(wall_x, 253), (wall_x, 816)], "muted", 1.1, "5 5")
    d.text(wall_x - 8, 801, "Wall datum", "small", "muted", "end")
    for name, color in section_parts(model):
        d.path(model.section(name, 0, 0), cut, color)

    d.dimension(cut((high_y, 10)), cut((low_y, 10)), 205, number(envelope["height"]), vertical=True)
    d.dimension(cut((low_y, wall_z)), cut((low_y, front_z)), 855, number(envelope["wall_to_face"]))
    d.text(between(wall_x, cut((0, front_z))[0]), 880, "Wall datum to face", "small", "muted", "middle")
    details = [
        ((44.5, 31.5), (516, 309), 309, "Red-oxide grille",
         f'{vent["slot_count"]} slots · {number(vent["slot_width"])} mm wide'),
        ((39.2, 27.18), (518, 358), 358, "Debris screen",
         f'{number(vent["grille_to_screen_wire"])} mm behind grille'),
        ((34.5, 9.8), (520, 409), 409, "Sensor daughterboard", "Within the vented bay"),
        ((18.9, 8.0), (520, 487), 487, "Bulkhead feedthrough",
         f'{number(vent["feedthrough_slit_height"])} mm slit · {number(vent["flex_height_at_feedthrough"])} mm flex'),
        ((-18.0, 9.9), (520, 626), 626, "Main electronics PCB", "Inside the gasket perimeter"),
    ]
    for target, elbow, y, title, note in details:
        d.leader(cut(target), elbow, (539, y))
        d.text(549, y + 5, title, "label")
        d.text(549, y + 27, note, "small", "muted")

    detail_top_left = cut((22.5, 10.55))
    detail_bottom_right = cut((16.8, 15.7))
    d.rect(*detail_top_left, detail_bottom_right[0] - detail_top_left[0],
           detail_bottom_right[1] - detail_top_left[1], stroke="oxide", dash="3 2")
    d.line([(detail_bottom_right[0], detail_bottom_right[1]), (439, 473), (459, 473)], "oxide")
    d.text(465, 478, "D", "ref", "oxide")

    d.rect(801, 197, 590, 290, "panel")
    d.text(825, 227, "SECTION LOCATION", "ref")
    plan = profile(942, 357, 1.88)
    d.path(model.section(FACE, 2, 31.5), plan, "cover")
    d.path(model.section(GRILLE, 2, 31.5), plan, "vent")
    d.line([(942, 241), (942, 467)], "paper", 1.1, "7 4")
    d.line([(942, 241), (942, 254)], "oxide", 1.2)
    d.line([(942, 460), (942, 467)], "oxide", 1.2)
    d.text(955, 251, "A", "ref", "oxide")
    d.text(955, 469, "A", "ref", "oxide")
    d.text(1074, 279, "Vent isolation", "label")
    for y, key, text in [
        (319, "bulkhead_to_cover_window", "Bulkhead to cover-window edge"),
        (386, "bulkhead_to_lowest_grille_opening", "Bulkhead to nearest slot tip"),
    ]:
        d.text(1074, y, number(vent[key]) + " mm", "dim", "oxide")
        d.text(1074, y + 23, text, "note", "muted")
    d.text(1074, 455, "Measured vertically at the upper bulkhead.", "small", "muted")

    d.rect(801, 508, 590, 384, "panel")
    d.text(825, 540, "D   UPPER GASKET SHOULDER", "ref")
    d.text(825, 567, "Enlarged from A–A · rigid meshes shown", "small", "muted")
    zoom = profile(607, 1233, 29, reverse=True)
    d.clip("seal-zoom", 825, 594, 300, 170)
    for name, color in section_parts(model):
        d.path(model.section(name, 0, 0), zoom, color)
    land_path = path_data(model.section(LAND, 0, 0), zoom)
    d.add(f'<clipPath id="land"><path d="{land_path}"/></clipPath><g clip-path="url(#land)">')
    d.path(model.section(GASKET, 0, 0), zoom, "url(#overlap)", "none")
    d.add("</g></g>")
    seat = model.bounds(GASKET, 2)[0]
    top = model.bounds(GASKET, 2)[1]
    land = model.bounds(LAND, 2)[0]
    d.dimension(zoom((16.9, seat)), zoom((16.9, land)), 795,
                number(seal["seat_to_land"]), label_at=(1033, 801))
    d.dimension(zoom((16.9, seat)), zoom((16.9, top)), 838,
                number(seal["free_height"]), label_at=(1033, 844))
    d.text(846, 801, "Seat → land", "small", "muted")
    d.text(846, 844, "Free gasket", "small", "muted")
    d.line([(1144, 597), (1144, 851)], "rule")
    for y, fill, label in [(625, "cover", "Cover land"), (655, "gasket", "Free gasket"),
                           (685, "rear", "Bulkhead and rails"), (715, "url(#overlap)", "Rigid overlap")]:
        d.rect(1161, y - 13, 19, 13, fill, "muted")
        d.text(1192, y - 1, label, "note", "muted")
    d.text(1161, 779, number(seal["nominal_squeeze_percent"]) + "%", "title", "oxide")
    d.text(1163, 808, "Nominal axial squeeze", "label")
    d.text(1163, 833, number(seal["rigid_overlap"]) + " mm overlap of datums", "small", "muted")

    d.footer("Source  cirrus.blend   /   Cut contours from evaluated meshes   /   Concept geometry study")
    return d.finish()


def mounting_sheet(model, data):
    mount = data["mount"]
    d = Drawing("Cirrus C-01 wall cleat and rail engagement",
                "Dimensioned cleat elevation, rail cross-section and nominal upward disengagement travel.")
    d.header("Wall mounting & removal", "Cleat elevation and transverse section through one engaged rail", "02 / 02")
    d.text(50, 213, "CLEAT   ELEVATION", "ref")
    d.text(50, 238, "Viewed from the enclosure toward the wall", "small", "muted")
    elev = profile(412, 539, 5.7)
    d.path(model.section(CLEAT, 2, between(*model.bounds(CLEAT, 2))), elev, "rear")
    for prefix, color in [
        ("Cleat rail | captured flange", "mount"), ("Cleat | lower travel stop", "mount"),
        ("Cleat | spring latch", "metal"), ("Cleat | latch tooth", "metal"),

    ]:
        for name in model.names(prefix):
            z_mid = between(*model.bounds(name, 2, True))
            d.path(model.section(name, 2, z_mid), elev, color)

    ax, ay = mount["anchor_pitch_x"] / 2, mount["anchor_pitch_y"] / 2
    for x in (-ax, ax):
        for y in (-ay, ay):
            px, py = elev((x, y))
            d.line([(px - 8, py), (px + 8, py)], "muted", 0.75)
            d.line([(px, py - 8), (px, py + 8)], "muted", 0.75)
    d.dimension(elev((-ax, ay)), elev((ax, ay)), 266, number(mount["anchor_pitch_x"]))
    d.dimension(elev((-ax, ay)), elev((-ax, -ay)), 137, number(mount["anchor_pitch_y"]), vertical=True)
    rail_x = mount["rail_pitch_x"] / 2
    _, rail_bottom = elev((0, model.bounds("Cleat rail | captured flange", 1)[0]))
    d.dimension((elev((-rail_x, 0))[0], rail_bottom), (elev((rail_x, 0))[0], rail_bottom),
                817, number(mount["rail_pitch_x"]))
    d.text(412, 845, "Rail center pitch", "small", "muted", "middle")
    d.leader(elev((ax + mount["anchor_width"] / 2, ay)), (585, 323), (657, 323))
    d.text(663, 318, f'{mount["anchor_count"]} slots', "label")
    d.text(663, 342, f'{number(mount["anchor_width"])} × {number(mount["anchor_height"])}', "dim")
    cut_y = -2.4
    d.line([elev((-46, cut_y)), elev((46, cut_y))], "oxide", 1.25, "9 5")
    d.text(*elev((-49, cut_y + 1.4)), "B", "ref", "oxide", "end")
    d.text(*elev((49, cut_y + 1.4)), "B", "ref", "oxide")
    d.line([(743, 723), (743, 580), (736, 591), (743, 580), (750, 591)], "oxide", 1.8)
    d.text(743, 752, "LIFT", "ref", "oxide", "middle")

    d.rect(802, 197, 589, 520, "panel")
    d.text(826, 229, "B–B   RIGHT RAIL INTERFACE", "ref")
    d.text(826, 256, "Wall below · fixed cleat in dark gray", "small", "muted")
    rail_cut = profile(1102 - rail_x * 32, 417, 32)
    fixed = sorted(model.names("Cleat rail | captured flange"), key=lambda name: model.bounds(name, 0))
    flange = fixed[-1]
    flange_x = model.bounds(flange, 0)
    lips = sorted(model.names("Rear receiver | undercut lip"), key=lambda name: model.bounds(name, 0))
    throat = (model.bounds(lips[-2], 0)[1], model.bounds(lips[-1], 0)[0])
    d.clip("rail-zoom", 830, 398, 533, 275)
    for name, color in [(CLEAT, "mount"), (FLOOR, "rear")]:
        d.path(model.section(name, 1, cut_y), rail_cut, color)
    for prefix, color in [("Cleat rail | stem", "mount"), ("Cleat rail | captured flange", "mount"),
                          ("Rear receiver | wall", "rear"), ("Rear receiver | undercut lip", "rear")]:
        for name in model.names(prefix):
            d.path(model.section(name, 1, cut_y), rail_cut, color)
    d.add("</g>")
    d.line([(831, 398), (1362, 398)], "muted", 0.8, "5 4")
    d.text(834, 390, "Rear floor cropped", "small", "muted")
    d.dimension(rail_cut((flange_x[0], -1)), rail_cut((flange_x[1], -1)), 358,
                number(mount["flange_width"]))
    d.text(1102, 331, "Captured flange", "small", "muted", "middle")
    d.dimension(rail_cut((throat[0], -3.4)), rail_cut((throat[1], -3.4)), 549,
                number(mount["receiver_throat_width"]), label_at=(1215, 555))
    d.text(834, 553, "Lip throat", "small", "muted")
    d.leader(rail_cut((flange_x[1] - 0.35, -2.48)), (1285, 475), (1322, 475))
    d.text(1357, 464, "Depth gap", "small", "muted", "end")
    wall_y = rail_cut((0, model.bounds(CLEAT, 2)[0]))[1]
    d.line([(829, wall_y), (1364, wall_y)], "ink", 1.15)
    d.text(834, 694, "Wall datum", "small", "muted")

    d.rect(802, 737, 589, 155, "panel")
    d.text(826, 767, "NOMINAL RAIL ENGAGEMENT", "ref")
    for x, y, key, note in [
        (826, 805, "capture_per_side", "Lip capture per side"),
        (826, 855, "flange_side_clearance_per_side", "Side clearance per side"),
        (1100, 805, "flange_to_lip_depth_clearance", "Flange-to-lip depth gap"),
        (1100, 855, "upward_slide_to_clear_flange", "Upward travel to clear flange"),
    ]:
        d.text(x, y, number(mount[key]) + " mm", "dim", "oxide")
        d.text(x, y + 19, note, "small", "muted")
    d.footer("Source  cirrus.blend   /   Travel measured from rigid rail overlap after latch release")
    return d.finish()



def handoff_notes(data):
    envelope, vent, seal, mount = (data[key] for key in ("envelope", "vent_and_feedthrough", "seal", "mount"))
    lengths = vent["slot_lengths_left_to_right"]
    rows = [
        ("Body envelope", f'{number(envelope["width"])} × {number(envelope["height"])} × '
         f'{number(envelope["body_depth"])} mm', "Cover width × height × rear floor-to-face depth."),
        ("Mounted projection", f'{number(envelope["wall_to_face"])} mm',
         f'Cleat back to molded face. The rear floor datum sits {number(envelope["wall_datum_to_rear_floor"])} mm forward of the cleat back.'),
        ("Grille openings", f'{vent["slot_count"]} × {number(vent["slot_width"])} mm wide',
         f'{number(min(lengths))}–{number(max(lengths))} mm long. The individual lengths are in the measurement file.'),
        ("Vent isolation offsets", f'{number(vent["bulkhead_to_cover_window"])} / '
         f'{number(vent["bulkhead_to_lowest_grille_opening"])} mm',
         "Vertical distance from the upper bulkhead to the lower edge of the cover window / nearest slot tip."),
        ("Debris screen stand-off", f'{number(vent["grille_to_screen_wire"])} mm',
         "From the rear of the grille to the forwardmost evaluated wire. The screen frame is excluded."),
        ("Feedthrough", f'{number(vent["feedthrough_slit_height"])} / '
         f'{number(vent["flex_height_at_feedthrough"])} mm',
         "Silicone slit height / modeled flex height at the feedthrough center. The profile leaves a nominal opening around the flex."),
        ("Gasket stack", f'{number(seal["free_height"])} / {number(seal["seat_to_land"])} mm',
         "Free gasket height / bulkhead seat-to-land distance. Both are measured along the enclosure depth axis."),
        ("Nominal axial squeeze", f'{number(seal["rigid_overlap"])} mm · '
         f'{number(seal["nominal_squeeze_percent"])}%',
         "Free height minus seat-to-land distance, divided by free height for the percentage. Section D hatches the actual rigid mesh overlap."),
        ("Gasket rail channel", f'{number(seal["rail_channel_width_at_upper_straight"])} mm',
         "Nominal gap between the inner and outer rails at the upper straight, measured through the rail height."),
        ("Cleat anchors", f'{mount["anchor_count"]} slots · {number(mount["anchor_width"])} × '
         f'{number(mount["anchor_height"])} mm',
         f'Slot width × height on {number(mount["anchor_pitch_x"])} × {number(mount["anchor_pitch_y"])} mm center pitch.'),
        ("Sliding rails", f'{number(mount["rail_pitch_x"])} mm pitch',
         f'{number(mount["flange_width"])} mm flange across a {number(mount["receiver_throat_width"])} mm throat, '
         f'for {number(mount["capture_per_side"])} mm lip capture per side.'),
        ("Rail clearances", f'{number(mount["flange_side_clearance_per_side"])} / '
         f'{number(mount["flange_to_lip_depth_clearance"])} mm',
         "Lateral flange-to-receiver clearance per side / axial flange-to-lip gap."),
        ("Removal travel", f'{number(mount["upward_slide_to_clear_flange"])} mm',
         "Upward shift from the assembled position until the receiver lips clear the fixed flanges, assuming the latch has already been released. Installation overhead needs its own allowance."),
    ]
    lines = [
        "# Cirrus C-01 enclosure handoff",
        "",
        "Nominal dimensions from the assembled cirrus.blend in assembly-local coordinates. "
        "X is width, Y is vertical and Z points out from the wall. The rear surface of the cleat defines the wall datum.",
        "",
        "[Section A–A and seal detail](../renders/section.svg) · "
        "[Cleat elevation and rail section](../renders/mounting.svg) · [Measurement data](measurements.json)",
        "",
        "| Feature | Model value | Datum or interpretation |",
        "| --- | ---: | --- |",
        *[f"| {label} | {value} | {datum} |" for label, value, datum in rows],
        "",
        "## Measurement basis",
        "",
        "Nominal dimensions use the underlying part meshes and Boolean openings. The sheets trace evaluated mesh sections, including bevels, and the screen and flex measurements use evaluated geometry. "
        "The section exporter uses a 0.001 mm numerical offset to avoid vertices that lie directly on the cut plane. "
        "Normal rays check all grille slots through the grille and cover window, and all four anchor slots through the cleat. "
        "The rail travel uses the flange upper end and the receiver lip lower end, measured in the assembled position.",
        "",
        "## Study limits",
        "",
        "Cirrus is an independent digital design study. The vent offsets describe spatial separation. "
        "The gasket calculation uses undeformed geometry, and the feedthrough fit leaves a modeled gap. "
        "Ingress protection, airflow, thermal and sensor response, gasket force and deformation, production tolerances, "
        "wall fastener selection and loading, latch actuation, and tool or hand access require separate validation.",
        "",
        "See the [project README](../README.md#reproduce-and-verify) for rebuild and verification commands.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare the saved handoff to a fresh extraction.")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    model = Model()
    data = measurements(model)
    outputs = {
        "renders/section.svg": section_sheet(model, data),
        "renders/mounting.svg": mounting_sheet(model, data),
        "handoff/measurements.json": json.dumps(data, indent=2) + "\n",
        "handoff/README.md": handoff_notes(data),
    }
    stale = []
    for name, contents in outputs.items():
        path = ROOT / name
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != contents:
                stale.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8", newline="\n")
    require(not stale, "Missing or stale handoff files: " + ", ".join(stale))
    status = "Verified" if args.check else "Generated"
    print(f"{status} {len(outputs)} handoff files from {Path(bpy.data.filepath).name}; "
          "checked 13 grille slots and 4 wall-anchor slots.")


if __name__ == "__main__":
    main()
