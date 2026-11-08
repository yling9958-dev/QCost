"""Render editable SVG with installed librsvg/Cairo, without new packages."""
import ctypes as ct
import ctypes.util
from pathlib import Path


class Rectangle(ct.Structure):
    _fields_ = [('x', ct.c_double), ('y', ct.c_double),
                ('width', ct.c_double), ('height', ct.c_double)]


def render(source, destination, width, height):
    rsvg = ct.CDLL(ctypes.util.find_library('rsvg-2'))
    cairo = ct.CDLL(ctypes.util.find_library('cairo'))
    gobject = ct.CDLL(ctypes.util.find_library('gobject-2.0'))
    rsvg.rsvg_handle_new_from_file.argtypes = [ct.c_char_p, ct.c_void_p]
    rsvg.rsvg_handle_new_from_file.restype = ct.c_void_p
    rsvg.rsvg_handle_render_document.argtypes = [ct.c_void_p, ct.c_void_p,
                                                ct.POINTER(Rectangle), ct.c_void_p]
    rsvg.rsvg_handle_render_document.restype = ct.c_int
    cairo.cairo_image_surface_create.argtypes = [ct.c_int, ct.c_int, ct.c_int]
    cairo.cairo_image_surface_create.restype = ct.c_void_p
    cairo.cairo_create.argtypes = [ct.c_void_p]
    cairo.cairo_create.restype = ct.c_void_p
    cairo.cairo_set_source_rgb.argtypes = [ct.c_void_p, ct.c_double, ct.c_double, ct.c_double]
    cairo.cairo_paint.argtypes = [ct.c_void_p]
    cairo.cairo_surface_write_to_png.argtypes = [ct.c_void_p, ct.c_char_p]
    cairo.cairo_surface_write_to_png.restype = ct.c_int
    cairo.cairo_destroy.argtypes = [ct.c_void_p]
    cairo.cairo_surface_destroy.argtypes = [ct.c_void_p]
    gobject.g_object_unref.argtypes = [ct.c_void_p]
    handle = rsvg.rsvg_handle_new_from_file(str(Path(source)).encode(), None)
    assert handle, f'SVG could not be opened: {source}'
    surface = cairo.cairo_image_surface_create(0, width, height)
    context = cairo.cairo_create(surface)
    try:
        cairo.cairo_set_source_rgb(context, 1., 1., 1.)
        cairo.cairo_paint(context)
        ok = rsvg.rsvg_handle_render_document(
            handle, context, ct.byref(Rectangle(0, 0, width, height)), None)
        assert ok, f'SVG could not be rendered: {source}'
        status = cairo.cairo_surface_write_to_png(surface, str(Path(destination)).encode())
        assert status == 0, f'Cairo PNG export status {status}'
    finally:
        cairo.cairo_destroy(context)
        cairo.cairo_surface_destroy(surface)
        gobject.g_object_unref(handle)
    return {'Backend': 'installed librsvg and Cairo', 'Status': 'PASS',
            'RenderPath': str(destination), 'Pixels': [width, height]}
