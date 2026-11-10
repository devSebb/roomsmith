"""Tool schemas: what the model reads. Written for a model, not a human."""

from __future__ import annotations

TOOLSET = "roomsmith"

_PLACE = {
    "type": "object",
    "description": (
        "Where to put it. Give ONE of: against_wall (wall id like 'w1' or label 'back'/'left'/'right'/'front'; "
        "optional align 'left'|'center'|'right' as seen from inside facing that wall, offset_m from that end); "
        "next_to (object id) with side 'left'|'right'|'front'|'behind' relative to that object's facing; "
        "in_corner [wall_a, wall_b]; centered_in_room true; on (object id, to rest on top of it); "
        "by [dx, dz] to nudge; or position_m [x, y, z] (y = height of the object's underside; ≥ 1.9 m counts as overhead and no longer blocks doors or walkways). Optional gap_m (default 0.02), facing (wall id/label), yaw_deg."
    ),
    "properties": {
        "against_wall": {"type": "string"},
        "align": {"type": "string", "enum": ["left", "center", "right"]},
        "offset_m": {"type": "number"},
        "next_to": {"type": "string"},
        "side": {"type": "string", "enum": ["left", "right", "front", "behind"]},
        "in_corner": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
        "centered_in_room": {"type": "boolean"},
        "on": {"type": "string"},
        "by": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        "position_m": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 3},
        "gap_m": {"type": "number"},
        "facing": {"type": "string"},
        "yaw_deg": {"type": "number"},
    },
}

_DIMS = {
    "type": "array",
    "description": "[width, height, depth] in metres: width across the front, depth front-to-back",
    "items": {"type": "number"},
    "minItems": 3,
    "maxItems": 3,
}

PROJECTS = {
    "name": "roomsmith_projects",
    "description": (
        "List the user's rooms, switch the active room, rename or delete one, and learn how to open the editor. "
        "Most other roomsmith tools act on the active room when project_id is omitted."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "activate", "rename", "delete"], "default": "list"},
            "project_id": {"type": "string", "description": "Room id (or its exact name) for activate/rename/delete"},
            "name": {"type": "string", "description": "New name for rename"},
        },
    },
}

NEW_ROOM = {
    "name": "roomsmith_new_room",
    "description": (
        "Create a new room. Either give the footprint (width_m along the back wall, depth_m, height_m) for a measured room, "
        "or give a `layout` draft when you can SEE a photo of the room yourself: estimate the room and its furniture in the draft format "
        "(walls named from the camera: back = the wall the camera faces, left, right, front = behind the camera; positions as fractions). "
        "The new room becomes the active room. Walls are w1 back, w2 right, w3 front, w4 left."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Short room name, e.g. 'Living room'"},
            "width_m": {"type": "number", "description": "Length of the back wall (x axis), metres"},
            "depth_m": {"type": "number", "description": "Back wall to front wall (z axis), metres"},
            "height_m": {"type": "number", "description": "Ceiling height, metres (default 2.5)"},
            "layout": {
                "type": "object",
                "description": (
                    "Draft from a photo you can see. {room:{width_m,depth_m,height_m}, colors:{walls,floor}, "
                    "openings:[{wall:'back'|'left'|'right'|'front', kind:'door'|'window'|'opening', position_fraction:0..1 along the wall "
                    "(0 at its left end seen from inside), width_m, height_m, sill_m}], "
                    "objects:[{label, category, width_m, height_m, depth_m, against_wall:'back'|'left'|'right'|'front'|'none', "
                    "across_fraction:0..1 (left wall to right wall), into_fraction:0..1 (back wall to camera), facing, "
                    "mount:'floor'|'surface'|'wall'|'ceiling' (pendant lights are 'ceiling', pictures on a wall are 'wall'), elevation_m (height of its lowest point), color, confidence}], notes}. "
                    "Use real-world anchors (door ~0.8 x 2.03 m). Everything is marked estimated until calibrated."
                ),
            },
            "photo_ids": {"type": "array", "items": {"type": "string"}, "description": "Photo ids to attach to the room, if any"},
        },
    },
}

