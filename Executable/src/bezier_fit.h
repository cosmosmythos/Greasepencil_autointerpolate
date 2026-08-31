#pragma once
// Faithful C++ port of Philip J. Schneider's FitCurves.c
// from erich666/GraphicsGems (Graphics Gems, Academic Press 1990)
// Original 2D Point2/Vector2 extended to 3D Point3/Vector3 for Grease Pencil.
// Keep logic identical to FitCurves.c — no "biased" improvements.

#include <vector>

namespace bezier_fit {

struct Vec3 {
   double x, y, z;
   Vec3() : x(0), y(0), z(0) {}
   Vec3(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}
};

struct BezierCurve {
   Vec3 p0, c1, c2, p1;
};

// Entry: fit digitized points to piecewise cubic Beziers.
// points: polyline in BU (meters), error: squared tolerance.
std::vector<BezierCurve> fit_curve(const std::vector<Vec3> &points, double max_error);

// Flat float helpers for nanobind (no Vec3 exposure).
std::vector<float> fit_curve_flat(const float *data, size_t count, double max_error);

} // namespace bezier_fit
