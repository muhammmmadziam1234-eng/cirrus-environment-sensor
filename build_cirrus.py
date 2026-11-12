"""Build the Cirrus concept with Blender 4.5.4 and the built-in Python API."""

import argparse
import math
from pathlib import Path
import sys

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


OUT = Path(__file__).resolve().parent

# Blender units are centimetres. Parts are drawn in the mounting plane (XY);
# local +Z points out of the wall. The assembly root turns this upright.
WIDTH = 10.40
HEIGHT = 10.90
CORNER = 1.05
WALL = 0.31
FRONT = 3.36
SCREWS = tuple((x, y) for y in (-3.72, 3.72) for x in (-4.58, 4.58))
SEAL_W, SEAL_H, SEAL_Y = 8.18, 7.00, -1.39
VENT_Y = 3.60
VENTS = tuple(
    (x, VENT_Y, length)
    for x, length in zip(
        (-3.12, -2.60, -2.08, -1.56, -1.04, -0.52, 0.0,
         0.52, 1.04, 1.56, 2.08, 2.60, 3.12),
        (0.98, 1.14, 1.30, 1.40, 1.40, 1.40, 1.40,
         1.40, 1.40, 1.40, 1.30, 1.14, 0.98),
    )
)
MOUNT_HOLES = tuple((x, y) for x in (-2.00, 2.00) for y in (-3.08, 3.08))
BOARD_HOLES = tuple((x, y) for x in (-3.08, 3.08) for y in (-3.56, 1.04))
STATUS_X, STATUS_Y = 2.76, -2.50

scene = bpy.context.scene
for original in tuple(bpy.data.objects):
    bpy.data.objects.remove(original, do_unlink=True)
for original in tuple(bpy.data.collections):
    bpy.data.collections.remove(original)


def collection(name, parent=None):
    new = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(new)
    return new


product = collection("CIRRUS · assembly")
hardware = collection("01 · Wall cleat", product)
rear = collection("02 · Rear housing", product)
electronics = collection("03 · Electronics", product)
seal = collection("04 · Compression seal", product)
front = collection("05 · Face and captive fasteners", product)
studio = collection("Studio · cameras and lights")
temporary = collection("Temporary tooling")


def empty(name, owner, parent=None):
    obj = bpy.data.objects.new(name, None)
    owner.objects.link(obj)
    obj.parent = parent
    obj.empty_display_type = 'PLAIN_AXES'
    obj.empty_display_size = 0.48
    return obj


root = empty("Cirrus | Explode control", product)
root.rotation_euler.x = math.pi / 2
root.location.z = 5.54
root["Explode"] = 0.0
root.id_properties_ui("Explode").update(
    min=0.0, max=1.0, soft_min=0.0, soft_max=1.0,
    description="0 = assembled, 1 = exploded along the housing service axis",
)

layers = {}
for group, offset in ((hardware, -14.0), (rear, -5.6), (electronics, 2.65),
                      (seal, 9.25), (front, 16.5)):
    carrier = empty(group.name + " | travel", group, root)
    carrier.empty_display_size = 0.18
    driver = carrier.driver_add("location", 2).driver
    variable = driver.variables.new()
    variable.name = "spread"
    variable.type = 'SINGLE_PROP'
    variable.targets[0].id = root
    variable.targets[0].data_path = '["Explode"]'
    driver.expression = f"{offset} * spread"
    layers[group] = (carrier, offset)


def surface(name, rgb, roughness, metallic=0.0, texture=None):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgb, 1.0)
    mat.use_nodes = True
    tree = mat.node_tree
    shader = tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*rgb, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    if texture:
        noise = tree.nodes.new("ShaderNodeTexNoise")
        noise.label = "Fine surface grain"
        noise.inputs["Scale"].default_value = texture[0]
        noise.inputs["Detail"].default_value = 2.0
        coords = tree.nodes.new("ShaderNodeTexCoord")
        tree.links.new(coords.outputs["Object"], noise.inputs["Vector"])
        bump = tree.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = texture[1]
        bump.inputs["Distance"].default_value = texture[2]
        tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        tree.links.new(bump.outputs["Normal"], shader.inputs["Normal"])
        ramp = tree.nodes.new("ShaderNodeMapRange")
        ramp.inputs["To Min"].default_value = roughness - 0.045
        ramp.inputs["To Max"].default_value = roughness + 0.045
        tree.links.new(noise.outputs["Fac"], ramp.inputs["Value"])
        tree.links.new(ramp.outputs["Result"], shader.inputs["Roughness"])
    return mat


graphite = surface("Graphite · fine-texture enclosure", (0.034, 0.044, 0.052),
                   0.43, 0.09, (102, 0.20, 0.0032))
rear_graphite = surface("Graphite · molded rear", (0.025, 0.032, 0.038),
                        0.50, 0.04, (93, 0.18, 0.0035))
oxide = surface("Red oxide · anodized vent cassette", (0.265, 0.070, 0.040),
                0.37, 0.54, (121, 0.15, 0.0028))
cleat_finish = surface("Slate · coated wall cleat", (0.080, 0.107, 0.116),
                       0.45, 0.58, (112, 0.12, 0.0025))
