
import bpy
from bpy.types import Operator
from bpy.props import (
    StringProperty, IntProperty, BoolProperty, FloatProperty,
    CollectionProperty
)
from bpy.types import OperatorFileListElement
from bpy_extras.io_utils import ImportHelper
import numpy as np
import os


class GPENCIL_OT_import_lineart(Operator, ImportHelper):
    bl_idname = "gpencil.import_lineart"

    @classmethod
    def poll(cls, context):
        obj = getattr(context, "object", None)
        return bool(obj and obj.type in ("GREASEPENCIL", "GPENCIL"))
    bl_label = "Import Line Art"
    bl_options = {'REGISTER', 'UNDO'}

    # File browser
    filename_ext = ""
    filter_glob: StringProperty(
        default="*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff",
        options={'HIDDEN'},
    )

    files: CollectionProperty(
        type=OperatorFileListElement,
        options={'HIDDEN', 'SKIP_SAVE'},
    )

    directory: StringProperty(
        subtype='DIR_PATH',
        options={'HIDDEN'},
    )

    # Preprocessing


    threshold: IntProperty(
        name="Threshold",
        description="(Fixed) Background/foreground separation. Kept for backward compatibility.",
        default=90,
        min=0,
        max=255,
        options={'HIDDEN'},
    )

    # Preprocessing
    blur_pixels: IntProperty(
        name="Blur Pixels",
        description="Gaussian blur radius in pixels applied before vectorization (0 disables)",
        default=0,
        min=0,
        max=5,
    )

    downscale: IntProperty(
        name="Downscale",
        description="Factor to reduce image resolution. Higher values are faster but lose detail.",
        default=1,
        min=1,
        max=4,
    )

    verbose_logging: BoolProperty(
        name="Verbose Logging",
        description="Enable detailed console logging for debugging (slower)",
        default=False,
    )

    stroke_radius: FloatProperty(
        name="Stroke Radius",
        description="Thickness of strokes",
        default=0.01,
        min=0.001,
        max=0.1,
        precision=3,
    )

    scale_factor: FloatProperty(
        name="Scale",
        description="Scale factor for imported strokes",
        default=0.003,
        min=0.0001,
        max=1.0,
        precision=3,
    )

    target_layer: StringProperty(
        name="Layer",
        description="Target GP layer name",
        default="LineArt",
    )

    # Sequence
    start_frame: IntProperty(
        name="Start Frame",
        description="First frame for image sequence",
        default=1,
        min=1,
    )

    frame_step: IntProperty(
        name="Frame Step",
        description="Frames between each image in sequence",
        default=4,
        min=1,
    )

    def execute(self, context):

        obj = context.object
        if not obj or obj.type not in ("GREASEPENCIL", "GPENCIL"):
            self.report({'ERROR'}, "Select an active Grease Pencil object before importing line art")
            return {'CANCELLED'}

        from ..utils import vectorization

        # Check C++ backend
        if not vectorization.is_backend_available():
            self.report({'ERROR'},
                "C++ vectorization backend not available! "
                "Please reinstall addon with platform-specific wheels."
            )
            return {'CANCELLED'}

        # Get files
        if self.files:
            files = [os.path.join(self.directory, f.name) for f in self.files if f.name]
            files.sort()
        else:
            files = [self.filepath]

        if not files:
            self.report({'ERROR'}, "No files selected")
            return {'CANCELLED'}


        gp_obj, gp_data = self._get_or_create_gpencil(context)
        if not gp_data:
            self.report({'ERROR'}, "Failed to create GP object")
            return {'CANCELLED'}

        layer_name = self._get_unique_layer_name(gp_data, self.target_layer)
        layer = gp_data.layers.get(layer_name)
        if layer is None:
            layer = gp_data.layers.new(name=layer_name)

        total_strokes = 0
        frame_number = self.start_frame
        total_files = len(files)


        wm = context.window_manager
        wm.progress_begin(0, total_files)

        try:
            for file_idx, filepath in enumerate(files):
                # Update progress
                wm.progress_update(file_idx)

                if not os.path.exists(filepath):
                    continue

                try:

                    abs_filepath = bpy.path.abspath(filepath)

                    polylines = vectorization.process_image_file_with_downscale(
                        abs_filepath,
                        blur_pixels=self.blur_pixels,
                        user_downscale=self.downscale,
                        verbose=self.verbose_logging,
                    )

                    if len(polylines) > 0:

                        temp_img = bpy.data.images.load(abs_filepath)
                        orig_width, orig_height = temp_img.size
                        bpy.data.images.remove(temp_img)

                        stroke_count = self._create_strokes_gpv3(
                            layer, frame_number, polylines, orig_width, orig_height
                        )
                        total_strokes += stroke_count

                except Exception as e:
                    print(f"[GPAI Lineart] Error: {e}")

                frame_number += self.frame_step

        finally:
            wm.progress_end()

        if total_strokes > 0:
            self.report({'INFO'}, f"Imported {total_strokes} strokes from {total_files} image(s)")
        else:
            self.report({'WARNING'}, "No lines detected")

        if context.area:
            context.area.tag_redraw()

        return {'FINISHED'}

    def _create_strokes_gpv3(self, layer, frame_number, polylines, image_width, image_height):
        frame = None
        for f in layer.frames:
            if f.frame_number == frame_number:
                frame = f
                break

        if frame is None:
            frame = layer.frames.new(frame_number)

        drawing = frame.drawing
        if drawing is None:
            return 0

        valid_polylines = []
        for polyline in polylines:
            if isinstance(polyline, np.ndarray):
                if len(polyline) >= 2:
                    valid_polylines.append(polyline)
            elif len(polyline) >= 2:
                valid_polylines.append(np.array(polyline))

        if not valid_polylines:
            return 0

        sizes = [len(p) for p in valid_polylines]
        total_points = sum(sizes)

        try:
            drawing.add_strokes(sizes)

            # Center offsets
            center_x = (image_width * self.scale_factor) / 2
            center_z = (image_height * self.scale_factor) / 2

            positions = []
            for polyline in valid_polylines:
                for i in range(len(polyline)):
                    x = polyline[i, 0] if polyline.ndim == 2 else polyline[i][0]
                    y = polyline[i, 1] if polyline.ndim == 2 else polyline[i][1]






                    scaled_x = float(x * self.scale_factor) - center_x
                    scaled_z = float((image_height - y) * self.scale_factor) - center_z

                    positions.extend([scaled_x, 0.0, scaled_z])

            attrs = drawing.attributes



            if 'radius' not in attrs:
                attrs.new(name='radius', type='FLOAT', domain='POINT')
            if 'opacity' not in attrs:
                attrs.new(name='opacity', type='FLOAT', domain='POINT')

            if 'position' in attrs:
                attrs['position'].data.foreach_set('vector', positions)
                drawing.tag_positions_changed()


            if 'radius' in attrs:
                attrs['radius'].data.foreach_set('value', [float(self.stroke_radius)] * total_points)

            if 'opacity' in attrs:
                attrs['opacity'].data.foreach_set('value', [1.0] * total_points)

            return len(valid_polylines)

        except Exception as e:
            print(f"[GPAI Lineart] Error: {e}")
            return 0

    def _get_unique_layer_name(self, gp_data, base_name):
        if base_name not in gp_data.layers:
            return base_name

        counter = 1
        while True:
            new_name = f"{base_name}.{counter:03d}"
            if new_name not in gp_data.layers:
                return new_name
            counter += 1
            if counter > 999:
                return f"{base_name}.{counter}"

    def _get_or_create_gpencil(self, context):
        obj = context.object

        if obj and obj.type in ('GREASEPENCIL', 'GPENCIL'):
            return obj, obj.data

        for obj in context.scene.objects:
            if obj.type in ('GREASEPENCIL', 'GPENCIL'):
                context.view_layer.objects.active = obj
                return obj, obj.data

        try:
            bpy.ops.object.grease_pencil_add()
            obj = context.object
            obj.name = "LineArt_GP"
            return obj, obj.data
        except Exception:
            try:
                bpy.ops.object.gpencil_add(type='EMPTY')
                obj = context.object
                obj.name = "LineArt_GP"
                return obj, obj.data
            except Exception:
                return None, None

    def draw(self, context):
        layout = self.layout

        from ..utils import vectorization
        if not vectorization.is_backend_available():
            box = layout.box()
            box.alert = True
            box.label(text="C++ backend not available!", icon='ERROR')
            box.label(text="Reinstall addon with wheels")
            return

        obj = context.object
        if not obj or obj.type not in ('GREASEPENCIL', 'GPENCIL'):
            box = layout.box()
            box.alert = True
            box.label(text="Select an active Grease Pencil object", icon='ERROR')
            return

        box = layout.box()
        box.label(text="Stroke", icon='GREASEPENCIL')
        box.prop(self, "scale_factor")
        box.prop(self, "stroke_radius")
        box.prop(self, "target_layer")

        box = layout.box()
        box.label(text="Preprocessing", icon='IMAGE')
        box.prop(self, "downscale")
        box.prop(self, "blur_pixels")





        box = layout.box()
        box.label(text="Image Sequence", icon='SEQUENCE')
        box.prop(self, "start_frame")
        box.prop(self, "frame_step")

        box = layout.box()
        box.label(text="Developer", icon='PREFERENCES')
        box.prop(self, "verbose_logging")


def menu_func_import(self, context):
    self.layout.operator(
        GPENCIL_OT_import_lineart.bl_idname,
        text="GPAI Line Art (.png, .jpg)"
    )


def register():
    bpy.utils.register_class(GPENCIL_OT_import_lineart)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(GPENCIL_OT_import_lineart)
