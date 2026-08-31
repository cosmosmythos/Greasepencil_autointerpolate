#include "bezier_fit.h"
#include <cmath>
#include <cstdlib>
#include <vector>
#include <algorithm>

// Faithful port of https://github.com/erich666/GraphicsGems/blob/master/gems/FitCurves.c
// by Philip J. Schneider, Graphics Gems (1990).
// 3D extension: V2* -> V3* (all ops on x,y,z), otherwise identical.
// MaxIterations=4, iterationError=error*4 kept verbatim (issue 23 fix).
// No arc-length map/find_t — ComputeMaxError uses direct BezierII at u (original).

namespace bezier_fit {

// --- V3 helpers (from GGVecLib.c, V2* extended to 3D) ---
static double V3SquaredLength(const Vec3 *a) { return a->x*a->x + a->y*a->y + a->z*a->z; }
static double V3Length(const Vec3 *a) { return std::sqrt(V3SquaredLength(a)); }
static Vec3* V3Normalize(Vec3 *v) {
   double len = V3Length(v);
   if (len != 0) { v->x/=len; v->y/=len; v->z/=len; }
   return v;
}
static Vec3* V3Add(const Vec3 *a, const Vec3 *b, Vec3 *c) { c->x=a->x+b->x; c->y=a->y+b->y; c->z=a->z+b->z; return c; }
static Vec3* V3Sub(const Vec3 *a, const Vec3 *b, Vec3 *c) { c->x=a->x-b->x; c->y=a->y-b->y; c->z=a->z-b->z; return c; }
static Vec3 V3SubII(Vec3 a, Vec3 b) { return {a.x-b.x, a.y-b.y, a.z-b.z}; }
static Vec3 V3AddII(Vec3 a, Vec3 b) { return {a.x+b.x, a.y+b.y, a.z+b.z}; }
static Vec3 V3ScaleIII(Vec3 v, double s) { return {v.x*s, v.y*s, v.z*s}; }
static double V3Dot(const Vec3 *a, const Vec3 *b) { return a->x*b->x + a->y*b->y + a->z*b->z; }
static Vec3* V3Negate(Vec3 *v) { v->x=-v->x; v->y=-v->y; v->z=-v->z; return v; }
static Vec3* V3Scale(Vec3 *v, double s) { v->x*=s; v->y*=s; v->z*=s; return v; }
static double V3DistanceBetween2Points(const Vec3 *a, const Vec3 *b) {
   double dx=a->x-b->x, dy=a->y-b->y, dz=a->z-b->z;
   return std::sqrt(dx*dx+dy*dy+dz*dz);
}

// --- Bezier helpers (verbatim) ---
static double B0(double u) { double t=1-u; return t*t*t; }
static double B1(double u) { double t=1-u; return 3*u*t*t; }
static double B2(double u) { double t=1-u; return 3*u*u*t; }
static double B3(double u) { return u*u*u; }

static Vec3 BezierII(int degree, Vec3 *V, double t) {
   int i,j;
   Vec3 Q;
   Vec3 *Vtemp = (Vec3*)std::malloc((unsigned)((degree+1)*sizeof(Vec3)));
   for (i=0;i<=degree;i++) Vtemp[i]=V[i];
   for (i=1;i<=degree;i++) for (j=0;j<=degree-i;j++) {
      Vtemp[j].x = (1.0-t)*Vtemp[j].x + t*Vtemp[j+1].x;
      Vtemp[j].y = (1.0-t)*Vtemp[j].y + t*Vtemp[j+1].y;
      Vtemp[j].z = (1.0-t)*Vtemp[j].z + t*Vtemp[j+1].z;
   }
   Q=Vtemp[0];
   std::free(Vtemp);
   return Q;
}

// Forward decls — plain names, same logic as FitCurves.c
static void FitCubic(const Vec3 *points, int start_index, int end_index, Vec3 left_tangent, Vec3 right_tangent, double max_allowed_error, std::vector<BezierCurve> &fitted_curves);
static Vec3* GenerateBezier(const Vec3 *points, int start_index, int end_index, double *stroke_t, Vec3 left_tangent, Vec3 right_tangent);
static double* Reparameterize(const Vec3 *points, int start_index, int end_index, double *stroke_t, Vec3 *curve);
static double NewtonRaphsonRootFind(Vec3 *curve, Vec3 stroke_point, double t_guess);
static Vec3 ComputeLeftTangent(const Vec3 *points, int start_index);
static Vec3 ComputeRightTangent(const Vec3 *points, int end_index);
static Vec3 ComputeCenterTangent(const Vec3 *points, int middle_index);
static double* EdgeLengthParameterize(const Vec3 *points, int start_index, int end_index);
static double ComputeMaxError(const Vec3 *points, int start_index, int end_index, Vec3 *curve, double *stroke_t, int *worst_point_index);

// ---- Step 1: tangents — which way is the pen going? ----
// left_tangent = tiny vector from first dot to second dot, made length 1
static Vec3 ComputeLeftTangent(const Vec3 *points, int start_index) {
   Vec3 start_segment = V3SubII(points[start_index+1], points[start_index]); // tiny segment: point[1] - point[0]
   V3Normalize(&start_segment); // squish/stretch to length 1 — keeps direction only
   return start_segment; // This means: unit direction at start
}
// right_tangent = tiny vector from second-last dot to last dot, but flipped to point inward
static Vec3 ComputeRightTangent(const Vec3 *points, int end_index) {
   Vec3 end_segment = V3SubII(points[end_index-1], points[end_index]); // tiny segment: point[n-2] - point[n-1]
   V3Normalize(&end_segment); // make it length 1
   return end_segment; // This means: unit direction at end
}
// center_tangent = average of two neighbour vectors at a split — keeps the join smooth
static Vec3 ComputeCenterTangent(const Vec3 *points, int middle_index) {
   Vec3 incoming = V3SubII(points[middle_index-1], points[middle_index]); // vector into the middle dot
   Vec3 outgoing = V3SubII(points[middle_index], points[middle_index+1]); // vector out of it
   Vec3 averaged = {(incoming.x+outgoing.x)/2.0, (incoming.y+outgoing.y)/2.0, (incoming.z+outgoing.z)/2.0}; // (V1+V2)/2
   V3Normalize(&averaged); // make it length 1
   return averaged; // This means: smooth direction through the split point
}

// ---- Step 2: edge lengths — how far along the stroke is each dot? ----
// edge = straight stick between two neighbour dots on the stroke. total = all sticks end-to-end.
// This returns 0..1 for each dot: walked distance along stroke / total stroke length.
static double* EdgeLengthParameterize(const Vec3 *points, int start_index, int end_index) {
   int i;
   double *stroke_t = (double*)std::malloc((unsigned)(end_index-start_index+1)*sizeof(double));
   stroke_t[0]=0.0; // start of stroke = 0
   for (i=start_index+1;i<=end_index;i++) stroke_t[i-start_index]=stroke_t[i-start_index-1]+V3DistanceBetween2Points(&points[i], &points[i-1]); // add each edge
   for (i=start_index+1;i<=end_index;i++) stroke_t[i-start_index]=stroke_t[i-start_index]/stroke_t[end_index-start_index]; // squish total stroke to 1
   return stroke_t; // This means: 0 at start of stroke, 1 at end, in-between by real edge length
}

// ---- GenerateBezier — slide handles until best hug (least-squares) ----
static Vec3* GenerateBezier(const Vec3 *points, int start_index, int end_index, double *stroke_t, Vec3 left_tangent, Vec3 right_tangent) {
   int i;
   int point_count = end_index - start_index + 1;
   std::vector<std::vector<Vec3>> handle_vectors(point_count, std::vector<Vec3>(2)); // This means: vectors along tangents scaled by Bernstein
   double C[2][2]={0}, X[2]={0};
   double det_C0_C1, det_C0_X, det_X_C1;
   double left_handle_dist, right_handle_dist; // This means: how far to slide handles out
   Vec3 gap;
   Vec3 *curve = (Vec3*)std::malloc(4*sizeof(Vec3));
   double straight_length, tiny;

   for (i=0;i<point_count;i++) {
      Vec3 left = left_tangent, right = right_tangent;
      V3Scale(&left, B1(stroke_t[i])); // scale left vector by Bernstein B1 at this stroke position
      V3Scale(&right, B2(stroke_t[i])); // scale right vector by B2
      handle_vectors[i][0]=left; handle_vectors[i][1]=right;
   }
   C[0][0]=C[0][1]=C[1][0]=C[1][1]=X[0]=X[1]=0;
   for (i=0;i<point_count;i++) {
      C[0][0]+=V3Dot(&handle_vectors[i][0],&handle_vectors[i][0]);
      C[0][1]+=V3Dot(&handle_vectors[i][0],&handle_vectors[i][1]);
      C[1][0]=C[0][1];
      C[1][1]+=V3Dot(&handle_vectors[i][1],&handle_vectors[i][1]);
      gap = V3SubII(points[start_index+i],
         V3AddII(V3ScaleIII(points[start_index], B0(stroke_t[i])),
         V3AddII(V3ScaleIII(points[start_index], B1(stroke_t[i])),
         V3AddII(V3ScaleIII(points[end_index], B2(stroke_t[i])),
                 V3ScaleIII(points[end_index], B3(stroke_t[i]))))));
      X[0]+=V3Dot(&handle_vectors[i][0],&gap);
      X[1]+=V3Dot(&handle_vectors[i][1],&gap);
   }
   det_C0_C1=C[0][0]*C[1][1]-C[1][0]*C[0][1];
   det_C0_X =C[0][0]*X[1]-C[1][0]*X[0];
   det_X_C1 =X[0]*C[1][1]-X[1]*C[0][1];
   left_handle_dist = (det_C0_C1==0)?0:det_X_C1/det_C0_C1; // This means: distance to slide left handle
   right_handle_dist = (det_C0_C1==0)?0:det_C0_X/det_C0_C1; // This means: distance to slide right handle
   straight_length=V3DistanceBetween2Points(&points[end_index],&points[start_index]);
   tiny=1.0e-6*straight_length;
   if (left_handle_dist<tiny || right_handle_dist<tiny) { // fallback if handles too short/negative
      double third=straight_length/3.0;
      curve[0]=points[start_index]; curve[3]=points[end_index];
      Vec3 left = left_tangent, right = right_tangent;
      V3Scale(&left,third); V3Scale(&right,third);
      V3Add(&curve[0],&left,&curve[1]); // c1 = p0 + left_tangent * third
      V3Add(&curve[3],&right,&curve[2]); // c2 = p1 + right_tangent * third
      return curve;
   }
   curve[0]=points[start_index]; curve[3]=points[end_index];
   Vec3 left = left_tangent, right = right_tangent;
   V3Scale(&left,left_handle_dist); V3Scale(&right,right_handle_dist);
   V3Add(&curve[0],&left,&curve[1]); // c1 = p0 + left_tangent * left_handle_dist
   V3Add(&curve[3],&right,&curve[2]); // c2 = p1 + right_tangent * right_handle_dist
   return curve;
}

// ---- Reparameterize — re-aim each stroke point's t to be more perpendicular ----
static double* Reparameterize(const Vec3 *points, int start_index, int end_index, double *stroke_t, Vec3 *curve) {
   int point_count=end_index-start_index+1, i;
   double *refined_stroke_t=(double*)std::malloc(point_count*sizeof(double));
   for (i=start_index;i<=end_index;i++) refined_stroke_t[i-start_index]=NewtonRaphsonRootFind(curve,points[i],stroke_t[i-start_index]);
   return refined_stroke_t;
}

// ---- NewtonRaphsonRootFind — nudge one stroke point's t toward closest point on curve ----
static double NewtonRaphsonRootFind(Vec3 *curve, Vec3 stroke_point, double stroke_t) {
   double along, across;
   Vec3 curve_tangent[3], curve_curvature[2];
   Vec3 point_on_curve, tangent_at_t, curvature_at_t;
   double better_t;
   int i;
   point_on_curve=BezierII(3,curve,stroke_t);
   for (i=0;i<=2;i++) { curve_tangent[i].x=(curve[i+1].x-curve[i].x)*3.0; curve_tangent[i].y=(curve[i+1].y-curve[i].y)*3.0; curve_tangent[i].z=(curve[i+1].z-curve[i].z)*3.0; }
   for (i=0;i<=1;i++) { curve_curvature[i].x=(curve_tangent[i+1].x-curve_tangent[i].x)*2.0; curve_curvature[i].y=(curve_tangent[i+1].y-curve_tangent[i].y)*2.0; curve_curvature[i].z=(curve_tangent[i+1].z-curve_tangent[i].z)*2.0; }
   tangent_at_t=BezierII(2,curve_tangent,stroke_t); curvature_at_t=BezierII(1,curve_curvature,stroke_t);
   along = (point_on_curve.x-stroke_point.x)*(tangent_at_t.x) + (point_on_curve.y-stroke_point.y)*(tangent_at_t.y) + (point_on_curve.z-stroke_point.z)*(tangent_at_t.z);
   across = (tangent_at_t.x)*(tangent_at_t.x)+(tangent_at_t.y)*(tangent_at_t.y)+(tangent_at_t.z)*(tangent_at_t.z)
               + (point_on_curve.x-stroke_point.x)*(curvature_at_t.x)+(point_on_curve.y-stroke_point.y)*(curvature_at_t.y)+(point_on_curve.z-stroke_point.z)*(curvature_at_t.z);
   if (across==0) return stroke_t;
   better_t=stroke_t-(along/across);
   return better_t;
}

// ---- ComputeMaxError — find the stroke point farthest from the curve ----
static double ComputeMaxError(const Vec3 *points, int start_index, int end_index, Vec3 *curve, double *stroke_t, int *worst_point_index) {
   int i;
   double biggest_gap=0, gap;
   Vec3 curve_point;
   Vec3 to_point;
   *worst_point_index=(end_index-start_index+1)/2;
   for (i=start_index+1;i<end_index;i++) {
      curve_point=BezierII(3,curve,stroke_t[i-start_index]);
      V3Sub(&curve_point,&points[i],&to_point);
      gap=V3SquaredLength(&to_point);
      if (gap>=biggest_gap) { biggest_gap=gap; *worst_point_index=i; }
   }
   return biggest_gap;
}

// ---- FitCubic — tries one Bezier, checks error, iterates or splits ----
// This is the heart: same logic as FitCubic in FitCurves.c, just plain names
static void FitCubic(const Vec3 *points, int start_index, int end_index, Vec3 left_tangent, Vec3 right_tangent, double max_allowed_error, std::vector<BezierCurve> &fitted_curves) {
   Vec3 *curve; // 4 points: p0,c1,c2,p1
   double *stroke_t, *refined_stroke_t; // This means: 0..1 how far along the stroke each dot sits
   double worst_gap; // biggest squared distance
   int worst_point_index, point_count;
   double try_again_threshold;
   int max_tries=4, i;
   Vec3 middle_tangent;

   try_again_threshold = max_allowed_error*4.0; // if gap < 4× allowed, try Newton tweaks before splitting
   point_count = end_index - start_index + 1;

   // Only 2 dots? heuristic: handles 1/3 of the straight distance out along tangents
   if (point_count==2) {
      double straight_dist = V3DistanceBetween2Points(&points[end_index], &points[start_index]) / 3.0;
      curve = (Vec3*)std::malloc(4*sizeof(Vec3));
      curve[0]=points[start_index]; curve[3]=points[end_index];
      Vec3 left_handle = left_tangent, right_handle = right_tangent;
      V3Scale(&left_handle, straight_dist); V3Scale(&right_handle, straight_dist);
      V3Add(&curve[0], &left_handle, &curve[1]); // c1 = p0 + left_tangent * dist
      V3Add(&curve[3], &right_handle, &curve[2]); // c2 = p1 + right_tangent * dist
      fitted_curves.push_back({curve[0],curve[1],curve[2],curve[3]});
      std::free(curve);
      return;
   }
   stroke_t = EdgeLengthParameterize(points, start_index, end_index); // This means: edge lengths → 0..1 for each dot
   curve = GenerateBezier(points, start_index, end_index, stroke_t, left_tangent, right_tangent); // This means: slide handles until best hug
   worst_gap = ComputeMaxError(points, start_index, end_index, curve, stroke_t, &worst_point_index);
   if (worst_gap < max_allowed_error) { // good enough — keep this one curve
      fitted_curves.push_back({curve[0],curve[1],curve[2],curve[3]});
      std::free(stroke_t); std::free(curve);
      return;
   }
   if (worst_gap < try_again_threshold) { // close — try re-aiming stroke positions with Newton
      for (i=0;i<max_tries;i++) {
         refined_stroke_t = Reparameterize(points, start_index, end_index, stroke_t, curve);
         std::free(curve);
         curve = GenerateBezier(points, start_index, end_index, refined_stroke_t, left_tangent, right_tangent);
         worst_gap = ComputeMaxError(points, start_index, end_index, curve, refined_stroke_t, &worst_point_index);
         if (worst_gap < max_allowed_error) {
            fitted_curves.push_back({curve[0],curve[1],curve[2],curve[3]});
            std::free(stroke_t); std::free(curve); std::free(refined_stroke_t);
            return;
         }
         std::free(stroke_t); stroke_t = refined_stroke_t;
      }
   }
   // still too wobbly — split at worst dot and fit each half
   std::free(stroke_t); std::free(curve);
   middle_tangent = ComputeCenterTangent(points, worst_point_index); // This means: smooth vector through the split dot
   FitCubic(points, start_index, worst_point_index, left_tangent, middle_tangent, max_allowed_error, fitted_curves);
   V3Negate(&middle_tangent); // flip vector for the other side
   FitCubic(points, worst_point_index, end_index, middle_tangent, right_tangent, max_allowed_error, fitted_curves);
}

// ---- Public entry — dedup then start the recursion ----
std::vector<BezierCurve> fit_curve(const std::vector<Vec3> &input_points, double max_allowed_error) {
   if (input_points.size()<2) return {};
   // remove exact duplicate dots in a row — like JS filter `val === points[i-1][j]`
   std::vector<Vec3> clean_points;
   clean_points.reserve(input_points.size());
   clean_points.push_back(input_points[0]);
   for (size_t i=1;i<input_points.size();++i) {
      const Vec3 &next = input_points[i], &prev = clean_points.back();
      if (std::abs(next.x-prev.x)>1e-9 || std::abs(next.y-prev.y)>1e-9 || std::abs(next.z-prev.z)>1e-9) clean_points.push_back(next);
   }
   if (clean_points.size()<2) return {};
   int point_count = (int)clean_points.size();
   Vec3 *ordered_points = (Vec3*)std::malloc(point_count*sizeof(Vec3));
   for (int i=0;i<point_count;i++) ordered_points[i]=clean_points[i];
   Vec3 start_vector = ComputeLeftTangent(ordered_points, 0); // tiny vector at start: point[1] - point[0], length 1
   Vec3 end_vector   = ComputeRightTangent(ordered_points, point_count-1); // tiny vector at end: point[n-2] - point[n-1], length 1
   if (V3SquaredLength(&start_vector)==0) start_vector={1,0,0}; // fallback if dots stacked
   if (V3SquaredLength(&end_vector)==0)   end_vector={1,0,0};
   std::vector<BezierCurve> fitted_curves;
   FitCubic(ordered_points, 0, point_count-1, start_vector, end_vector, max_allowed_error, fitted_curves);
   std::free(ordered_points);
   return fitted_curves;
}

std::vector<float> fit_curve_flat(const float *data, size_t count, double max_error) {
   if (!data || count<6 || count%3!=0) return {};
   size_t n=count/3;
   std::vector<Vec3> pts; pts.reserve(n);
   for (size_t i=0;i<n;i++) pts.push_back({(double)data[i*3],(double)data[i*3+1],(double)data[i*3+2]});
   auto curves=fit_curve(pts,max_error);
   std::vector<float> flat; flat.reserve(curves.size()*12);
   for (auto &c:curves) {
      flat.push_back((float)c.p0.x); flat.push_back((float)c.p0.y); flat.push_back((float)c.p0.z);
      flat.push_back((float)c.c1.x); flat.push_back((float)c.c1.y); flat.push_back((float)c.c1.z);
      flat.push_back((float)c.c2.x); flat.push_back((float)c.c2.y); flat.push_back((float)c.c2.z);
      flat.push_back((float)c.p1.x); flat.push_back((float)c.p1.y); flat.push_back((float)c.p1.z);
   }
   return flat;
}

} // namespace bezier_fit