FROM_PHOTO = {
    "name": "roomsmith_from_photo",
    "description": (
        "Build a draft room from one to four photo files on disk (JPEG/PNG/WebP paths, or photo ids uploaded through the editor). "
        "The plugin sends the images to the user's Hermes model and builds an editable 3D room: walls, door/window guesses, furniture as sized boxes. "
        "Sizes are estimates until the user gives one real measurement (then use roomsmith_apply with op 'calibrate'). "
        "If you can see the photo yourself in this conversation, you may instead call roomsmith_new_room with a `layout`."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "images": {"type": "array", "items": {"type": "string"}, "description": "File paths or photo ids", "minItems": 1, "maxItems": 4},
            "name": {"type": "string", "description": "Room name"},
            "notes": {"type": "string", "description": "Anything the user said about the room (known sizes, what to ignore)"},
        },
        "required": ["images"],
    },
}

INSPECT = {
    "name": "roomsmith_inspect",
    "description": (
        "Read the current room: size, walls (ids, labels, lengths), openings, every object with id, size, position and facing, the revision number, "
        "and open issues. Call this before editing so you have the ids and the current revision. detail 'full' returns the raw scene JSON too."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "detail": {"type": "string", "enum": ["summary", "full"], "default": "summary"},
        },
    },
}

APPLY = {
    "name": "roomsmith_apply",
    "description": (
        "Edit the room with one atomic batch of operations (all apply or none). Pass expected_revision from your last inspect; "
        "on 'revision_conflict' re-inspect and retry. Operations (each an object with 'op'):\n"
        "- add_object {name, category, dimensions_m?, place?, color?} (omit dimensions for a typical size)\n"
        "- move_object {id, place} | rotate_object {id, yaw_deg | by_deg | facing} | set_dimensions {id, dimensions_m | width_m/height_m/depth_m}\n"
        "- update_object {id, name?, category?, color?, locked?} | duplicate_object {id, place?} | remove_object {id} | swap_objects {a, b}\n"
        "- set_room_rectangle {width_m, depth_m} | set_room_height {height_m} | set_wall_length {id, length_m} | move_vertex {id, x?, z?, by?}\n"
        "- set_surface_color {surface: 'floor'|'ceiling'|'walls'|wall id, color: '#rrggbb'}\n"
        "- add_opening {wall: id or label ('front'), kind: 'door'|'window'|'opening', width_m? (door 0.9, window 1.2), offset_m | position_fraction (0..1 along the wall), height_m?, sill_m?, swing?, hinge?}\n"
        "- update_opening {id, ...same fields} | remove_opening {id}\n"
        "- calibrate {reference: {kind: 'room_size', width_m, depth_m}} fits the room to its real floor size (each axis separately — photos stretch depth more than width), keeps furniture sizes, keeps things against their walls. PREFER this when the user knows the room's size. "
        "Or {reference: {kind: 'wall_length'|'room_height'|'opening_width', id, real_m}} (room + positions; furniture sizes kept) or {kind: 'object_width'|'object_height'|'object_depth', id, real_m} (scales everything estimated).\n"
        "Placing or moving a floor piece with against_wall/next_to/in_corner/centered_in_room slides it to the nearest clear spot if it would land inside another piece or in a doorway's clear zone "
        "(the receipt says 'slid 0.62 m along the wall to clear X'); exact position_m is honoured as given; allow_overlap: true keeps the described spot. "
        "Things sitting on a piece (mount 'surface') move with it.\n"
        "Returns what changed, the new revision, and any issues the change caused (overlap, outside_room, blocks_door, blocks_window, tight_walkway, too_tall)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "expected_revision": {"type": "integer", "description": "The revision you last saw"},
            "operations": {"type": "array", "items": {"type": "object"}, "minItems": 1},
            "command_id": {"type": "string", "description": "Optional unique id so a retried call is applied once"},
        },
        "required": ["operations"],
    },
}
APPLY["parameters"]["properties"]["operations"]["items"] = {
    "type": "object",
    "properties": {
        "op": {"type": "string"},
        "id": {"type": "string"},
        "name": {"type": "string"},
        "category": {"type": "string"},
        "dimensions_m": _DIMS,
        "place": _PLACE,
        "color": {"type": "string"},
        "locked": {"type": "boolean"},
        "width_m": {"type": "number"},
        "height_m": {"type": "number"},
        "depth_m": {"type": "number"},
        "length_m": {"type": "number"},
        "yaw_deg": {"type": "number"},
        "by_deg": {"type": "number"},
        "facing": {"type": "string"},
        "a": {"type": "string"},
        "b": {"type": "string"},
        "surface": {"type": "string"},
        "wall_id": {"type": "string"},
        "kind": {"type": "string"},
        "offset_m": {"type": "number"},
        "position_fraction": {"type": "number"},
        "sill_m": {"type": "number"},
        "swing": {"type": "string"},
        "hinge": {"type": "string"},
        "x": {"type": "number"},
        "z": {"type": "number"},
        "by": {"type": "array", "items": {"type": "number"}},
        "reference": {"type": "object"},
        "force": {"type": "boolean"},
    },
    "required": ["op"],
}

