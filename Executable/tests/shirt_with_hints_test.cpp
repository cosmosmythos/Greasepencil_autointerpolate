#include "../src/fuzzy_topology.h"
#include "../src/stroke.h"
#include "../src/stroke_matcher.h"
#include "shirt_data.h"
#include <cmath>
#include <iostream>
#include <iomanip>
#include <algorithm>
#include <set>
#include <vector>

static double direction_angle_diff(const ftpsc::Stroke &a, const ftpsc::Stroke &b) {
   ftpsc::Vec2 dir_a = a.get_end_point() - a.get_start_point();
   ftpsc::Vec2 dir_b = b.get_end_point() - b.get_start_point();
   double len_a = dir_a.length();
   double len_b = dir_b.length();
   if (len_a < 1e-9 || len_b < 1e-9) return 0.0;
   ftpsc::Vec2 norm_a = dir_a / len_a;
   ftpsc::Vec2 norm_b = dir_b / len_b;
   double dot = std::max(-1.0, std::min(1.0, norm_a.dot(norm_b)));
   return std::acos(dot);
}
static double length_ratio_cost(const ftpsc::Stroke &a, const ftpsc::Stroke &b) {
   double len_a = a.get_total_length();
   double len_b = b.get_total_length();
   if (len_a < 1e-9 && len_b < 1e-9) return 0.0;
   double max_len = std::max(len_a, len_b);
   if (max_len < 1e-9) return 0.0;
   return std::abs(len_a - len_b) / max_len;
}
int main() {
   using namespace ftpsc;
   auto initial = shirt_test::get_shirt_frame1();
   auto target = shirt_test::get_shirt_frame14();
   double max_connection_dist = 0.5;
   std::cout << "Shirt hints test — topology-only + direction/centroid (no shape)\\n";
   std::cout << "initial 40 target 40\\n\\n";
   std::cout << "--- Seed scoring: old max-size vs new centroid+tie+direction ---\\n";
   struct SeedScore { int i,j; size_t sz; double avg_tie; double centroid_dist; double angle; double len_ratio; double score_new; };
   std::vector<SeedScore> candidates;
   for (size_t i=0;i<initial.size();++i) {
      for (size_t j=0;j<target.size();++j) {
         auto pair_top = make_topologies_compatible(initial[i], target[j], initial, target, (int)i, (int)j, max_connection_dist);
         auto &ti = pair_top.first;
         auto &tt = pair_top.second;
         if (!ti.is_compatible_with(tt) || ti.size()==0) continue;
         double avg_tie=0;
         for (size_t k=0;k<ti.size();++k) avg_tie += std::abs(ti.points[k].position_along_stroke - tt.points[k].position_along_stroke);
         avg_tie /= ti.size();
         double centroid_dist = initial[i].get_centroid().distance_to(target[j].get_centroid());
         double angle = direction_angle_diff(initial[i], target[j]);
         double len_ratio = length_ratio_cost(initial[i], target[j]);
         double score_new = avg_tie + 0.2*centroid_dist + 0.3*angle + 0.1*len_ratio;
         candidates.push_back({(int)i,(int)j, ti.size(), avg_tie, centroid_dist, angle, len_ratio, score_new});
      }
   }
   std::sort(candidates.begin(), candidates.end(), [](auto &a, auto &b){ return a.sz > b.sz; });
   std::cout << "Top 5 by size (old):\\n";
   for (size_t k=0;k<std::min<size_t>(5,candidates.size());++k) {
      auto &c = candidates[k];
      std::cout << "  " << c.i << "->" << c.j << " size " << c.sz << " avg_tie " << std::setprecision(3) << c.avg_tie << " centroid " << c.centroid_dist << " angle " << c.angle << " len_ratio " << c.len_ratio << (c.i==c.j?" <- perfect":"") << "\\n";
   }
   std::sort(candidates.begin(), candidates.end(), [](auto &a, auto &b){ return a.score_new < b.score_new; });
   std::cout << "Top 5 by new score (avg_tie + 0.2*centroid + 0.3*angle + 0.1*len): smaller wins\\n";
   for (size_t k=0;k<std::min<size_t>(5,candidates.size());++k) {
      auto &c = candidates[k];
      std::cout << "  " << c.i << "->" << c.j << " size " << c.sz << " score " << c.score_new << " tie " << c.avg_tie << " centroid " << c.centroid_dist << " angle " << c.angle << (c.i==c.j?" <- perfect":"") << "\\n";
   }
   std::cout << "\\n--- Full match: auto (no hints) vs with 3 hints (0->0,4->4,23->23) ---\\n";
   StrokeMatcher matcher_auto;
   {
      MatcherConfig cfg; cfg.max_alpha = 0.5; cfg.coincident_threshold = 0.1;
      matcher_auto.set_config(cfg);
   }
   auto result_auto = matcher_auto.match(initial, target);
   int perfect_auto = 0;
   for (auto pr : result_auto.final_correspondence.matches) if (pr.first==pr.second) perfect_auto++;
   std::cout << "auto matched " << result_auto.num_matched << "/40 perfect a==b " << perfect_auto << " used_stage2 " << result_auto.used_stage_two << "\\n";
   std::vector<std::pair<int,int>> hints;
   hints = {{0,0},{4,4},{23,23}};
   auto result_hints = matcher_auto.match_with_seeds(initial, target, hints);
   int perfect_hints = 0;
   for (auto pr : result_hints.final_correspondence.matches) if (pr.first==pr.second) perfect_hints++;
   std::cout << "with 3 hints (0,4,23) matched " << result_hints.num_matched << "/40 perfect " << perfect_hints << "\\n";
   {
      std::set<int> matched_initial, matched_target;
      for (auto pr : result_hints.final_correspondence.matches) { matched_initial.insert(pr.first); matched_target.insert(pr.second); }
      std::cout << "  missing initial: "; for (int i=0;i<40;++i) if (!matched_initial.count(i)) std::cout << i << " ";
      std::cout << "\n  missing target: "; for (int j=0;j<40;++j) if (!matched_target.count(j)) std::cout << j << " ";
      std::cout << "\n  mismatched (first 10): "; int cnt=0; for (auto pr : result_hints.final_correspondence.matches) if (pr.first!=pr.second && cnt++<10) std::cout << pr.first << "->" << pr.second << " ";
      std::cout << "\n";
   }
    hints.clear();
    hints.push_back({0,0}); hints.push_back({4,4}); hints.push_back({11,11}); hints.push_back({23,23}); hints.push_back({31,31});
    auto result_hints5 = matcher_auto.match_with_seeds(initial, target, hints);
    int perfect_hints5 = 0;
    for (auto pr : result_hints5.final_correspondence.matches) if (pr.first==pr.second) perfect_hints5++;
    std::cout << "with 5 hints (0,4,11,23,31) matched " << result_hints5.num_matched << "/40 perfect " << perfect_hints5 << "\n";

    std::cout << "\n--- Greedy Hint Search ---\n";
    std::vector<std::pair<int, int>> search_hints;
    for (int iter = 0; iter < 40; ++iter) {
       auto res = matcher_auto.match_with_seeds(initial, target, search_hints);
       int perf = 0;
       int first_mismatch = -1;
       std::vector<int> match_target_for_initial(40, -1);
       for (auto pr : res.final_correspondence.matches) {
          if (pr.first >= 0 && pr.first < 40) {
             match_target_for_initial[pr.first] = pr.second;
          }
       }
       for (int i = 0; i < 40; ++i) {
          if (match_target_for_initial[i] == i) {
             perf++;
          } else if (first_mismatch == -1) {
             first_mismatch = i;
          }
       }
       std::cout << "Iteration " << iter << ": hints size " << search_hints.size() 
                 << " matched " << res.num_matched << "/40 perfect " << perf << "\n";
       if (perf == 40) {
          std::cout << "Perfect match achieved with " << search_hints.size() << " hints:\n  ";
          for (auto h : search_hints) std::cout << "{" << h.first << "," << h.second << "} ";
          std::cout << "\n";
          break;
       }
       if (first_mismatch != -1) {
          search_hints.push_back({first_mismatch, first_mismatch});
       } else {
          break;
       }
    }

    std::cout << "\nDone hints test (direction = start->end angle, not shape).\n";
    return 0;
 }
