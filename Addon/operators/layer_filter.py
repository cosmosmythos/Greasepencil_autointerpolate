"""
Layer Filter Popup
Allows users to select which layers should be interpolated.
Stores data on the GP data object since layers don't support IDProperties.
"""

import bpy
import json
from bpy.types import Operator


# Custom property key on GP data object
LAYER_FILTER_KEY = "gpai_layer_filter"


def _get_layer_filter_data(gp_data):
    """Get the layer filter dict from GP data."""
    if LAYER_FILTER_KEY in gp_data:
        try:
            return json.loads(gp_data[LAYER_FILTER_KEY])
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _set_layer_filter_data(gp_data, data):
    """Save the layer filter dict to GP data."""
    gp_data[LAYER_FILTER_KEY] = json.dumps(data)


def should_interpolate_layer(layer):
    """Check if a layer should be interpolated. Defaults to True."""
    # Get the GP data from the layer's id_data
    gp_data = layer.id_data
    if gp_data is None:
        return True
    
    filter_data = _get_layer_filter_data(gp_data)
    # Use layer name as key
    return filter_data.get(layer.name, True)


def set_layer_interpolate(gp_data, layer_name, value):
    """Set whether a layer should be interpolated."""
    filter_data = _get_layer_filter_data(gp_data)
    filter_data[layer_name] = value
    _set_layer_filter_data(gp_data, filter_data)


class GP_OT_LayerFilterPopup(Operator):
    """Select which layers to interpolate"""
    bl_idname = "gp.layer_filter_popup"
    bl_label = "Layer Interpolation"
    bl_description = "Select which layers to include in interpolation"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'GREASEPENCIL' and
                context.scene.gp_interpolation_enabled)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=250)

    def draw(self, context):
        layout = self.layout
        gp_obj = context.active_object
        
        if not gp_obj or not gp_obj.data.layers:
            layout.label(text="No layers found")
            return
        
        col = layout.column(align=True)
        
        for layer in gp_obj.data.layers:
            row = col.row(align=True)
            
            # Get current value (default True)
            is_enabled = should_interpolate_layer(layer)
            
            # Create a checkbox-like toggle
            icon = 'CHECKBOX_HLT' if is_enabled else 'CHECKBOX_DEHLT'
            op = row.operator("gp.toggle_layer_interpolate", text=layer.name, icon=icon, emboss=False)
            op.layer_name = layer.name

    def execute(self, context):
        # Rebuild cache to apply filter changes
        from ..core import cache
        gp_obj = context.active_object
        if gp_obj and context.scene.gp_interpolation_enabled:
            cache.clear(gp_obj.name)
            cache.build(gp_obj)
        return {'FINISHED'}


class GP_OT_ToggleLayerInterpolate(Operator):
    """Toggle layer interpolation on/off"""
    bl_idname = "gp.toggle_layer_interpolate"
    bl_label = "Toggle Layer"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    
    layer_name: bpy.props.StringProperty()

    def execute(self, context):
        gp_obj = context.active_object
        if not gp_obj:
            return {'CANCELLED'}
        
        layer = gp_obj.data.layers.get(self.layer_name)
        if not layer:
            return {'CANCELLED'}
        
        # Toggle the value
        current = should_interpolate_layer(layer)
        set_layer_interpolate(gp_obj.data, self.layer_name, not current)
        
        # Force UI redraw
        context.area.tag_redraw()
        
        return {'FINISHED'}


def register():
    bpy.utils.register_class(GP_OT_LayerFilterPopup)
    bpy.utils.register_class(GP_OT_ToggleLayerInterpolate)


def unregister():
    bpy.utils.unregister_class(GP_OT_ToggleLayerInterpolate)
    bpy.utils.unregister_class(GP_OT_LayerFilterPopup)