CHECK = {
    "name": "roomsmith_check",
    "description": (
        "Fit and clearance questions, answered by geometry (quote the numbers, do not estimate). question:\n"
        "- 'issues': all current issues in the room\n"
        "- 'fits_at': does a box of dimensions_m fit at `place`, with how much to spare. object_id alone = test an existing object elsewhere; "
        "object_id + dimensions_m = test a REPLACEMENT (a new bed where the old bed is: the old one is ignored, place defaults to its spot)\n"
        "- 'where_fits': up to three spots along the walls where dimensions_m would fit, ranked by clearance\n"
        "- 'passes_door': would dimensions_m pass through the door(s) (conservative rule)\n"
        "- 'clearance': free distance around object_id on each side"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "question": {"type": "string", "enum": ["issues", "fits_at", "where_fits", "passes_door", "clearance"], "default": "issues"},
            "dimensions_m": _DIMS,
            "object_id": {"type": "string"},
            "place": _PLACE,
            "opening_id": {"type": "string"},
            "name": {"type": "string", "description": "Label for the candidate in the answer"},
        },
    },
}

READ_PRODUCT = {
    "name": "roomsmith_read_product",
    "description": (
        "Read a product page the user pasted (one request to that URL only): title, price, image and the printed dimensions, parsed to metres. "
        "Use it to answer 'would this fit?' (then roomsmith_check with its dimensions_m) before adding anything. "
        "Works on pages with schema.org Product data, Shopify stores and plain HTML; bot-protected or JavaScript-only shops return dims null -> ask the user for the size printed on the page. "
        "Never state product sizes from memory as if they came from the page."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "category": {"type": "string", "description": "sofa, bed_double, desk, ... when the user said what it is (a bed's 'L' is its length)"},
        },
        "required": ["url"],
    },
}

ADD_PRODUCT = {
    "name": "roomsmith_add_product",
    "description": (
        "Add a real product as a true-size stand-in box with its name, price, link and picture. Give the url alone and the plugin reads the page itself "
        "(title, price, image, printed dimensions). Or give dimensions_text exactly as written on the page (e.g. 'Width: 228 cm, Depth: 95 cm, Height: 83 cm' "
        "or 'W88.6\" x D39.4\" x H32.3\"') / dimensions_m from the user, plus title. Pass category when obvious (a bed's 'L' is its length). "
        "The plugin parses sizes in code and reports clearance and whether it passes the door. "
        "If the page prints no dimensions the reply says so: ask the user for the size, never use sizes from memory as dimensions_text."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "title": {"type": "string"},
            "dimensions_text": {"type": "string", "description": "Dimensions as written on the page"},
            "dimensions_m": _DIMS,
            "url": {"type": "string"},
            "image_url": {"type": "string"},
            "price": {"type": "string"},
            "category": {"type": "string", "description": "sofa, bed_double, desk, bookshelf, ... (helps the default colour)"},
            "color": {"type": "string"},
            "place": _PLACE,
            "expected_revision": {"type": "integer"},
        },
        "required": [],
    },
}

HISTORY = {
    "name": "roomsmith_history",
    "description": "Undo or redo the last change(s), or list recent revisions with who made them (you or the user in the editor).",
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "action": {"type": "string", "enum": ["undo", "redo", "list"], "default": "list"},
            "steps": {"type": "integer", "default": 1},
            "limit": {"type": "integer", "default": 10},
        },
    },
}

EXPORT = {
    "name": "roomsmith_export",
    "description": "Write the room to a file and return its path. format: 'json' (re-importable), 'glb' (3D model for Blender/Quick Look), 'summary' (text list with sizes and product links).",
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "format": {"type": "string", "enum": ["json", "glb", "summary"], "default": "glb"},
            "out_dir": {"type": "string", "description": "Folder to write into (default: the plugin's exports folder)"},
        },
    },
}

ALL = [PROJECTS, NEW_ROOM, FROM_PHOTO, INSPECT, APPLY, CHECK, READ_PRODUCT, ADD_PRODUCT, HISTORY, EXPORT]
TOOL_NAMES = [t["name"] for t in ALL]
