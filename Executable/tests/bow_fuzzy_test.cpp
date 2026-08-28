#include "../src/fuzzy_topology.h"
#include "../src/stroke.h"
#include "bow_data.h"
#include <cmath>
#include <iostream>
#include <iomanip>
#include <algorithm>

int main() {
   using namespace ftpsc;
   auto initial = bow_test::get_bow_frame1();
   auto target = bow_test::get_bow_frame14();

   std::cout << "Bow layer 0-10 normalized (viewport_view)\n";
   std::cout << "initial strokes: " << initial.size() << " target: " << target.size() << "\n";
   for (size_t i=0;i<initial.size();++i) std::cout << "  init " << i << " pts " << initial[i].size() << "\n";
   for (size_t i=0;i<target.size();++i) std::cout << "  targ " << i << " pts " << target[i].size() << "\n";

   double connection_dist = 0.5; // 0-10 space
   double max_connection_dist = 0.5;

   std::cout << std::fixed << std::setprecision(4);

   // Per-stroke alpha topology
   std::cout << "\n--- compute_alpha_topology at connection_dist=0.5 ---\n";
   for (size_t idx=0; idx<initial.size(); ++idx) {
      AlphaTopology top = compute_alpha_topology(initial[idx], initial, (int)idx, connection_dist);
      std::cout << "initial stroke " << idx << " topology size " << top.size() << " (alpha " << top.alpha_threshold << "): ";
      for (auto &pt: top.points) {
         std::cout << "[" << pt.stroke_index << " pos " << pt.position_along_stroke << " dist " << pt.distance_to_neighbor << "] ";
      }
      std::cout << "\n";
   }
   for (size_t idx=0; idx<target.size(); ++idx) {
      AlphaTopology top = compute_alpha_topology(target[idx], target, (int)idx, connection_dist);
      std::cout << "target stroke " << idx << " topology size " << top.size() << ": ";
      for (auto &pt: top.points) std::cout << "[" << pt.stroke_index << " pos " << pt.position_along_stroke << " dist " << pt.distance_to_neighbor << "] ";
      std::cout << "\n";
   }

   // Distance matrix for initial frame (mu)
   std::cout << "\n--- distance_to_stroke matrix initial (mu) ---\n";
   for (size_t i=0;i<initial.size();++i) {
      for (size_t j=0;j<initial.size();++j) if(i!=j) {
         double d = compute_distance_to_stroke(initial[i], initial[j]);
         if (d < 0.6) std::cout << "  mu init " << i << "->" << j << " = " << d << (d<=connection_dist?" [conn]":"") << "\n";
      }
   }

   // make_topologies_compatible for assumed 1-1 correspondence (0->0,1->1...)
   std::cout << "\n--- make_topologies_compatible for assumed pairs (0->0 etc) ---\n";
   for (size_t k=0;k<std::min(initial.size(), target.size());++k) {
      auto [top_initial, top_target] = make_topologies_compatible(initial[k], target[k], initial, target, (int)k, (int)k, max_connection_dist);
      std::cout << "pair " << k << "->" << k << " compatible? " << (top_initial.is_compatible_with(top_target)?"yes":"no")
                << " sizes " << top_initial.size() << "/" << top_target.size()
                << " alpha_used " << top_initial.alpha_threshold << "\n";
      if (top_initial.size()>0) {
         std::cout << "  init topo: ";
         for (auto &p: top_initial.points) std::cout << p.stroke_index << "@" << p.position_along_stroke << " ";
         std::cout << "\n  targ topo: ";
         for (auto &p: top_target.points) std::cout << p.stroke_index << "@" << p.position_along_stroke << " ";
         std::cout << "\n";
      }
   }

   // Test are_strokes_connected for a close pair vs far pair
   if (initial.size()>=3) {
      bool conn01 = are_strokes_connected(initial[0], initial[1], connection_dist);
      bool conn02 = are_strokes_connected(initial[0], initial[2], connection_dist);
      std::cout << "\nare_strokes_connected init 0-1 at 0.5: " << conn01 << "  0-2: " << conn02 << "\n";
   }

   // --- heap demo for seed 0->0 (plain) ---
   std::cout << "\n--- Stage1 CD heap for seed 0->0 (plain) ---\n";
   {
      int seed_initial = 0, seed_target = 0;
      auto [top_initial, top_target] = make_topologies_compatible(initial[seed_initial], target[seed_target], initial, target, seed_initial, seed_target, max_connection_dist);
      std::cout << "seed 0->0 topologies sizes " << top_initial.size() << "/" << top_target.size() << "\n";
      std::cout << "  initial neighbours along stroke 0: ";
      for (auto &pt: top_initial.points) std::cout << pt.stroke_index << "@" << std::fixed << std::setprecision(2) << pt.position_along_stroke << " ";
      std::cout << "\n  target neighbours along stroke 0: ";
      for (auto &pt: top_target.points) std::cout << pt.stroke_index << "@" << pt.position_along_stroke << " ";
      std::cout << "\n  candidate pairs (k paired):\n";
      struct HeapItem { int initial_idx, target_idx; double cost; };
      std::vector<HeapItem> heap;
      for (size_t k=0;k<top_initial.size();++k) {
         int candidate_initial = top_initial.points[k].stroke_index;
         int candidate_target = top_target.points[k].stroke_index;
         double position_initial = top_initial.points[k].position_along_stroke;
         double position_target = top_target.points[k].position_along_stroke;
         double tie_cost = std::abs(position_initial - position_target);
         double priority = -tie_cost;
         heap.push_back({candidate_initial, candidate_target, priority});
         std::cout << "    k=" << k << "  " << candidate_initial << "->" << candidate_target << "  tie " << tie_cost << " priority " << priority << "\n";
      }
      std::sort(heap.begin(), heap.end(), [](auto &a, auto &b){ return a.cost > b.cost; });
      std::cout << "  heap sorted (best position match first):\n";
      for (auto &h: heap) std::cout << "    " << h.initial_idx << "->" << h.target_idx << "  priority " << h.cost << "\n";
      std::cout << "  -> SP would pop " << heap[0].initial_idx << "->" << heap[0].target_idx << " as next seed\n";
   }
   // hub seed 4->4
   std::cout << "\n--- Stage1 CD heap for seed 4->4 hub (plain, no shape) ---\n";
   {
      int seed_initial = 4, seed_target = 4;
      auto [top_initial, top_target] = make_topologies_compatible(initial[seed_initial], target[seed_target], initial, target, seed_initial, seed_target, max_connection_dist);
      std::cout << "seed 4->4 topologies sizes " << top_initial.size() << "/" << top_target.size() << "\n";
      std::cout << "  initial order: ";
      for (auto &pt: top_initial.points) std::cout << pt.stroke_index << "@" << pt.position_along_stroke << " ";
      std::cout << "\n  target order: ";
      for (auto &pt: top_target.points) std::cout << pt.stroke_index << "@" << pt.position_along_stroke << " ";
      std::cout << "\n  candidate pairs k=0..5 (scrambled order):\n";
      for (size_t k=0;k<top_initial.size();++k) {
         int ci = top_initial.points[k].stroke_index;
         int ct = top_target.points[k].stroke_index;
         double position_initial = top_initial.points[k].position_along_stroke;
         double position_target = top_target.points[k].position_along_stroke;
         double tie = std::abs(position_initial - position_target);
         std::cout << "    k=" << k << "  " << ci << "->" << ct;
         if ((ci==1 && ct==6) || (ci==3 && ct==5)) std::cout << "  <- scrambled";
         std::cout << "  tie " << tie << "\n";
      }
   }

   std::cout << "\nDone. Current C++ fuzzy_topology (no wheel) tested on bow 7 strokes 0-10.\n";
   return 0;
}
