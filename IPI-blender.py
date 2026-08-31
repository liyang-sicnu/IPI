import math
import random
import shutil
from pathlib import Path

import bpy
from mathutils import Vector


OUT_DIR = Path("/Users/leonsky/Downloads/AI设计图/modeling_output")
STL_SOURCE_CANDIDATES = [
    Path("/Users/leonsky/Downloads/IPI高度16mm厚度2mm.stl"),
    Path("/Users/leonsky/Downloads/AI设计图/实物拍摄图/IPI高度16mm厚度2mm.stl"),
]
CUSTOM_HEX_STL_CANDIDATES = [
    Path("/Users/leonsky/Downloads/AI设计图/实物拍摄图/定制六边形亚克力装置.stl"),
]
STL_PATH = OUT_DIR / "ipi_rack_source_ascii.stl"
BLEND_PATH = OUT_DIR / "ipi_device_v1_17.blend"
PREVIEW_PATH = OUT_DIR / "previews" / "ipi_device_v1_17_preview.png"


COLLECTIONS = {}
RACK_EXTERIOR_CLEARANCE = 1.75
RACK_SLOT_EXIT_LOCAL_X = 9.7
RACK_EXTERNAL_TUBE_LOCAL_X = 20.5
SLOT_ARC_SAMPLES = 42
SHARED_FLUIDIC_TUBE_RADIUS = 0.55
UPRIGHT_PACK_TUBE_RADIUS = 0.45


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for coll in list(bpy.data.collections):
        if coll.users == 0:
            bpy.data.collections.remove(coll)


def cleanup_empty_collections():
    removed = True
    while removed:
        removed = False
        for coll in list(bpy.data.collections):
            if not coll.objects and not coll.children:
                for parent in bpy.data.collections:
                    if coll.name in parent.children:
                        parent.children.unlink(coll)
                if coll.name in bpy.context.scene.collection.children:
                    bpy.context.scene.collection.children.unlink(coll)
                bpy.data.collections.remove(coll)
                removed = True


def get_collection(path):
    parent = bpy.context.scene.collection
    current_path = []
    for part in path.split("/"):
        current_path.append(part)
        key = "/".join(current_path)
        if key not in COLLECTIONS:
            coll = bpy.data.collections.new(part)
            parent.children.link(coll)
            COLLECTIONS[key] = coll
        parent = COLLECTIONS[key]
    return parent


def move_to_collection(obj, coll):
    if coll.name not in [c.name for c in obj.users_collection]:
        coll.objects.link(obj)
    for user_coll in list(obj.users_collection):
        if user_coll != coll:
            user_coll.objects.unlink(obj)
    return obj


