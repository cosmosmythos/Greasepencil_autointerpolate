# Decisive Matching Plan and Research Findings

This document summarizes the core findings from our deep research into relational structure matching, seed selection, and error propagation, concluding with a decisive implementation plan to enhance the C++ matching engine.

## Contents
- [1. Research Findings and Heuristic Pitfalls](#1-research-findings-and-heuristic-pitfalls)
- [2. Comparative Analysis of Matching Paradigms](#2-comparative-analysis-of-matching-paradigms)
- [3. The Decisive Implementation Plan](#3-the-decisive-implementation-plan)

---

## 1. Research Findings and Heuristic Pitfalls

The fundamental problem with incremental greedy matching algorithms (like FTP-SC's Stage 1) is **irreversible cascading error (drift)**. If the initial seed choice is incorrect, the topological neighborhood context for neighboring nodes becomes corrupted. This propagates errors exponentially across the structure.

### Flaws in Current Auto-Seeding Heuristics:
* **Largest Topology Size:** Symmetrical or high-density regions (hubs) have identical local neighbor counts. Choosing the "biggest" topology frequently picks the most ambiguous node, resulting in early mismatches.
* **Centroid + Along-Stroke Proximity (Tie/Centroid):** Assumes coordinates are already globally registered. Any significant translation, rotation, scaling, or deformation renders centroid distance misleading, leading to poor auto-seed choices.

---

## 2. Comparative Analysis of Matching Paradigms

To establish a robust alternative, we evaluated four major paradigms from graph matching, point set registration, and computer vision:

### 2.1. Consensus-based Seeding (RANSAC)
* **Concept:** Generate $K$ candidate seeds, run parallel greedy walks, and select the final match matrix that maximizes a global adjacency consistency score.
* **Strengths:** High resilience to outlier seeds.
* **Weaknesses:** High computational overhead ($O(K \cdot N^2)$ time), scaling poorly for real-time applications.

### 2.2. Global Spectral Matching / Projected Power Methods (PPM)
* **Concept:** Compute adjacency/association matrix eigenvectors to find global matching confidences, projecting them onto a discrete assignment matrix.
* **Strengths:** Integrates global topology constraints in a single step; very fast.
* **Weaknesses:** Fails under structural noise (node deletion/addition) and exhibits sign ambiguity in symmetric graphs.

### 2.3. Belief Propagation (MRF-based)
* **Concept:** Loopy message passing between neighboring nodes over a Markov Random Field to reach consensus.
* **Strengths:** Jointly optimizes local attributes and global pairwise relations; robust to local deformations.
* **Weaknesses:** Highly complex ($O(N^2 \cdot \text{deg})$); not guaranteed to converge on graphs with loops.

### 2.4. Hierarchical (Coarse-to-Fine)
* **Concept:** Partition the graph into high-level clusters (super-vertices), match the clusters, and match individual nodes locally inside matched clusters.
* **Strengths:** Reduces search space and prevents cross-boundary error propagation.
* **Weaknesses:** Fails completely if deformations cause the clustering algorithm to group nodes inconsistently between keyframes.

---

## 3. The Decisive Implementation Plan

To build a robust, performant C++ matching engine, we recommend a hybrid approach combining **Inline Seed Initialization** with **Integer Projected Fixed Point (IPFP) Global Refinement**.

```
               [Manual Seeds / Hints]
                         │
                         ▼
        ┌──────────────────────────────────┐
        │  Stage 1: Inline Greedy Match    │ ◄── Manual seeds populate heap at
        │  (Heap initialized at step 0     │     step 0 with user seeds)                │
        └────────────────┬─────────────────┘
                         │
                         ▼
        ┌──────────────────────────────────┐
        │  Stage 2: IPFP Global Solver     │ ◄── Continuous matrix updates
        │  (Refines matches globally via   │     eliminate local drift errors
        │  QAP alignment; no greedy walk)  │
        └────────────────┬─────────────────┘
                         │
                         ▼
                 [Final Alignment]
```

### Action Item 1: Inline Seed Initialization (Stage 1 Core Fix)
Refactor Stage 1 (`run_stage_one`) in the C++ engine to accept manual seeds directly.
* **Mechanism:** Push the user-provided manual seeds into the greedy matching heap at step 0 with infinite priority.
* **Why:** This forces the greedy propagation walk to start *exclusively* from correct, trusted anchors, ensuring neighboring candidates are evaluated using correct topological context. This immediately eliminates the topological contradictions introduced by post-merging.

### Action Item 2: IPFP Global Refinement (Stage 2 Core Fix)
Replace Stage 2's heuristic neighborhood competition with an **IPFP solver**.
* **Mechanism:** Formulate the matching as a Quadratic Assignment Problem (QAP) maximizing $\mathbf{x}^T \mathbf{W} \mathbf{x}$. Initialize with manual seeds. Iteratively perform continuous power iterations ($A X B^T$) and discrete assignments (greedy/Hungarian projections) until convergence.
* **Why:** IPFP is a mathematically rigorous global solver that does not suffer from greedy drift, does not require training an AI model, and converges to a stable local maximum in milliseconds using basic matrix math (via the project's Eigen3 dependency).