rubber = surface("Black · molded seals", (0.013, 0.021, 0.022), 0.68)
seal_blue = surface("Slate green · compression gasket", (0.083, 0.175, 0.159), 0.62)
steel = surface("Smoke · passivated steel", (0.31, 0.35, 0.38), 0.34, 0.84)
brass = surface("Brass · threaded inserts", (0.49, 0.27, 0.086), 0.34, 0.75)
mask = surface("Deep jade · solder mask", (0.024, 0.110, 0.084), 0.48, 0.20)
trace_mask = surface("Copper under mask · routing", (0.048, 0.175, 0.125), 0.45, 0.28)
copper = surface("Gold · PCB finish", (0.54, 0.34, 0.105), 0.36, 0.78)
ceramic = surface("Tan · chip dielectric", (0.34, 0.240, 0.150), 0.56)
plastic = surface("Black · IC encapsulant", (0.019, 0.021, 0.022), 0.49)
silkscreen = surface("Mist · PCB legend", (0.50, 0.60, 0.53), 0.65)
mark = surface("Fog · front legend", (0.62, 0.66, 0.64), 0.49, 0.21)
fine_mark = surface("Muted mist · secondary legend", (0.31, 0.37, 0.38), 0.50, 0.16)
flex_finish = surface("Amber · polyimide", (0.39, 0.168, 0.038), 0.42, 0.18)
lightpipe = surface("Green · status light guide", (0.085, 0.34, 0.24), 0.30, 0.15)
light_shader = lightpipe.node_tree.nodes.get("Principled BSDF")
light_shader.inputs["Emission Color"].default_value = (0.086, 0.55, 0.34, 1)
light_shader.inputs["Emission Strength"].default_value = 0.30
floor_finish = surface("Studio · mineral gray", (0.104, 0.145, 0.157), 0.61)


def rounded(w, h, radius, x=0.0, y=0.0, steps=20):
    """Return a counterclockwise rounded rectangle, with explicit arc vertices."""
    points = []
    corners = ((1, 1), (-1, 1), (-1, -1), (1, -1))
    for quadrant, (sx, sy) in enumerate(corners):
        cx, cy = x + sx * (w / 2 - radius), y + sy * (h / 2 - radius)
        for step in range(steps + 1):
            a = (quadrant + step / steps) * math.pi / 2
            point = (cx + radius * math.cos(a), cy + radius * math.sin(a))
            if not points or math.dist(point, points[-1]) > 1e-7:
                points.append(point)
    if math.dist(points[0], points[-1]) < 1e-7:
        points.pop()
    return points


def circle(radius, x, y, sides=40):
    return [(x + radius * math.cos(i * math.tau / sides),
             y + radius * math.sin(i * math.tau / sides)) for i in range(sides)]


def mesh(name, vertices, faces, owner, mat=None):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    owner.objects.link(obj)
    if owner in layers:
        obj.parent = layers[owner][0]
    if mat:
        data.materials.append(mat)
    return obj