def make_mat(name, color, alpha=1.0, roughness=0.55, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = color
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
    mat.blend_method = "BLEND" if alpha < 0.99 else "OPAQUE"
    mat.use_screen_refraction = alpha < 0.99
    mat.show_transparent_back = alpha >= 0.99
    return mat


def add_box(name, loc, dims, mat=None, rot_z=0.0, bevel=0.0, coll=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=(0, 0, rot_z))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat:
        obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("softened_edges", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        obj.modifiers.new("weighted_normals", "WEIGHTED_NORMAL")
    if coll:
        move_to_collection(obj, coll)
    return obj


def add_cylinder_between(name, p1, p2, radius, mat=None, vertices=32, coll=None):
    p1 = Vector(p1)
    p2 = Vector(p2)
    mid = (p1 + p2) / 2
    direction = p2 - p1
    length = direction.length
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=length, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    if mat:
        obj.data.materials.append(mat)
    try:
        bpy.ops.object.shade_smooth()
    except Exception:
        pass
    if coll:
        move_to_collection(obj, coll)
    return obj


def add_cylinder(name, loc, radius, depth, mat=None, vertices=48, axis="Z", coll=None):
    rot = (0, 0, 0)
    if axis == "X":
        rot = (0, math.pi / 2, 0)
    elif axis == "Y":
        rot = (math.pi / 2, 0, 0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    try:
        bpy.ops.object.shade_smooth()
    except Exception:
        pass
    if coll:
        move_to_collection(obj, coll)
    return obj


def add_cone(name, loc, radius1, radius2, depth, mat=None, vertices=72, coll=None):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius1, radius2=radius2, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    try:
        bpy.ops.object.shade_smooth()
    except Exception:
        pass
    if coll:
        move_to_collection(obj, coll)
    return obj


def smooth_polyline_points(points, samples_per_corner=8, corner_cut=5.0):
    pts = [Vector(p) for p in points]
    if len(pts) < 3:
        return pts
    smoothed = [pts[0]]
    for i in range(1, len(pts) - 1):
        prev_pt = pts[i - 1]
        corner = pts[i]
        next_pt = pts[i + 1]
        in_vec = corner - prev_pt
        out_vec = next_pt - corner
        if in_vec.length < 1e-6 or out_vec.length < 1e-6:
            continue
        cut = min(corner_cut, in_vec.length * 0.42, out_vec.length * 0.42)
        p_start = corner - in_vec.normalized() * cut
        p_end = corner + out_vec.normalized() * cut
        if (p_start - smoothed[-1]).length > 0.05:
            smoothed.append(p_start)
        for j in range(1, samples_per_corner):
            t = j / samples_per_corner
            smoothed.append((1 - t) * (1 - t) * p_start + 2 * (1 - t) * t * corner + t * t * p_end)
        smoothed.append(p_end)
    smoothed.append(pts[-1])
    return smoothed


def add_curve_tube(name, points, radius, mat=None, resolution=2, coll=None, smooth=True, fill_caps=False):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 12
    curve.bevel_depth = radius
    curve.bevel_resolution = resolution
    curve.use_fill_caps = fill_caps
    curve_points = smooth_polyline_points(points) if smooth and len(points) > 2 else [Vector(p) for p in points]
    spline = curve.splines.new("POLY")
    spline.points.add(len(curve_points) - 1)
    for p, co in zip(spline.points, curve_points):
        p.co = (co[0], co[1], co[2], 1)
    obj = bpy.data.objects.new(name, curve)
    (coll or bpy.context.scene.collection).objects.link(obj)
    if mat:
        obj.data.materials.append(mat)
    return obj


def add_cubic_bezier_tube(name, p0, h0, h1, p1, radius, mat=None, resolution=3, coll=None, fill_caps=True):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 32
    curve.bevel_depth = radius
    curve.bevel_resolution = resolution
    curve.use_fill_caps = fill_caps
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(1)
    start, end = spline.bezier_points
    p0 = Vector(p0)
    h0 = Vector(h0)
    h1 = Vector(h1)
    p1 = Vector(p1)
    start.co = p0
    start.handle_left_type = "FREE"
    start.handle_right_type = "FREE"
    start.handle_left = p0 - (h0 - p0) * 0.35
    start.handle_right = h0
    end.co = p1
    end.handle_left_type = "FREE"
    end.handle_right_type = "FREE"
    end.handle_left = h1
    end.handle_right = p1 + (p1 - h1) * 0.35
    obj = bpy.data.objects.new(name, curve)
    (coll or bpy.context.scene.collection).objects.link(obj)
    if mat:
        obj.data.materials.append(mat)
    return obj


def quadratic_arc_points(p0, p1, bow_vec, samples=18):
    p0 = Vector(p0)
    p1 = Vector(p1)
    pts = []
    for i in range(samples):
        t = i / (samples - 1)
        bow = 1 - (2 * t - 1) ** 2
        pts.append(p0.lerp(p1, t) + Vector(bow_vec) * bow)
    return pts


def small_arc_points(p0, p1, bow_vec, samples=24):
    p0 = Vector(p0)
    p1 = Vector(p1)
    bow_vec = Vector(bow_vec)
    return [p0.lerp(p1, t / (samples - 1)) + bow_vec * math.sin(math.pi * t / (samples - 1)) for t in range(samples)]


def slot_quarter_arc_points(module_center, tangent, outward, profile, side_sign, membrane_half_len, slot_half_len, z):
    """Circular 90-degree turn from the exposed tube end into the rack slot."""
    sign = 1 if side_sign >= 0 else -1
    start_y = sign * membrane_half_len
    start_x = ipi_membrane_local_x(profile, start_y)
    radius = abs(slot_half_len - membrane_half_len)
    center_y = start_y
    center_x = start_x + radius
    if sign > 0:
        angles = [-math.pi / 2 + (math.pi / 2) * i / (SLOT_ARC_SAMPLES - 1) for i in range(SLOT_ARC_SAMPLES)]
    else:
        angles = [-math.pi / 2 - (math.pi / 2) * i / (SLOT_ARC_SAMPLES - 1) for i in range(SLOT_ARC_SAMPLES)]
    return [
        ipi_local_point(
            module_center,
            tangent,
            outward,
            center_y + radius * math.cos(theta),
            center_x + radius * math.sin(theta),
            z,
        )
        for theta in angles
    ]


def concat_points(*segments):
    out = []
    for segment in segments:
        for p in segment:
            p = Vector(p)
            if not out or (p - out[-1]).length > 0.01:
                out.append(p)
    return out


def add_polygon_prism(name, points_xy, z_min, z_max, mat=None, coll=None):
    verts = [(x, y, z_min) for x, y in points_xy] + [(x, y, z_max) for x, y in points_xy]
    n = len(points_xy)
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        faces.append((i, (i + 1) % n, n + (i + 1) % n, n + i))
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    (coll or bpy.context.scene.collection).objects.link(obj)
    if mat:
        obj.data.materials.append(mat)
    return obj


def hex_vertices(side=90.0):
    return [(side * math.cos(math.radians(90 + i * 60)), side * math.sin(math.radians(90 + i * 60))) for i in range(6)]


def add_hex_wall_reactor(side, height, wall_thick, mat, edge_mat, coll):
    verts = [Vector((x, y, 0)) for x, y in hex_vertices(side)]
    for i in range(6):
        v1 = verts[i]
        v2 = verts[(i + 1) % 6]
        mid = (v1 + v2) / 2
        tangent = (v2 - v1).normalized()
        angle = math.atan2(tangent.y, tangent.x)
        add_box(
            f"clear hex reactor wall {i+1}",
            (mid.x, mid.y, height / 2),
            ((v2 - v1).length, wall_thick, height),
            mat,
            rot_z=angle,
            bevel=0.8,
            coll=coll,
        )
    add_polygon_prism("transparent hex bottom plate", hex_vertices(side + 5), -3.0, 0.0, edge_mat, coll=coll)


def _parse_ascii_stl_components(stl_path):
    faces = []
    current = []
    for line in stl_path.read_text(errors="ignore").splitlines():
        parts = line.strip().split()
        if len(parts) == 4 and parts[0] == "vertex":
            current.append(tuple(round(float(value), 6) for value in parts[1:]))
            if len(current) == 3:
                faces.append(tuple(current))
                current = []

    coords = []
    coord_to_index = {}
    indexed_faces = []
    adjacency = []
    for face in faces:
        ids = []
        for coord in face:
            if coord not in coord_to_index:
                coord_to_index[coord] = len(coords)
                coords.append(coord)
                adjacency.append(set())
            ids.append(coord_to_index[coord])
        indexed_faces.append(tuple(ids))
        for a_i, a in enumerate(ids):
            for b in ids[a_i + 1:]:
                adjacency[a].add(b)
                adjacency[b].add(a)

    seen = set()
    components = []
    for start in range(len(coords)):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        component = []
        while stack:
            idx = stack.pop()
            component.append(idx)
            for neighbor in adjacency[idx]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(component)

    return coords, indexed_faces, components


def add_custom_hex_acrylic_shell(mat, edge_mat, coll):
    source_path = next((path for path in CUSTOM_HEX_STL_CANDIDATES if path.exists()), None)
    if source_path is None:
        add_hex_wall_reactor(90.0, 60.0, 3.0, mat, edge_mat, coll)
        return None

    coords, indexed_faces, components = _parse_ascii_stl_components(source_path)
    component_scores = []
    for component in components:
        mins = [min(coords[idx][axis] for idx in component) for axis in range(3)]
        maxs = [max(coords[idx][axis] for idx in component) for axis in range(3)]
        dims = [maxs[axis] - mins[axis] for axis in range(3)]
        score = abs(dims[0] - 180.0) + abs(dims[1] - 60.0) + abs(dims[2] - 155.88)
        component_scores.append((score, component))
    selected = set(min(component_scores, key=lambda item: item[0])[1])

    vertex_map = {}
    verts = []
    faces = []
    for face in indexed_faces:
        if not all(idx in selected for idx in face):
            continue
        new_face = []
        for idx in face:
            if idx not in vertex_map:
                x, y, z = coords[idx]
                vertex_map[idx] = len(verts)
                # Gmsh STL axes are X=hex long axis, Y=height, Z=hex short axis.
                verts.append((z, x, y))
            new_face.append(vertex_map[idx])
        faces.append(tuple(new_face))

    mesh = bpy.data.meshes.new("custom_slotted_hex_acrylic_shell_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("custom slotted acrylic hex reactor shell", mesh)
    coll.objects.link(obj)
    obj.data.materials.append(mat)
    obj.modifiers.new("clear shell weighted normals", "WEIGHTED_NORMAL")
    add_polygon_prism("clear acrylic bottom plate", hex_vertices(94.0), -3.0, 0.0, edge_mat, coll=coll)
    return obj


def load_ipi_stl_mesh(mat):
    source_path = next((path for path in STL_SOURCE_CANDIDATES if path.exists()), None)
    if source_path is None:
        raise FileNotFoundError("IPI rack STL was not found in the known source paths.")
    if not STL_PATH.exists() or STL_PATH.stat().st_size != source_path.stat().st_size:
        shutil.copyfile(source_path, STL_PATH)
    temp_coll = get_collection("00_source_meshes")
    bpy.ops.wm.stl_import(filepath=str(STL_PATH))
    obj = bpy.context.object
    obj.name = "source IPI curved STL rack"
    obj.data.materials.append(mat)
    # Normalize mesh to local origin, scale height to 16 mm while keeping the STL's curved plan.
    mins = [1e9, 1e9, 1e9]
    maxs = [-1e9, -1e9, -1e9]
    for v in obj.data.vertices:
        for i in range(3):
            mins[i] = min(mins[i], v.co[i])
            maxs[i] = max(maxs[i], v.co[i])
    center = Vector(((mins[0] + maxs[0]) / 2, (mins[1] + maxs[1]) / 2, (mins[2] + maxs[2]) / 2))
    height_scale = 16.0 / (maxs[2] - mins[2])
    for v in obj.data.vertices:
        v.co -= center
        v.co.z *= height_scale
    obj.data.update()
    obj.hide_viewport = True
    obj.hide_render = True
    move_to_collection(obj, temp_coll)
    return obj.data


def duplicate_ipi_rack(mesh, name, center, tangent, mat, coll):
    tangent_angle = math.atan2(tangent.y, tangent.x)
    obj = bpy.data.objects.new(name, mesh)
    obj.location = center
    # STL length is along local Y, so rotate local Y onto the wall tangent.
    obj.rotation_euler = (0, 0, tangent_angle - math.pi / 2)
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    coll.objects.link(obj)
    return obj


def build_rack_exterior_profile(mesh, sample_count=161, band_width=0.55):
    ys = [v.co.y for v in mesh.vertices]
    y_min = min(ys)
    y_max = max(ys)
    samples = []
    for i in range(sample_count):
        y = y_min + (y_max - y_min) * i / (sample_count - 1)
        band = [v.co.x for v in mesh.vertices if abs(v.co.y - y) <= band_width]
        radius = band_width
        while not band and radius < 3.0:
            radius += 0.35
            band = [v.co.x for v in mesh.vertices if abs(v.co.y - y) <= radius]
        samples.append((y, min(band), max(band)))
    return samples


def interpolate_profile_x(profile, local_y, edge_index):
    if local_y <= profile[0][0]:
        return profile[0][edge_index]
    if local_y >= profile[-1][0]:
        return profile[-1][edge_index]
    for i in range(1, len(profile)):
        y0 = profile[i - 1][0]
        y1 = profile[i][0]
        if local_y <= y1:
            t = (local_y - y0) / (y1 - y0)
            return profile[i - 1][edge_index] * (1.0 - t) + profile[i][edge_index] * t
    return profile[-1][edge_index]


def rack_exterior_local_x(profile, local_y):
    # The real STL's outside of the curved white rack is the minimum local-X
    # edge. The positive-X side is the open window where the old model placed
    # the 10 membrane tubes incorrectly.
    return interpolate_profile_x(profile, local_y, 1)


def ipi_membrane_local_x(profile, local_y):
    return rack_exterior_local_x(profile, local_y) - RACK_EXTERIOR_CLEARANCE


def ipi_local_point(module_center, tangent, outward, local_y, local_x, z):
    return Vector(module_center) + tangent * local_y + outward * local_x + Vector((0, 0, z - module_center.z))


def ipi_membrane_point(module_center, tangent, outward, profile, local_y, z):
    return ipi_local_point(module_center, tangent, outward, local_y, ipi_membrane_local_x(profile, local_y), z)


def add_slot_height_reducer(name, slot_center, tangent, outward, mat, coll, visible_height=17.2):
    tangent_angle = math.atan2(tangent.y, tangent.x)
    plug_height = (20.0 - visible_height) / 2.0
    for suffix, sign in [("upper", 1), ("lower", -1)]:
        loc = Vector(slot_center) + outward * 2.8 + Vector((0, 0, sign * (visible_height / 2.0 + plug_height / 2.0)))
        add_box(
            f"{name} {suffix} acrylic slot height reducer",
            loc,
            (5.6, 4.2, plug_height),
            mat,
            rot_z=tangent_angle,
            bevel=0.25,
            coll=coll,
        )


def add_beaker(name, x, y, z, glass, water, coll):
    add_cylinder(name + " tall outer glass", (x, y, z + 25.0), 14.5, 50.0, glass, vertices=72, coll=coll)
    add_cylinder(name + " taller water volume", (x, y, z + 20.5), 11.2, 37.0, water, vertices=72, coll=coll)
    add_cylinder(name + " high lip ring", (x, y, z + 51.0), 14.8, 2.0, glass, vertices=72, coll=coll)
    add_box(name + " small pouring lip", (x + 12.5, y, z + 51.5), (5.5, 4, 2.2), glass, bevel=1.0, coll=coll)


def add_syringe(name, base, direction, length, mat_glass, mat_water, mat_blue, mat_metal, coll):
    base = Vector(base)
    direction = Vector(direction).normalized()
    barrel_start = base
    barrel_end = base + direction * length
    add_cylinder_between(name + " barrel", barrel_start, barrel_end, 4.8, mat_glass, vertices=48, coll=coll)
    add_cylinder_between(name + " nearly full water liquid", barrel_start + direction * 2.2, barrel_end - direction * 2.8, 3.65, mat_water, vertices=48, coll=coll)
    add_cylinder_between(name + " blue luer tip", barrel_start - direction * 8, barrel_start, 2.2, mat_blue, vertices=32, coll=coll)
    return barrel_start - direction * 8, barrel_end, barrel_end


def add_upright_water_supply_pack(name, tube_start, direction, mat_glass, mat_water, mat_blue, mat_ptfe, coll):
    direction = Vector(direction).normalized()
    rot_z = math.atan2(direction.y, direction.x) + math.pi / 2
    tube_start = Vector(tube_start)
    center = tube_start + direction * 29
    center.z = 49.5
    add_box(name + " shortened upright transparent water pack", center, (14.0, 3.4, 30.0), mat_glass, rot_z=rot_z, bevel=3.0, coll=coll)
    add_box(name + " compact contained water volume", center + Vector((0, -0.35, -2.7)), (11.8, 2.3, 20.0), mat_water, rot_z=rot_z, bevel=2.0, coll=coll)
    lower_port = center + Vector((0, 0, -17.0))
    tube_entry = lower_port - Vector((0, 0, 1.8))
    add_cubic_bezier_tube(
        name + " single smooth PTFE feed from shortened water pack",
        tube_start,
        tube_start + direction * 18.0,
        tube_entry - Vector((0, 0, 12.0)),
        tube_entry,
        UPRIGHT_PACK_TUBE_RADIUS,
        mat_ptfe,
        resolution=3,
        coll=coll,
        fill_caps=True,
    )
    add_cylinder_between(name + " compact lower pack outlet", lower_port - Vector((0, 0, 1.6)), lower_port + Vector((0, 0, 1.6)), 0.92, mat_blue, vertices=20, coll=coll)


def add_three_way_valve(name, center, mat_blue, mat_clear, coll):
    center = Vector(center)
    add_cylinder(name + " clear body", center, 3.0, 10, mat_clear, vertices=32, axis="Z", coll=coll)
    for angle in [0, 120, 240]:
        d = Vector((math.cos(math.radians(angle)), math.sin(math.radians(angle)), 0))
        add_cylinder_between(name + f" blue handle {angle}", center, center + d * 8, 1.0, mat_blue, vertices=16, coll=coll)
    return center


def add_iv_bag(name, loc, mat_bag, mat_water, mat_blue, coll):
    x, y, z = loc
    add_box(name + " soft bag body", (x, y, z), (25, 4, 48), mat_bag, bevel=6, coll=coll)
    add_box(name + " lowered contained water fill", (x, y - 0.4, z - 7.0), (21, 3, 29), mat_water, bevel=4, coll=coll)
    add_cylinder(name + " neck", (x, y, z - 29), 3.2, 8, mat_bag, vertices=32, coll=coll)
    add_cylinder(name + " blue clamp", (x, y - 0.2, z - 36), 3.4, 4.5, mat_blue, vertices=32, coll=coll)
    return Vector((x, y, z - 40))


def add_silicone_cap(name, pos, direction, mat_cap, coll):
    direction = Vector(direction).normalized()
    start = Vector(pos) - direction * 3.2
    end = Vector(pos) + direction * 4.8
    add_cylinder_between(name + " silicone sleeve covering PTFE end", start, end, 0.78, mat_cap, vertices=24, coll=coll)
    add_cylinder_between(name + " rounded sealed tip", end, end + direction * 1.8, 0.66, mat_cap, vertices=24, coll=coll)


def build_ipi_side_module(index, v1, v2, rack_mesh, rack_profile, mats, feed_to_bag=False):
    white, ptfe, blue, glue, acrylic, cap_mat, water, metal = mats
    coll = get_collection(f"03_IPI_modules/IPI_module_{index:02d}")
    fluid_coll = get_collection("04_external_fluidics")

    p1 = Vector((v1[0], v1[1], 0))
    p2 = Vector((v2[0], v2[1], 0))
    mid = (p1 + p2) / 2
    tangent = (p2 - p1).normalized()
    outward = mid.normalized()
    inward = -outward

    module_z = 18.0
    module_center = mid + inward * 13 + Vector((0, 0, module_z))
    duplicate_ipi_rack(rack_mesh, f"IPI curved STL rack {index:02d}", module_center, tangent, white, coll)

    module_len = 58.0
    half_module_len = module_len / 2
    membrane_visible_half_len = 26.8
    membrane_radius = 0.80
    ptfe_radius = 0.45
    z_levels = [module_center.z - 7.02 + k * 1.56 for k in range(10)]
    feed_center = mid + outward * 78 - tangent * 42 + Vector((0, 0, module_z))
    cap_column_base = mid + outward * 80 + tangent * 44

    for k, z in enumerate(z_levels):
        local_ys = [-membrane_visible_half_len + 2 * membrane_visible_half_len * step / 25 for step in range(26)]
        membrane_pts = [ipi_membrane_point(module_center, tangent, outward, rack_profile, local_y, z) for local_y in local_ys]
        left_end = membrane_pts[0]
        right_end = membrane_pts[-1]
        add_curve_tube(f"STL-exterior 1.6mm PES membrane tube {k+1:02d}", membrane_pts, membrane_radius, white, resolution=3, coll=coll)

        feed_slot_arc = slot_quarter_arc_points(module_center, tangent, outward, rack_profile, -1, membrane_visible_half_len, half_module_len, z)
        feed_slot_exterior = feed_slot_arc[-1]
        feed_slot_exit = ipi_local_point(module_center, tangent, outward, -half_module_len, RACK_SLOT_EXIT_LOCAL_X, z)
        feed_external_start = ipi_local_point(module_center, tangent, outward, -half_module_len, RACK_EXTERNAL_TUBE_LOCAL_X, z + 0.25)
        twist_angle = math.radians(-115 + k * 25)
        stopper_face = feed_center - outward * 3.6
        feed_target = stopper_face + tangent * (math.sin(twist_angle) * 3.2) + Vector((0, 0, math.cos(twist_angle) * 3.2))
        feed_slot_pts = concat_points(feed_slot_arc, [feed_slot_exit, feed_external_start])
        add_curve_tube(f"feed-side 0.9mm PTFE through slot transition {k+1:02d}", feed_slot_pts, ptfe_radius, ptfe, resolution=2, coll=coll, smooth=False, fill_caps=True)
        feed_handle0 = feed_external_start + outward * 25.0 + Vector((0, 0, 0.25))
        feed_handle1 = feed_target - outward * 22.0
        add_cubic_bezier_tube(
            f"feed-side smooth Bezier approach to syringe stopper {k+1:02d}",
            feed_external_start,
            feed_handle0,
            feed_handle1,
            feed_target,
            ptfe_radius,
            ptfe,
            resolution=3,
            coll=coll,
            fill_caps=True,
        )

        cap_slot_arc = slot_quarter_arc_points(module_center, tangent, outward, rack_profile, 1, membrane_visible_half_len, half_module_len, z)
        cap_slot_exterior = cap_slot_arc[-1]
        cap_slot_exit = ipi_local_point(module_center, tangent, outward, half_module_len, RACK_SLOT_EXIT_LOCAL_X, z)
        cap_external_start = ipi_local_point(module_center, tangent, outward, half_module_len, RACK_EXTERNAL_TUBE_LOCAL_X, z + 0.25)
        cap_pos = cap_column_base + Vector((0, 0, z))
        cap_axis = (cap_pos - cap_external_start).normalized()
        cap_line_end = cap_pos - cap_axis * 2.0
        cap_slot_pts = concat_points(cap_slot_arc, [cap_slot_exit, cap_external_start])
        add_curve_tube(f"vertical capped-side 0.9mm PTFE through slot transition {k+1:02d}", cap_slot_pts, ptfe_radius, ptfe, resolution=2, coll=coll, smooth=False, fill_caps=True)
        cap_handle0 = cap_external_start + outward * 24.0 + Vector((0, 0, 0.15))
        cap_handle1 = cap_line_end - cap_axis * 24.0
        add_cubic_bezier_tube(
            f"vertical capped-side smooth Bezier approach to silicone cap {k+1:02d}",
            cap_external_start,
            cap_handle0,
            cap_handle1,
            cap_line_end,
            ptfe_radius,
            ptfe,
            resolution=3,
            coll=coll,
            fill_caps=True,
        )
        add_silicone_cap(f"individual silicone cap {k+1:02d}", cap_pos, cap_axis, cap_mat, coll)

    # Blue butyl rubber stopper inserted in a short syringe barrel.
    add_cylinder_between(f"blue butyl stopper ring {index:02d}", feed_center - outward * 3, feed_center + outward * 3, 5.4, blue, vertices=40, coll=fluid_coll)
    add_cylinder_between(f"white wrapped stopper body {index:02d}", feed_center + outward * 3, feed_center + outward * 10, 5.0, acrylic, vertices=40, coll=fluid_coll)
    syringe_tip, syringe_back, water_pack_tube_start = add_syringe(
        f"feed syringe receiving stopper {index:02d}",
        feed_center + outward * 10,
        outward,
        35,
        acrylic,
        water,
        blue,
        metal,
        fluid_coll,
    )
    add_curve_tube(f"stopper into syringe short PTFE connection {index:02d}", [feed_center + outward * 6, syringe_tip], ptfe_radius, ptfe, resolution=2, coll=fluid_coll)
    add_upright_water_supply_pack(
        f"upright water supply pack behind syringe {index:02d}",
        water_pack_tube_start,
        outward,
        acrylic,
        water,
        blue,
        ptfe,
        fluid_coll,
    )

    return {
        "feed_center": feed_center,
        "syringe_back": syringe_back,
        "outward": outward,
        "tangent": tangent,
        "feed_to_bag": feed_to_bag,
    }


def add_light_source(mats):
    black, metal, light_mat = mats
    coll = get_collection("05_top_light_source")
    add_cylinder("larger top xenon lamp lens", (0, 0, 118), 19, 8, metal, vertices=96, coll=coll)
    add_cone("wider top black lamp shade", (0, 0, 107), 31, 14, 20, black, vertices=96, coll=coll)
    add_box("compact lamp housing", (0, 0, 130), (38, 30, 12), black, bevel=1.5, coll=coll)
    for x in [-16, -12, -8, -4, 0, 4, 8, 12, 16]:
        add_box(f"lamp heat sink fin {x}", (x, 0, 141), (1.0, 32, 11), black, bevel=0.25, coll=coll)

    apex = Vector((0, 0, 101))
    for ring, radius, z in [(1, 34, 78), (2, 68, 58), (3, 104, 43)]:
        count = {1: 12, 2: 24, 3: 36}[ring]
        for i in range(count):
            a = 2 * math.pi * i / count + (math.pi / count if ring in {2, 3} else 0)
            end = Vector((radius * math.cos(a), radius * math.sin(a), z))
            add_curve_tube(f"xenon light ray {ring}-{i}", [apex, end], 0.16, light_mat, resolution=1, coll=coll)
    for i in range(6):
        a = math.radians(60 * i + 30)
        end = Vector((98 * math.cos(a), 98 * math.sin(a), 45))
        add_curve_tube(f"six-face uniform illumination guide {i+1}", [apex, end], 0.24, light_mat, resolution=1, coll=coll)
    add_cone("wide soft transparent light cone covering all six faces", (0, 0, 76), 108, 8, 62, light_mat, vertices=144, coll=coll)


def add_shared_infusion_setup(module_infos, mats):
    acrylic, water, blue, metal, ptfe = mats
    coll = get_collection("04_external_fluidics")
    bag_out = add_iv_bag("shared medical infusion bag with lowered water level", (-142, -28, 66), acrylic, water, blue, coll)
    valve_center = add_three_way_valve("shared blue three-way valve", (-105, -82, 23), blue, acrylic, coll)
    add_curve_tube("infusion bag outlet to three-way valve", [bag_out, Vector((-145, -72, 52)), valve_center], SHARED_FLUIDIC_TUBE_RADIUS, ptfe, resolution=3, coll=coll)
    manifold = Vector((-76, -62, 38))
    add_curve_tube("three-way valve to clear feed manifold", [valve_center, Vector((-92, -71, 34)), manifold], SHARED_FLUIDIC_TUBE_RADIUS, ptfe, resolution=3, coll=coll)

    for i, info in enumerate(sorted(module_infos, key=lambda item: math.atan2(item["feed_center"].y, item["feed_center"].x)), 1):
        lift = 11.0 + (i % 3) * 4.0
        mid = (info["syringe_back"] + manifold) / 2 + Vector((0, 0, lift))
        add_curve_tube(f"infusion manifold to syringe back line {i:02d}", [manifold, mid, info["syringe_back"]], SHARED_FLUIDIC_TUBE_RADIUS, ptfe, resolution=3, coll=coll)


def granule_overlaps_ipi_zone(x, y, z, rx=0.0, ry=0.0, rz=0.0, side=90.0):
    point = Vector((x, y, 0))
    lateral_margin = max(rx, ry) + 2.2
    z_margin = rz + 1.2
    hv = [Vector((vx, vy, 0)) for vx, vy in hex_vertices(side)]
    for i in range(6):
        p1 = hv[i]
        p2 = hv[(i + 1) % 6]
        mid = (p1 + p2) / 2
        tangent = (p2 - p1).normalized()
        outward = mid.normalized()
        module_center = mid - outward * 13
        rel = point - module_center
        local_y = rel.dot(tangent)
        local_x = rel.dot(outward)
        if (
            -40.0 - lateral_margin <= local_y <= 40.0 + lateral_margin
            and -26.0 - lateral_margin <= local_x <= 35.0 + lateral_margin
            and 6.0 - z_margin <= z <= 33.5 + z_margin
        ):
            return True
    return False


def add_combined_soil_granules(mat_list, coll, side=90.0):
    rng = random.Random(23)
    verts = []
    faces = []
    mat_indices = []
    # Fine, irregular ellipsoid grains read more like wet packed soil than
    # large floating diamond-shaped chunks.
    rings = [
        (0.0, 0.0, 1.0),
        (0.55, 0.0, 0.78),
        (0.95, 0.0, 0.28),
        (0.95, 0.0, -0.28),
        (0.55, 0.0, -0.78),
        (0.0, 0.0, -1.0),
    ]
    base_dirs = []
    for ring_idx, (r, _, z_dir) in enumerate(rings):
        if ring_idx in {0, len(rings) - 1}:
            base_dirs.append([(0.0, 0.0, z_dir)])
        else:
            base_dirs.append([(r * math.cos(math.radians(a)), r * math.sin(math.radians(a)), z_dir) for a in range(0, 360, 45)])
    target_count = 980
    placed = 0
    attempts = 0
    while placed < target_count and attempts < target_count * 45:
        attempts += 1
        side_sign = -1 if rng.random() < 0.5 else 1
        x = rng.uniform(5, 80) * side_sign
        y_limit = 88 - abs(x) / math.sqrt(3)
        y = rng.uniform(-y_limit, y_limit)
        z = rng.uniform(1.0, 35.0)
        if rng.random() < 0.38:
            z = rng.uniform(31.0, 36.0)
        rx = rng.uniform(0.20, 0.85)
        ry = rng.uniform(0.18, 0.75)
        rz = rng.uniform(0.06, 0.24)
        if granule_overlaps_ipi_zone(x, y, z, rx=rx + 1.1, ry=ry + 1.1, rz=rz + 0.7, side=side):
            continue
        angle = rng.random() * math.tau
        ca = math.cos(angle)
        sa = math.sin(angle)
        row_indices = []
        for ring in base_dirs:
            row = []
            for dx, dy, dz in ring:
                jitter = rng.uniform(0.82, 1.18)
                px = dx * rx * jitter
                py = dy * ry * jitter
                pz = dz * rz * rng.uniform(0.80, 1.15)
                row.append(len(verts))
                verts.append((x + px * ca - py * sa, y + px * sa + py * ca, z + pz))
            row_indices.append(row)
        mat_idx = rng.randrange(len(mat_list))
        top = row_indices[0][0]
        bottom = row_indices[-1][0]
        first_ring = row_indices[1]
        last_ring = row_indices[-2]
        n = len(first_ring)
        for i in range(n):
            faces.append((top, first_ring[(i + 1) % n], first_ring[i]))
            mat_indices.append(mat_idx)
            faces.append((last_ring[i], last_ring[(i + 1) % n], bottom))
            mat_indices.append(mat_idx)
        for r_i in range(1, len(row_indices) - 2):
            row_a = row_indices[r_i]
            row_b = row_indices[r_i + 1]
            for i in range(n):
                faces.append((row_a[i], row_a[(i + 1) % n], row_b[(i + 1) % n], row_b[i]))
                mat_indices.append(mat_idx)
        placed += 1
    mesh = bpy.data.meshes.new("combined_soil_granules_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("combined soil granules scatter", mesh)
    coll.objects.link(obj)
    for mat in mat_list:
        obj.data.materials.append(mat)
    for poly, mat_idx in zip(obj.data.polygons, mat_indices):
        poly.material_index = mat_idx
    return obj


def build_model():
    clear_scene()
    random.seed(31)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 0.001

    reactor_coll = get_collection("01_reactor_and_internal_volumes")
    beaker_coll = get_collection("02_central_beakers")
    soil_coll = get_collection("01_reactor_and_internal_volumes/soil_texture")
    camera_coll = get_collection("06_camera_and_lights")

    acrylic = make_mat("clear acrylic", (0.82, 0.94, 1.0, 0.30), 0.30)
    acrylic_edge = make_mat("thick acrylic edges", (0.65, 0.80, 0.88, 0.45), 0.45)
    water = make_mat("clear water", (0.30, 0.68, 1.0, 0.42), 0.42)
    soil = make_mat("packed soil volume", (0.46, 0.30, 0.15, 0.72), 0.72)
    white = make_mat("white nylon/PES", (0.94, 0.93, 0.87, 1), 1)
    ptfe = make_mat("translucent PTFE tubing", (0.88, 0.96, 1.0, 0.64), 0.64)
    blue = make_mat("blue butyl rubber", (0.02, 0.32, 0.82, 1), 1)
    glue = make_mat("dark cured adhesive seals", (0.035, 0.028, 0.02, 1), 1)
    cap_mat = make_mat("white silicone caps", (0.96, 0.96, 0.92, 1), 1)
    metal = make_mat("metal hardware", (0.72, 0.72, 0.70, 1), 1, metallic=0.35)
    black = make_mat("black lamp housing", (0.015, 0.015, 0.014, 1), 1, metallic=0.2)
    light_mat = make_mat("warm transparent xenon light", (1.0, 0.58, 0.08, 0.22), 0.22)
    matte_base = make_mat("matte foil bench", (0.72, 0.72, 0.70, 1), 1, metallic=0.12)

    side = 90.0
    add_box("silver foil working surface", (0, 0, -5), (340, 300, 2), matte_base, bevel=1.5, coll=reactor_coll)
    add_custom_hex_acrylic_shell(acrylic, acrylic_edge, reactor_coll)

    fill_side = side - 2.5
    verts = hex_vertices(fill_side)
    left_half = [(0, fill_side), (0, -fill_side), verts[2], verts[1]]
    right_half = [(0, fill_side), verts[5], verts[4], (0, -fill_side)]
    add_polygon_prism("left packed soil sealed half", left_half, 0.4, 36.5, soil, coll=reactor_coll)
    add_polygon_prism("right packed soil sealed half", right_half, 0.4, 36.5, soil, coll=reactor_coll)
    add_polygon_prism("left water layer sealed half", left_half, 36.8, 55.0, water, coll=reactor_coll)
    add_polygon_prism("right water layer sealed half", right_half, 36.8, 55.0, water, coll=reactor_coll)
    add_box("full-height central acrylic partition", (0, 0, 31.5), (4.2, 181, 63), acrylic_edge, bevel=0.35, coll=reactor_coll)
    add_box("partition top lip", (0, 0, 62.5), (4.8, 181, 4.0), acrylic_edge, bevel=0.4, coll=reactor_coll)

    for i, (x, y) in enumerate([(-22, -24), (22, -24), (-22, 24), (22, 24)], 1):
        add_beaker(f"central water beaker {i}", x, y, 1.5, acrylic, water, beaker_coll)

    rack_mesh = load_ipi_stl_mesh(white)
    rack_profile = build_rack_exterior_profile(rack_mesh)
    hv = hex_vertices(side)
    module_infos = []
    for i in range(6):
        module_infos.append(
            build_ipi_side_module(
                i + 1,
                hv[i],
                hv[(i + 1) % 6],
                rack_mesh,
                rack_profile,
                (white, ptfe, blue, glue, acrylic, cap_mat, water, metal),
                feed_to_bag=(i in {0, 1, 5}),
            )
        )

    add_light_source((black, metal, light_mat))

    bpy.ops.object.light_add(type="AREA", location=(0, -180, 210))
    area = bpy.context.object
    area.name = "large studio area light"
    area.data.energy = 1550
    area.data.size = 235
    move_to_collection(area, camera_coll)
    bpy.ops.object.light_add(type="POINT", location=(0, 0, 112))
    point = bpy.context.object
    point.name = "xenon point light"
    point.data.energy = 620
    move_to_collection(point, camera_coll)
    bpy.ops.object.camera_add(location=(205, -255, 142), rotation=(math.radians(62), 0, math.radians(40)))
    cam = bpy.context.object
    cam.name = "preview camera"
    bpy.context.scene.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 335
    move_to_collection(cam, camera_coll)

    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.display.shading.light = "STUDIO"
    bpy.context.scene.display.shading.color_type = "MATERIAL"
    bpy.context.scene.display.shading.show_cavity = True
    bpy.context.scene.render.resolution_x = 1800
    bpy.context.scene.render.resolution_y = 1200
    bpy.context.scene.world.color = (1, 1, 1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    cleanup_empty_collections()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    bpy.context.scene.render.filepath = str(PREVIEW_PATH)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    build_model()
