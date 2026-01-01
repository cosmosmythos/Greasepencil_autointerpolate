"""
Import Line Art operator for converting raster images to Grease Pencil strokes.

Supports:
- Single images
- Image sequences (creates keyframes)
- Blender 4.3+ Grease Pencil v3 API
- Progress reporting

Uses PolyVector algorithm for high-quality vectorization with proper junction handling.
"""

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
    """Import line art image(s) as Grease Pencil strokes"""
    bl_idname = "gpencil.import_lineart"
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
        description="Background/foreground separation (0-255). Lower values detect more ink.",
        default=90,
        min=0,
        max=255,
    )
    
    # Stroke
    stroke_radius: FloatProperty(
        name="Stroke Radius",
        description="Radius of strokes",
        default=0.01,
        min=0.001,
        max=0.1,
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
        """Execute the import."""
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
        
        # Get or create GP object
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
        
        # Progress reporting via window manager
        wm = context.window_manager
        wm.progress_begin(0, total_files)
        
        try:
            for file_idx, filepath in enumerate(files):
                # Update progress
                wm.progress_update(file_idx)
                
                if not os.path.exists(filepath):
                    continue
                
                image = None
                try:
                    image = bpy.data.images.load(filepath)
                    width, height = image.size
                    channels = image.channels
                    
                    pixels = np.array(image.pixels[:]).reshape((height, width, channels))
                    
                    polylines = vectorization.process_image_to_polylines(
                        pixels,
                        threshold=self.threshold
                    )
                    
                    if len(polylines) > 0:
                        stroke_count = self._create_strokes_gpv3(
                            layer, frame_number, polylines, width, height
                        )
                        total_strokes += stroke_count
                    
                except Exception as e:
                    print(f"[GPAI Lineart] Error: {e}")
                
                finally:
                    if image:
                        bpy.data.images.remove(image)
                
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
            center_z = -(image_height * self.scale_factor) / 2
            
            positions = []
            for polyline in valid_polylines:
                for i in range(len(polyline)):
                    x = polyline[i, 0] if polyline.ndim == 2 else polyline[i][0]
                    y = polyline[i, 1] if polyline.ndim == 2 else polyline[i][1]
                    
                    scaled_x = float(x * self.scale_factor) - center_x
                    scaled_z = float(-(image_height - y) * self.scale_factor) - center_z
                    
                    positions.extend([scaled_x, 0.0, scaled_z])
            
            attrs = drawing.attributes
            if 'position' in attrs:
                attrs['position'].data.foreach_set('vector', positions)
                drawing.tag_positions_changed()
            
            if 'radius' in attrs:
                attrs['radius'].data.foreach_set('value', [self.stroke_radius] * total_points)
            
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
        
        box = layout.box()
        box.label(text="Stroke", icon='GREASEPENCIL')
        box.prop(self, "scale_factor")
        box.prop(self, "stroke_radius")
        box.prop(self, "target_layer")
        
        box = layout.box()
        box.label(text="Vectorization", icon='CURVE_DATA')
        box.prop(self, "threshold")
        
        box = layout.box()
        box.label(text="Image Sequence", icon='SEQUENCE')
        box.prop(self, "start_frame")
        box.prop(self, "frame_step")


def menu_func_import(self, context):
    self.layout.operator(
        GPENCIL_OT_import_lineart.bl_idname,
        text="Grease Pencil Line Art (.png, .jpg)"
    )


def register():
    bpy.utils.register_class(GPENCIL_OT_import_lineart)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(GPENCIL_OT_import_lineart)
