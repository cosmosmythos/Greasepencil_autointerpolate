#pragma once

#include <vector>
#include <optional>
#include <cmath>
#include <limits>

namespace ftpsc {

// 2D point. FTP-SC runs in 2D; 3D -> 2D projection happens at the Python boundary.
struct Vec2 {
   double x, y;

   Vec2() : x(0.0), y(0.0) {}
   Vec2(double x_, double y_) : x(x_), y(y_) {}

   Vec2 operator+(const Vec2 &other) const { return Vec2(x + other.x, y + other.y); }
   Vec2 operator-(const Vec2 &other) const { return Vec2(x - other.x, y - other.y); }
   Vec2 operator*(double s) const { return Vec2(x * s, y * s); }
   Vec2 operator/(double s) const { return Vec2(x / s, y / s); }

   double dot(const Vec2 &other) const { return x * other.x + y * other.y; }
   double length() const { return std::sqrt(x * x + y * y); }
   double length_squared() const { return x * x + y * y; }

   Vec2 normalized() const {
      double len = length();
      if (len < 1e-10) {
         return Vec2(0.0, 0.0);
      }
      return Vec2(x / len, y / len);
   }

   double distance_to(const Vec2 &other) const { return (*this - other).length(); }
};

// Stroke as polyline - ordered 2D points.
struct Stroke {
   std::vector<Vec2> points;

   mutable std::optional<Vec2> cached_centroid;
   mutable std::optional<double> cached_total_length;
   mutable std::optional<std::vector<double>> cached_position_along_stroke;

   Vec2 get_centroid() const {
      if (!cached_centroid) {
         if (points.empty()) {
            cached_centroid = Vec2(0.0, 0.0);
         } else {
            Vec2 sum(0.0, 0.0);
            for (const auto &p : points) {
               sum = sum + p;
            }
            cached_centroid = sum / static_cast<double>(points.size());
         }
      }
      return *cached_centroid;
   }

   double get_total_length() const {
      if (!cached_total_length) {
         double total = 0.0;
         for (size_t i = 1; i < points.size(); ++i) {
            total += points[i].distance_to(points[i - 1]);
         }
         cached_total_length = total;
      }
      return *cached_total_length;
   }

   // Kept for paper cross-ref: arc_length == total_length
   double get_arc_length() const { return get_total_length(); }

   // Position along stroke in [0,1] for each vertex. 0 at start, 1 at end (paper: arc parameter).
   const std::vector<double> &get_position_along_stroke() const {
      if (!cached_position_along_stroke) {
         cached_position_along_stroke = std::vector<double>();
         cached_position_along_stroke->reserve(points.size());
         if (points.empty()) {
            return *cached_position_along_stroke;
         }
         cached_position_along_stroke->push_back(0.0);
         double total = get_total_length();
         if (total < 1e-10) {
            for (size_t i = 1; i < points.size(); ++i) {
               cached_position_along_stroke->push_back(0.0);
            }
            return *cached_position_along_stroke;
         }
         double accumulated_length = 0.0;
         for (size_t i = 1; i < points.size(); ++i) {
            accumulated_length += points[i].distance_to(points[i - 1]);
            cached_position_along_stroke->push_back(accumulated_length / total);
         }
      }
      return *cached_position_along_stroke;
   }

   // Deprecated: paper term
   const std::vector<double> &get_arc_parameters() const { return get_position_along_stroke(); }

   Vec2 get_start_point() const { return points.empty() ? Vec2(0.0, 0.0) : points.front(); }
   Vec2 get_end_point() const { return points.empty() ? Vec2(0.0, 0.0) : points.back(); }
   bool is_valid() const { return points.size() >= 2; }

   void invalidate_cache() {
      cached_centroid.reset();
      cached_total_length.reset();
      cached_position_along_stroke.reset();
   }

   size_t size() const { return points.size(); }
};

inline Stroke create_stroke_from_coords(const double *coords, size_t num_points) {
   Stroke s;
   s.points.reserve(num_points);
   for (size_t i = 0; i < num_points; ++i) {
      s.points.emplace_back(coords[i * 2], coords[i * 2 + 1]);
   }
   return s;
}

template<typename ProjectFunc>
inline Stroke create_stroke_from_3d_coords(const double *coords, size_t num_points, ProjectFunc project_to_2d) {
   Stroke s;
   s.points.reserve(num_points);
   for (size_t i = 0; i < num_points; ++i) {
      double x = coords[i * 3];
      double y = coords[i * 3 + 1];
      double z = coords[i * 3 + 2];
      auto [x2d, y2d] = project_to_2d(x, y, z);
      s.points.emplace_back(x2d, y2d);
   }
   return s;
}

} // namespace ftpsc