def solid(name, outline, low, high, owner, mat=None):
    n = len(outline)
    vertices = [(x, y, z) for z in (low, high) for x, y in outline]
    faces = [tuple(reversed(range(n))), tuple(range(n, n * 2))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    return mesh(name, vertices, faces, owner, mat)


def loop(name, outer, inner, low, high, owner, mat):
    n = len(outer)
    assert n == len(inner)
    vertices = [(x, y, z) for z in (low, high) for profile in (outer, inner)
                for x, y in profile]
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.extend(((i, j, j + 2*n, i + 2*n),
                      (i + n, i + 3*n, j + 3*n, j + n),
                      (i + 2*n, j + 2*n, j + 3*n, i + 3*n),
                      (i, i + n, j + n, j)))
    return mesh(name, vertices, faces, owner, mat)


def edge(obj, width, segments=5):
    if width:
        # Shade the curved wall continuously while preserving planar caps.
        for polygon in obj.data.polygons:
            polygon.use_smooth = abs(polygon.normal.z) < 0.999
        bevel = obj.modifiers.new("Machined edge radius", 'BEVEL')
        bevel.width = width
        bevel.segments = segments
        bevel.limit_method = 'ANGLE'
        bevel.angle_limit = math.radians(28)
        bevel.harden_normals = True
        normals = obj.modifiers.new("Weighted surface normals", 'WEIGHTED_NORMAL')
        normals.keep_sharp = True
    return obj


def panel(name, w, h, r, low, high, owner, mat=None, x=0, y=0, bevel=0):
    return edge(solid(name, rounded(w, h, r, x, y), low, high, owner, mat), bevel)


def box(name, w, h, low, high, owner, mat=None, x=0, y=0, bevel=0):
    outline = [(x-w/2, y-h/2), (x+w/2, y-h/2),
               (x+w/2, y+h/2), (x-w/2, y+h/2)]
    return edge(solid(name, outline, low, high, owner, mat), bevel)


def disc(name, radius, low, high, owner, mat=None, x=0, y=0, bevel=0):
    return edge(solid(name, circle(radius, x, y), low, high, owner, mat), bevel)


def washer(name, outside, inside, low, high, owner, mat, x, y, bevel=0):
    return edge(loop(name, circle(outside, x, y), circle(inside, x, y),
                     low, high, owner, mat), bevel)


def rim(name, w, h, r, wall, low, high, owner, mat, x=0, y=0, bevel=0):
    return edge(loop(name, rounded(w, h, r, x, y),
                     rounded(w-2*wall, h-2*wall, r-wall, x, y),
                     low, high, owner, mat), bevel)


def subtract(obj, cutters, name):
    """Apply a real bore while leaving the part's finishing modifiers editable."""
    if len(cutters) > 1:
        vertices, faces = [], []
        for cutter in cutters:
            offset = len(vertices)
            vertices.extend(tuple(v.co) for v in cutter.data.vertices)
            faces.extend(tuple(offset + i for i in p.vertices)
                         for p in cutter.data.polygons)
            bpy.data.objects.remove(cutter, do_unlink=True)
        die = mesh(name + " · tool", vertices, faces, temporary)
    else:
        die = cutters[0]
    die.parent = obj.parent
    bpy.context.view_layer.update()
    mod = obj.modifiers.new(name, 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = 'EXACT'
    mod.object = die
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(die, do_unlink=True)


def label(name, text, size, x, y, z, owner, mat, tracking=1.12):
    curve = bpy.data.curves.new(name, 'FONT')
    curve.body = text
    curve.size = size
    curve.space_character = tracking
    curve.resolution_u = 8
    obj = bpy.data.objects.new(name, curve)
    owner.objects.link(obj)
    obj.parent = layers[owner][0]
    obj.location = (x, y, z)
    curve.materials.append(mat)
    return obj


def line(name, points, radius, owner, mat):
    data = bpy.data.curves.new(name, 'CURVE')
    data.dimensions = '3D'
    data.resolution_u = 1
    data.bevel_resolution = 1
    data.bevel_depth = radius
    spline = data.splines.new('POLY')
    spline.points.add(len(points) - 1)
    for point, (x, y, z) in zip(spline.points, points):
        point.co = (x, y, z, 1.0)
    obj = bpy.data.objects.new(name, data)
    owner.objects.link(obj)
    obj.parent = layers[owner][0]
    data.materials.append(mat)
    return obj


def capsule(name, w, h, low, high, owner, mat=None, x=0, y=0, bevel=0):
    return panel(name, w, h, min(w, h)/2, low, high, owner, mat, x, y, bevel)


# The wall cleat slides in from the open end of the two rear receivers.
plate = panel("Wall cleat | formed plate", 8.56, 8.56, 0.77, -0.77, -0.46,
              hardware, cleat_finish)
subtract(plate, [capsule("Wall anchor die", 0.47, 0.93, -0.92, -0.31,
                         temporary, x=x, y=y) for x, y in MOUNT_HOLES],
         "Four slotted wall anchors")
edge(plate, 0.072)
for x in (-2.93, 2.93):
    box("Cleat rail | stem", 0.34, 5.12, -0.47, -0.21, hardware, cleat_finish,
        x=x, y=-0.27, bevel=0.025)
    box("Cleat rail | captured flange", 0.72, 5.08, -0.24, -0.10,
        hardware, cleat_finish, x=x, y=-0.27, bevel=0.033)
    for sign in (-1, 1):
        box("Rear receiver | wall", 0.20, 5.43, -0.325, 0.055,
            rear, rear_graphite, x=x+sign*0.49, y=-0.24, bevel=0.025)
        box("Rear receiver | undercut lip", 0.32, 5.43, -0.34, -0.255,
            rear, rear_graphite, x=x+sign*0.45, y=-0.24, bevel=0.015)
for x in (-2.93, 2.93):
    box("Cleat | lower travel stop", 1.18, 0.24, -0.46, -0.09, hardware,
        cleat_finish, x=x, y=-3.10, bevel=0.043)
box("Rear | spring latch keeper", 0.72, 0.11, -0.21, 0.036,
    rear, rear_graphite, y=-2.99, bevel=0.017)
box("Cleat | spring latch", 0.63, 1.25, -0.47, -0.29, hardware,
    steel, y=-3.54, bevel=0.034)
box("Cleat | latch tooth", 0.36, 0.22, -0.29, -0.045, hardware,
    steel, y=-3.17, bevel=0.025)
for x in (-0.30, 0.30):
    line("Cleat | orientation chevron", [(0, 3.61, -0.45), (x, 3.22, -0.45)],
         0.025, hardware, fine_mark)
label("Cleat orientation", "UP", 0.26, -0.19, 2.84, -0.451, hardware, fine_mark)

# The floor and outer skirt remain separate editable molded features.
base = panel("Rear | molded floor", WIDTH-0.14, HEIGHT-0.14, CORNER-0.07,
             0.0, 0.44, rear, rear_graphite, bevel=0.105)
rim("Rear | perimeter wall", WIDTH-0.14, HEIGHT-0.14, CORNER-0.07, WALL,
    0.35, 1.24, rear, rear_graphite, bevel=0.048)
seal_wall = rim("Rear | closed electronics bulkhead", SEAL_W, SEAL_H, 0.69,
                0.44, 0.40, 1.125, rear, rear_graphite, y=SEAL_Y)
subtract(seal_wall, [box("Feedthrough die", 1.11, 0.76, 0.55, 0.90,
                          temporary, y=1.88)], "Potted cable feedthrough")
edge(seal_wall, 0.025)
rim("Rear | outer gasket rail", SEAL_W, SEAL_H, 0.69, 0.089,
    1.11, 1.228, rear, rear_graphite, y=SEAL_Y, bevel=0.017)
rim("Rear | inner gasket rail", SEAL_W-0.65, SEAL_H-0.65, 0.365, 0.112,
    1.11, 1.228, rear, rear_graphite, y=SEAL_Y, bevel=0.017)
grommet = box("Rear | silicone feedthrough", 1.105, 0.55, 0.553, 0.897,
              rear, rubber, y=1.91)
subtract(grommet, [box("Flex slot die", 0.63, 0.80, 0.707, 0.764,
                        temporary, y=1.91)], "Ribbon passage")
edge(grommet, 0.018)
gasket = rim("Seal | continuous molded silicone", SEAL_W-0.20, SEAL_H-0.20,
             0.59, 0.217, 1.125, 1.375, seal, seal_blue, y=SEAL_Y, bevel=0.064)

for i, (x, y) in enumerate(SCREWS, 1):
    washer(f"Rear | molded insert tower {i}", 0.373, 0.251, 0.40, 1.242,
           rear, rear_graphite, x, y, bevel=0.032)
    washer(f"Rear | brass insert {i}", 0.250, 0.150, 0.565, 1.251,
           rear, brass, x, y, bevel=0.019)
    for height in (0.71, 0.86, 1.01, 1.16):
        washer(f"Rear | insert thread crest {i}", 0.151, 0.143, height-0.018,
               height+0.018, rear, brass, x, y)

for i, (x, y) in enumerate(BOARD_HOLES, 1):
    washer(f"Rear | PCB standoff {i}", 0.267, 0.097, 0.416, 0.908,
           rear, rear_graphite, x, y, bevel=0.027)
for x in (-1.62, 1.62):
    for y in (3.11, 4.07):
        disc("Rear | sensing board support", 0.208, 0.42, 0.908,
             rear, rear_graphite, x, y, bevel=0.027)

# Both boards and their hardware remain individually editable.
pcb = panel("PCB | main FR-4", 7.12, 5.80, 0.32, 0.908, 1.075,
            electronics, mask, y=-1.25)
subtract(pcb, [disc("PCB drill", 0.125, 0.82, 1.17, temporary, x=x, y=y)
               for x, y in BOARD_HOLES], "Four plated clearance holes")
edge(pcb, 0.029)
for i, (x, y) in enumerate(BOARD_HOLES, 1):
    washer(f"PCB | plated mounting land {i}", 0.228, 0.125, 1.071, 1.083,
           electronics, copper, x, y)
    disc(f"PCB | mounting screw stem {i}", 0.089, 0.76, 1.115,
         electronics, steel, x, y)
    cap = disc(f"PCB | mounting screw head {i}", 0.173, 1.08, 1.17,
               electronics, steel, x, y)
    subtract(cap, [box("Screw recess die", 0.209, 0.037, 1.132, 1.23,
                       temporary, x=x, y=y)], "Drive slot")
    edge(cap, 0.016)

sensor = panel("PCB | exposed sensor daughterboard", 4.13, 1.72, 0.24,
               0.908, 1.064, electronics, mask, y=3.59, bevel=0.031)
for x in (-1.62, 1.62):
    for y in (3.11, 4.07):
        disc("Sensor board | fastener", 0.139, 1.064, 1.16,
             electronics, steel, x, y, bevel=0.022)
        box("Sensor board | recessed drive", 0.14, 0.028, 1.159, 1.162,
            electronics, plastic, x=x, y=y, bevel=0.007)
package = panel("Sensing element | metal package", 0.92, 0.73, 0.10,
                1.065, 1.357, electronics, steel, y=3.69)
subtract(package, [disc("Sensing aperture die", 0.116, 1.19, 1.43,
                         temporary, x=0.13, y=3.70)], "Sensing inlet")
edge(package, 0.027)
for x in (-0.68, -0.89, 0.71, 0.93):
    box("Sensor board | passive termination", 0.158, 0.23, 1.066, 1.131,
        electronics, steel, x=x, y=3.65, bevel=0.017)
    box("Sensor board | passive body", 0.122, 0.105, 1.107, 1.155,
        electronics, ceramic, x=x, y=3.65, bevel=0.012)
label("Sensor board | silkscreen", "SENSE  /  J2", 0.16, -0.63, 4.10,
      1.070, electronics, silkscreen)

for name, y, z in (("Main PCB | underside FPC connector", 1.41, 0.742),
                   ("Sensor PCB | FPC connector", 2.88, 1.064)):
    box(name, 0.83, 0.33, z, z+0.14, electronics, plastic, y=y, bevel=0.029)
    box(name + " latch", 0.72, 0.112, z+0.13, z+0.174,
        electronics, flex_finish, y=y+0.055, bevel=0.012)

flex_route = ((1.41, 0.735), (1.58, 0.735), (1.70, 0.735), (2.20, 0.735),
              (2.57, 0.735), (2.74, 1.17), (2.92, 1.19))
flex_vertices = [(x, y, z) for y, z in flex_route for x in (-0.292, 0.292)]
flex_faces = [(2*i, 2*i+1, 2*i+3, 2*i+2) for i in range(len(flex_route)-1)]
flex = mesh("Flex | removable sensor interconnect", flex_vertices, flex_faces,
            electronics, flex_finish)
flex.modifiers.new("Polyimide thickness", 'SOLIDIFY').thickness = 0.024
for x in (-0.20, -0.12, -0.04, 0.04, 0.12, 0.20):
    line("Flex | copper conductor", [(x, y, z+0.012) for y, z in flex_route],
         0.009, electronics, copper)

# Main board detail is deliberately legible from the exploded camera.
chip_x, chip_y = -0.56, -1.11
panel("PCB | main MCU package", 1.52, 1.52, 0.095, 1.101, 1.35,
      electronics, plastic, x=chip_x, y=chip_y, bevel=0.045)
disc("PCB | pin-one dimple", 0.073, 1.349, 1.353, electronics,
     fine_mark, chip_x-0.54, chip_y+0.54)
label("PCB | MCU laser legend", "U1", 0.24, chip_x-0.20, chip_y-0.09,
      1.354, electronics, fine_mark)
for side in (-1, 1):
    for k in range(8):
        step = (k-3.5)*0.152
        for swap in (False, True):
            x, y = (step, side*0.82) if swap else (side*0.82, step)
            w, h = (0.08, 0.32) if swap else (0.32, 0.08)
            box("PCB | MCU exposed lead", w, h, 1.075, 1.128,
                electronics, steel, x=chip_x+x, y=chip_y+y, bevel=0.015)
            dx, dy = (0.06*(k-3.5), side*(0.35+0.036*k)) if swap else (
                side*(0.35+0.036*k), 0.06*(k-3.5))
            a = (chip_x+x, chip_y+y, 1.080)
            b = (a[0]+dx*0.43, a[1]+dy*0.70, a[2])
            c = (a[0]+dx, a[1]+dy, a[2])
            line("PCB | masked fanout", [a, b, c], 0.018, electronics, trace_mask)
            disc("PCB | fanout via", 0.035, 1.076, 1.085, electronics,
                 copper, c[0], c[1])

panel("PCB | regulator", 0.93, 0.62, 0.085, 1.09, 1.308, electronics,
      plastic, x=1.66, y=0.35, bevel=0.026)
for x in (1.38, 1.65, 1.92):
    for y in (0.03, 0.67):
        box("PCB | regulator lead", 0.114, 0.26, 1.075, 1.128,
            electronics, steel, x=x, y=y, bevel=0.021)
panel("PCB | shielded inductor", 0.79, 0.75, 0.105, 1.074, 1.474,
      electronics, plastic, x=2.36, y=-0.72, bevel=0.075)
label("PCB | inductor mark", "4R7", 0.188, 2.15, -0.79,
      1.477, electronics, fine_mark)
panel("PCB | crystal can", 0.75, 0.49, 0.11, 1.075, 1.242,
      electronics, steel, x=-2.22, y=-0.61, bevel=0.031)
for x, y in ((-2.57, 0.19), (-2.23, 0.19), (-1.89, 0.19),
             (1.43, -0.70), (1.43, -1.04), (1.43, -1.38),
             (2.08, -1.49), (2.44, -1.49), (2.80, -1.49),
             (-2.42, -1.60), (-2.42, -1.94), (-2.42, -2.28),
             (-0.44, -2.49), (-0.08, -2.49), (0.28, -2.49)):
    box("PCB | passive terminations", 0.20, 0.28, 1.075, 1.155,
        electronics, steel, x=x, y=y, bevel=0.018)
    box("PCB | passive body", 0.195, 0.15, 1.115, 1.188,
        electronics, ceramic, x=x, y=y, bevel=0.016)
for i in range(7):
    x = -1.47 + 0.43*i
    disc("PCB | test land", 0.117, 1.071, 1.088, electronics, copper, x, -3.48)
    line("PCB | test land routing", [(x, -3.39, 1.079),
         (x, -3.12+0.033*i, 1.079), (x+0.20, -2.92+0.033*i, 1.079)],
         0.022, electronics, trace_mask)
box("PCB | status LED package", 0.47, 0.37, 1.075, 1.18,
    electronics, ceramic, x=STATUS_X, y=STATUS_Y, bevel=0.028)
box("PCB | green LED die", 0.30, 0.18, 1.18, 1.235,
    electronics, lightpipe, x=STATUS_X, y=STATUS_Y, bevel=0.033)
label("PCB | board identifier", "CIRRUS  /  C-01", 0.31, -2.62, 0.92,
      1.078, electronics, silkscreen)
label("PCB | test land identifier", "TP1–7", 0.19, -0.45, -3.87,
      1.078, electronics, silkscreen)
label("PCB | LED identifier", "D1", 0.19, 2.55, -2.94,
      1.078, electronics, silkscreen)

# The vented nose lies beyond the sealed volume. The insert's airflow holes and
# the shell window are open geometry, with an offset mesh screen behind.
rim("Cover | perimeter skirt", WIDTH, HEIGHT, CORNER, WALL,
    1.31, 3.08, front, graphite, bevel=0.080)
rim("Cover | gasket compression land", SEAL_W-0.025, SEAL_H-0.025,
    0.678, 0.435, 1.315, 3.03, front, graphite, y=SEAL_Y, bevel=0.024)
face = panel("Cover | molded face", WIDTH, HEIGHT, CORNER,
             2.95, FRONT, front, graphite)
subtract(face, [panel("Vent aperture die", 7.94, 2.40, 0.52,
                       2.82, 3.52, temporary, y=VENT_Y)], "Vent cassette opening")
subtract(face, [disc("Fastener bore die", 0.185, 2.82, 3.53,
                      temporary, x=x, y=y) for x, y in SCREWS], "Four shank bores")
subtract(face, [disc("Fastener counterbore die", 0.391, 3.145, 3.54,
                      temporary, x=x, y=y) for x, y in SCREWS], "Four recessed seats")
subtract(face, [capsule("Light guide die", 0.54, 0.219, 2.80, 3.52,
                         temporary, x=STATUS_X, y=STATUS_Y)], "Status window")
edge(face, 0.066, 6)

vent = panel("Vent cassette | red oxide grille", 7.83, 2.286, 0.47,
             2.968, 3.329, front, oxide, y=VENT_Y)
subtract(vent, [capsule("Vent slot die", 0.238, length, 2.84, 3.50, temporary,
                         x=x, y=y) for x, y, length in VENTS], "Thirteen airflow slots")
edge(vent, 0.034)
rim("Vent cassette | rear retention flange", 8.20, 2.61, 0.58, 0.26,
    2.84, 2.977, front, oxide, y=VENT_Y, bevel=0.029)
for y in (3.04, 3.26, 3.48, 3.70, 3.92, 4.14):
    line("Vent cassette | debris screen weft", [(-3.45, y, 2.72), (3.45, y, 2.72)],
         0.023, front, rear_graphite)
for i in range(39):
    x = -3.42 + i*0.18
    line("Vent cassette | debris screen warp", [(x, 2.83, 2.69), (x, 4.36, 2.69)],
         0.023, front, rear_graphite)
rim("Vent cassette | debris screen frame", 7.25, 1.73, 0.17, 0.12,
    2.65, 2.76, front, rear_graphite, y=VENT_Y, bevel=0.014)
for x in (-3.47, 3.47):
    box("Vent cassette | screen hanger", 0.28, 1.38, 2.65, 2.86, front,
        rear_graphite, x=x, y=VENT_Y, bevel=0.025)

for i, (x, y) in enumerate(SCREWS, 1):
    washer(f"Cover | captive screw sleeve {i}", 0.365, 0.189,
           2.48, 2.985, front, graphite, x, y, bevel=0.034)
    shank = disc(f"Cover | captive screw shank {i}", 0.116, 0.655, 3.192,
                 front, steel, x, y, bevel=0.021)
    threads = [(x+0.130*math.cos(t*math.tau/20), y+0.130*math.sin(t*math.tau/20),
                0.706+t*0.0027) for t in range(201)]
    line(f"Cover | rolled screw thread {i}", threads, 0.011, front, steel)
    washer(f"Cover | captured retaining ring {i}", 0.243, 0.111,
           2.397, 2.478, front, steel, x, y, bevel=0.018)
    head = disc(f"Cover | recessed six-lobe screw head {i}", 0.324, 3.15, 3.328,
                front, steel, x, y)
    torx = []
    for k in range(72):
        angle = k*math.tau/72
        radius = 0.134 + 0.030*math.cos(6*angle)
        torx.append((x+radius*math.cos(angle), y+radius*math.sin(angle)))
    subtract(head, [solid("Six-lobe drive die", torx, 3.247, 3.47, temporary)],
             "Six-lobe drive recess")
    edge(head, 0.024)

capsule("Status | front light guide", 0.506, 0.190, 1.283, 3.327, front,
        lightpipe, x=STATUS_X, y=STATUS_Y, bevel=0.023)
edge(loop("Status | light guide seat",
          rounded(0.67, 0.34, 0.17, STATUS_X, STATUS_Y),
          rounded(0.509, 0.193, 0.0965, STATUS_X, STATUS_Y),
          2.875, 2.958, front, rubber), 0.014)
label("CIRRUS | wordmark", "CIRRUS", 1.17, -3.68, 0.56, FRONT+0.005,
      front, mark, 1.21)
label("Face | function", "ENVIRONMENTAL SENSOR", 0.255, -3.61, 0.002, FRONT+0.005,
      front, fine_mark, 1.16)
label("Face | model identifier", "C-01", 0.31, -3.61, -2.62, FRONT+0.005,
      front, mark, 1.13)
label("Face | status identifier", "STATUS", 0.19, 2.36, -2.91, FRONT+0.005,
      front, fine_mark, 1.10)
box("Face | etched datum rule", 7.18, 0.018, FRONT+0.001, FRONT+0.007,
    front, fine_mark, y=-2.10, bevel=0.003)

bpy.data.collections.remove(temporary)



def area(name, xyz, target, power, color, size, size_y):
    lamp = bpy.data.lights.new(name, 'AREA')
    lamp.shape = 'RECTANGLE'
    lamp.energy = power
    lamp.color = color
    lamp.size = size
    lamp.size_y = size_y
    obj = bpy.data.objects.new(name, lamp)
    studio.objects.link(obj)
    obj.location = xyz
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()
    return obj


def camera(name, direction):
    data = bpy.data.cameras.new(name)
    data.type = 'ORTHO'
    data.sensor_fit = 'HORIZONTAL'
    data.clip_end = 240
    obj = bpy.data.objects.new(name, data)
    studio.objects.link(obj)
    obj.rotation_euler = (-Vector(direction)).to_track_quat('-Z', 'Y').to_euler()
    return obj


floor = box("Studio | seamless mineral sweep", 170, 170, -0.30, 0.0,
            studio, floor_finish)
area("Studio | warm overhead key", (-9, -12, 16), (0, -1.8, 4.8),
     2800, (1.00, 0.87, 0.75), 12, 10)
area("Studio | cool vertical fill", (11, -11, 9), (0, -2.2, 5.2),
     1680, (0.72, 0.87, 1.00), 8, 14)
area("Studio | rear shoulder strip", (5, 7, 14), (0, -0.3, 6.0),
     2480, (0.81, 0.93, 1.00), 11, 7)
area("Studio | face bounce card", (-2, -15, 8), (0, -1.5, 5.1),
     420, (0.88, 0.95, 1.00), 13, 7)
area("Studio | near end extension", (1, -26, 15), (0, -17, 5.2),
     1750, (1.00, 0.91, 0.83), 13, 12)
area("Studio | far end extension", (7, 18, 15), (0, 11, 5.2),
     2300, (0.85, 0.94, 1.00), 14, 10)
hero = camera("Camera · 01 Hero", (0.45, -0.84, 0.275))
exploded = camera("Camera · 02 Exploded", (0.83, -0.56, 0.39))

scene.unit_settings.system = 'METRIC'
scene.unit_settings.length_unit = 'MILLIMETERS'
scene.unit_settings.scale_length = 0.01
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 32
scene.cycles.use_adaptive_sampling = True
scene.cycles.adaptive_threshold = 0.038
scene.cycles.adaptive_min_samples = 8
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 5
scene.cycles.diffuse_bounces = 2
scene.cycles.glossy_bounces = 3
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.film_transparent = False
scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
scene.world.use_nodes = True
background = scene.world.node_tree.nodes.get("Background")
background.inputs["Color"].default_value = (0.24, 0.31, 0.39, 1.0)
background.inputs["Strength"].default_value = 0.28
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Medium High Contrast'
scene.view_settings.exposure = 0.34


def set_spread(value):
    root["Explode"] = value
    root.update_tag()
    scene.frame_set(scene.frame_current)
    bpy.context.view_layer.update()


def product_bounds():
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in product.all_objects:
        if obj.type in {'MESH', 'CURVE', 'FONT'}:
            item = obj.evaluated_get(depsgraph)
            points.extend(item.matrix_world @ Vector(p) for p in item.bound_box)
    return points


def set_format(width, height):
    scene.render.resolution_x = width
    scene.render.resolution_y = height


def compose(cam, width, height, fill, bias=(0.0, 0.0)):
    """Frame the evaluated assembly with consistent product margins."""
    set_format(width, height)
    points = product_bounds()
    rotation = cam.rotation_euler.to_matrix()
    in_camera = [rotation.transposed() @ point for point in points]
    low = Vector(tuple(min(point[i] for point in in_camera) for i in range(3)))
    high = Vector(tuple(max(point[i] for point in in_camera) for i in range(3)))
    span = high - low
    aspect = width / height
    cam.data.ortho_scale = max(span.x / fill[0], span.y * aspect / fill[1])
    center = (low + high) / 2
    center.x -= bias[0] * cam.data.ortho_scale
    center.y -= bias[1] * cam.data.ortho_scale / aspect
    center.z += 57
    cam.location = rotation @ center
    bpy.context.view_layer.update()
    for point in points:
        p = world_to_camera_view(scene, cam, point)
        assert 0.025 < p.x < 0.975 and 0.025 < p.y < 0.975 and p.z > 0, \
            f"Product geometry clipped in {cam.name}"


def ray_hit(obj, x, y):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    hit, *_ = evaluated.ray_cast(Vector((x, y, 7)), Vector((0, 0, -1)))
    return hit


def z_extent(obj):
    return tuple(f((vertex.co.z for vertex in obj.data.vertices)) for f in (min, max))


def closed(obj):
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        assert bm.faces and all(edge.is_manifold for edge in bm.edges), \
            f"{obj.name} has an open or nonmanifold mesh"
        assert abs(bm.calc_volume()) > 0.01, f"{obj.name} has no usable volume"
    finally:
        bm.free()


def validate():
    """Check source geometry and live relationships before saving or rendering."""
    set_spread(0)
    assert len(electronics.objects) > 100 and len(front.objects) > 65
    for item in (plate, base, seal_wall, grommet, gasket, pcb, sensor, face, vent):
        closed(item)
    for x, y, _ in VENTS:
        assert not ray_hit(vent, x, y), "An airflow slot is blocked by the grille"
    assert ray_hit(vent, 0.26, VENT_Y), "The vent web is absent"
    assert not ray_hit(face, 0, VENT_Y), "The grille has no opening through the face"
    assert not ray_hit(face, STATUS_X, STATUS_Y), "The light guide bore is blocked"
    assert ray_hit(face, 0, -1), "The main face is missing"
    for x, y in MOUNT_HOLES:
        assert not ray_hit(plate, x, y), "A wall anchor slot is blocked"
    for i, (x, y) in enumerate(SCREWS, 1):
        assert not ray_hit(face, x, y), "A captive screw bore is blocked"
        head = bpy.data.objects[f"Cover | recessed six-lobe screw head {i}"]
        ring = bpy.data.objects[f"Cover | captured retaining ring {i}"]
        shank = bpy.data.objects[f"Cover | captive screw shank {i}"]
        insert = bpy.data.objects[f"Rear | brass insert {i}"]
        closed(head)
        assert z_extent(head)[1] < FRONT
        assert z_extent(insert)[0] < z_extent(shank)[0] < z_extent(insert)[1]
        assert ring.parent == head.parent == shank.parent == layers[front][0]
        head_rim = max(math.hypot(v.co.x-x, v.co.y-y) for v in head.data.vertices)
        retainer_od = max(math.hypot(v.co.x-x, v.co.y-y) for v in ring.data.vertices)
        assert head_rim > retainer_od > 0.189, "Fastener retention is undersized"
    for i, (x, y) in enumerate(BOARD_HOLES, 1):
        assert not ray_hit(pcb, x, y), "A PCB drill is blocked"
        post = bpy.data.objects[f"Rear | PCB standoff {i}"]
        assert abs(z_extent(post)[1]-z_extent(pcb)[0]) < 0.002
    land = bpy.data.objects["Cover | gasket compression land"]
    assert z_extent(gasket)[0] < z_extent(land)[0] < z_extent(gasket)[1]
    assert 0.65 < (z_extent(land)[0]-z_extent(gasket)[0]) / (
        z_extent(gasket)[1]-z_extent(gasket)[0]) < 0.84
    for group, (carrier, _) in layers.items():
        assert abs(carrier.location.z) < 1e-5
        assert all(obj == carrier or obj.parent == carrier for obj in group.objects)
    sealed_top = SEAL_Y + SEAL_H/2
    assert VENT_Y - max(length for _, _, length in VENTS)/2 > sealed_top
    assert VENT_Y - 1.20 > sealed_top
    assert 0.34 < 2*(0.45-0.32/2) < 0.72  # Rail stem, lip opening, and flange widths.
    for spread in (0.5, 1):
        set_spread(spread)
        for carrier, offset in layers.values():
            assert abs(carrier.location.z - offset*spread) < 1e-4
    set_spread(0)
    print(f"Cirrus geometry validated: {len(product.all_objects)} assembly objects, "
          "13 open vents, aligned fasteners, PCB and wall anchor bores, "
          "gasket compression and five driven layers.", flush=True)


def render(cam, spread, width, height, path):
    set_spread(spread)
    scene.camera = cam
    set_format(width, height)
    scene.render.filepath = str(path)
    print(f"Rendering {path.name} ({width} × {height})", flush=True)
    bpy.ops.render.render(write_still=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--build-only", action="store_true", help="Validate and save without rendering")
    modes.add_argument("--preview", action="store_true", help="Render small proofs under preview/")
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    validate()
    set_spread(1)
    compose(exploded, 1400, 890, (0.90, 0.81))
    set_spread(0)
    compose(hero, 1320, 1320, (0.76, 0.76), bias=(-0.02, 0.018))
    scene.camera = hero
    scene.render.resolution_percentage = 100
    scene.render.filepath = "//renders/hero.png"

    for obj in studio.objects:
        obj.hide_set(obj.type != 'CAMERA')
    bpy.context.view_layer.objects.active = root
    root.select_set(True)
    for screen in bpy.data.screens:
        for area_item in screen.areas:
            if area_item.type == 'VIEW_3D':
                view = area_item.spaces.active
                view.clip_end = 240
                view.shading.color_type = 'MATERIAL'
                view.overlay.show_floor = False
                view.overlay.show_axis_x = False
                view.overlay.show_axis_y = False
                view.region_3d.view_location = (0, -1.40, 5.55)
                view.region_3d.view_rotation = hero.rotation_euler.to_quaternion()
                view.region_3d.view_distance = 19.0
    scene["Product"] = "Cirrus C-01 | industrial environmental sensor concept"
    scene["Render sizes"] = "Hero 1320 x 1320. Exploded 1400 x 890."
    scene["Assembly axis"] = "Local +Z at the Cirrus | Explode control."
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "cirrus.blend"))
    print("Saved editable cirrus.blend", flush=True)

    if args.build_only:
        return
    output_dir = OUT / ("preview" if args.preview else "renders")
    output_dir.mkdir(exist_ok=True)
    if args.preview:
        scene.cycles.samples = 14
        scene.cycles.adaptive_min_samples = 6
        scene.render.resolution_percentage = 44
    render(hero, 0, 1320, 1320, output_dir / "hero.png")
    render(exploded, 1, 1400, 890, output_dir / "exploded.png")
    set_spread(0)
    scene.camera = hero


if __name__ == "__main__":
    main()
