#include "../src/fuzzy_topology.h"
#include "../src/stroke.h"
#include "shirt_data.h"
#include <cmath>
#include <iostream>
#include <iomanip>
#include <algorithm>

int main() {
   using namespace ftpsc;
   auto initial = shirt_test::get_shirt_frame1();
   auto target = shirt_test::get_shirt_frame14();

   std::cout << "Shirt layer 0-10 normalized (viewport_view) — perfect order 40 strokes\n";
   std::cout << "initial: " << initial.size() << " target: " << target.size() << "\n";
   double connection_dist = 0.5;
   double max_connection_dist = 0.5;
   std::cout << std::fixed << std::setprecision(4);

   // Per-stroke topology at 0.5
   std::cout << "\n--- compute_alpha_topology initial (frame1) at 0.5 ---\n";
   for (size_t idx=0; idx<initial.size(); ++idx) {
      AlphaTopology top = compute_alpha_topology(initial[idx], initial, (int)idx, connection_dist);
      std::cout << "init " << std::setw(2) << idx << " (" << std::setw(2) << initial[idx].size() << " pts) topo " << std::setw(2) << top.size() << ": ";
      for (auto &pt: top.points) std::cout << pt.stroke_index << "@" << std::setprecision(2) << pt.position_along_stroke << "(" << std::setprecision(3) << pt.distance_to_neighbor << ") ";
      std::cout << "\n";
   }
   std::cout << "\n--- target (frame14) at 0.5 ---\n";
   for (size_t idx=0; idx<target.size(); ++idx) {
      AlphaTopology top = compute_alpha_topology(target[idx], target, (int)idx, connection_dist);
      std::cout << "targ " << std::setw(2) << idx << " (" << std::setw(2) << target[idx].size() << " pts) topo " << std::setw(2) << top.size() << ": ";
      for (auto &pt: top.points) std::cout << pt.stroke_index << "@" << std::setprecision(2) << pt.position_along_stroke << "(" << std::setprecision(3) << pt.distance_to_neighbor << ") ";
      std::cout << "\n";
   }

   // Compatibility for assumed perfect 0->0 ..39->39
   std::cout << "\n--- make_topologies_compatible perfect pairs 0->0 ..39->39 ---\n";
   int compatible = 0, total = (int)std::min(initial.size(), target.size());
   for (int k=0;k<total;++k) {
      auto [top_initial, top_target] = make_topologies_compatible(initial[k], target[k], initial, target, k, k, max_connection_dist);
      bool ok = top_initial.is_compatible_with(top_target);
      if (ok) compatible++;
      std::cout << std::setw(2) << k << "->" << std::setw(2) << k << " " << (ok?"YES":" NO") << " " << top_initial.size() << "/" << top_target.size() << " alpha " << top_initial.alpha_threshold;
      if (top_initial.size()>0 && top_initial.size()<8) {
         std::cout << "  init[";
         for (auto &p: top_initial.points) std::cout << p.stroke_index << "@" << std::setprecision(2) << p.position_along_stroke << " ";
         std::cout << "] targ[";
         for (auto &p: top_target.points) std::cout << p.stroke_index << "@" << p.position_along_stroke << " ";
         std::cout << "]";
      } else if (top_initial.size()>=8) {
         std::cout << "  (large hub)";
      }
      std::cout << "\n";
   }
   std::cout << "\nCompatible: " << compatible << "/" << total << " (" << (100.0*compatible/total) << "%) at 0.5\n";

   // Closer inspection: which pairs failed?
   std::cout << "\n--- failures (if any) detail ---\n";
   for (int k=0;k<total;++k) {
      auto [top_initial, top_target] = make_topologies_compatible(initial[k], target[k], initial, target, k, k, max_connection_dist);
      if (!top_initial.is_compatible_with(top_target)) {
         std::cout << k << "->" << k << " sizes " << top_initial.size() << "/" << top_target.size() << "\n";
         std::cout << "  init: "; for (auto &p: top_initial.points) std::cout << p.stroke_index << " ";
         std::cout << "\n  targ: "; for (auto &p: top_target.points) std::cout << p.stroke_index << " ";
         std::cout << "\n";
      }
   }

   std::cout << "\n--- True Auto SI: centroid+tie (no shape) ---\n";
   struct SeedInfo { int i,j; size_t sz; double alpha; double avg_tie; double centroid_dist; double score; };
   std::vector<SeedInfo> all_seeds;
   for (size_t i=0;i<initial.size();++i) for (size_t j=0;j<target.size();++j) {
      auto [ti, tt] = make_topologies_compatible(initial[i], target[j], initial, target, (int)i, (int)j, max_connection_dist);
      if (!ti.is_compatible_with(tt) || ti.size()==0) continue;
      double avg_tie=0; for (size_t k=0;k<ti.size();++k) avg_tie += std::abs(ti.points[k].position_along_stroke - tt.points[k].position_along_stroke);
      avg_tie/=ti.size();
      double centroid_dist = initial[i].get_centroid().distance_to(target[j].get_centroid());
      double score = avg_tie + 0.2*centroid_dist;
      all_seeds.push_back({(int)i,(int)j,ti.size(), ti.alpha_threshold, avg_tie, centroid_dist, score});
   }
   std::sort(all_seeds.begin(), all_seeds.end(), [](auto &a, auto &b){ return a.score < b.score; });
   std::cout << "assumed 0->0 would be size 5 (centroid tie)\n";
   std::cout << "true auto checks 1600 compatible pairs, top 5 by centroid+tie (small score wins):\n";
   for (size_t k=0;k<std::min<size_t>(5, all_seeds.size());++k) {
      auto &s = all_seeds[k];
      std::cout << "  " << k+1 << ". " << s.i << "->" << s.j << " size " << s.sz << " avg_tie " << std::setprecision(3) << s.avg_tie << " centroid " << s.centroid_dist << " score " << s.score << (k==0?" <- auto picks this":"") << "\n";
   }
   int best_i=-1, best_j=-1; size_t best_sz=0;
   if (!all_seeds.empty()) { best_i=all_seeds[0].i; best_j=all_seeds[0].j; best_sz=all_seeds[0].sz; }
   std::cout << "auto picks " << best_i << "->" << best_j << " size " << best_sz << "  vs assumed 0->0 size 5\n";
   if (best_i!=-1) {
      auto [ti, tt] = make_topologies_compatible(initial[best_i], target[best_j], initial, target, best_i, best_j, max_connection_dist);
      std::cout << "  init topo: "; for (auto &p: ti.points) std::cout << p.stroke_index << "@" << p.position_along_stroke << " ";
      std::cout << "\n  targ topo: "; for (auto &p: tt.points) std::cout << p.stroke_index << "@" << p.position_along_stroke << " ";
      std::cout << "\n  candidates k paired (topology order, tie by pos diff):\n";
      for (size_t k=0;k<ti.size() && k<6; ++k) {
         int ci = ti.points[k].stroke_index;
         int ct = tt.points[k].stroke_index;
         double tie = std::abs(ti.points[k].position_along_stroke - tt.points[k].position_along_stroke);
         std::cout << "    k=" << k << " " << ci << "->" << ct << " tie " << tie << (ci==ct?" <- perfect":"") << "\n";
      }
      if (ti.size()>6) std::cout << "    ... (" << ti.size()-6 << " more)\n";
   }

   std::cout << "\nDone shirt 40 perfect order test (no shape, topology only).\n";
   return 0;
}
