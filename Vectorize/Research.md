# Research: Optimizing PolyVectorization

## Executive Summary
The target of reducing runtime from 28s to 5-10s (~3x-5x speedup) is **highly feasible** without changing the core mathematical results. The current implementation contains several inefficiencies, primarily in the optimization solver and redundant computations.

## Performance Analysis via Code Review

### 1. The Bottleneck: Singularity Refinement Loop
The core logic in `polyvector_core.cpp` (lines 331-354) contains a `do-while` loop that iteratively:
1.  Identifies singularities.
2.  Sets weights to zero at those locations.
3.  **Re-solves the entire linear system** (`optimizeByLinearSolve`).
4.  Re-traces roots.

This loop can run multiple times (potentially 5-10+). Inside `optimizeByLinearSolve`, the code:
-   **Re-builds** all matrices (`A`, `A2`, `L`) from scratch by iterating over all pixels ($O(N)$).
-   **Solves** the system using `Eigen::ConjugateGradient` (iterative solver).

### 2. Redundant Computations
In `optimizeByLinearSolve`:
-   `A2` (regularization energy) is constructed from `onesMatrix` and `g`. These inputs **do not change** during the singularity refinement loop. Currently, this matrix is rebuilt every single iteration.
-   `L` (Laplacian) is rebuilt every iteration. While weights change, the structure is static.

### 3. Solver Efficiency
The project uses `Eigen::ConjugateGradient`. For 2D grid-based problems (like this image vectorization):
-   Iterative solvers (CG) can be slow if the condition number is bad.
-   **Direct solvers** (like Simplicial Cholesky / LLT) are typically much faster for sparse 2D Laplacian-like systems up to a few million unknowns.

### 4. Parallelism Gaps
-   **Component Loop:** The code processes connected components serially (`for` loop in `polyvector_core.cpp` line 275). Components are mathematically independent and should be processed in parallel.
-   **Energy Calculation:** In `polynomial_energy.cpp`, the `#pragma omp parallel for` is commented out! This means the matrix construction is single-threaded.

---

## Proposed Optimizations

### Strategy 1: Parallelize Component Processing (High Impact)
The algorithm splits the image into connected components (lines 268-275 of `polyvector_core.cpp`).
-   **Action:** Change the `for` loop to `#pragma omp parallel for`.
-   **Benefit:** Linear speedup with the number of cores (e.g., on an 8-core machine, 4-6x speedup for images with many distinct strokes).

### Strategy 2: Switch to Direct Linear Solver (High Impact)
Replace `Eigen::ConjugateGradient` with `Eigen::SimplicialLLT` (LLT Cholesky factorization) or `Eigen::SimplicialLDLT`.
-   **Action:** Modify `Optimizer.cpp`.
-   **Benefit:** Direct solvers are often 10x faster than iterative ones for this class of problems. They also avoid convergence issues.

### Strategy 3: Optimize Matrix Construction (Medium Impact)
Refactor `optimizeByLinearSolve` to accept pre-computed matrices.
-   **Action:**
    1.  Compute `A2` (regularization matrix) **once** before the singularity loop.
    2.  Pass it into the solver function.
-   **Benefit:** Removes significant overhead from the inner loop.

### Strategy 4: Enable OpenMP for Energy (Low Effort)
-   **Action:** Uncomment `#pragma omp parallel for` in `polynomial_energy.cpp`.
-   **Note:** Requires careful handling of the `energies` vector or using OpenMP reduction/atomic adds, although the current logic writes to `energies[idx]` where `idx` is unique per pixel-index, so it might be thread-safe if `indices` are unique. *Investigation needed to ensure thread safety of sparse triplet generation.*
    -   *Better Approach:* Compute thread-local vectors of Triplets and merge them.

### Strategy 5: Factorization Update (Advanced)
If using a Direct Solver (Cholesky), when modifying weights (setting some diagonal entries to 0 or changing values slightly):
-   **Action:** Instead of re-factorizing from scratch, use rank-updates or simply benefit from the fact that the symbolic factorization (sparsity pattern) remains the same. Re-using the **Analysis Phase** of the solver saves time.

---

## Action Plan (Implementation)

1.  **Modify `polyvector_core.cpp`:**
    -   Add `#pragma omp parallel for` around the component processing loop.
    -   Move the `polynomial_energy_matrix` calculation for `A2` outside the singularity loop.
2.  **Modify `Optimizer.cpp`:**
    -   Change `Eigen::ConjugateGradient` to `Eigen::SimplicialLLT`.
    -   Add support for passing in pre-computed `A2`.
3.  **Modify `polynomial_energy.cpp`:**
    -   Safely re-enable OpenMP.

## Estimated Performance Gain
| Optimization | Est. Speedup | Complexity |
| :--- | :--- | :--- |
| Parallel Components | 2x - 6x | Low |
| Direct Solver (LLT) | 2x - 5x | Low |
| Precompute Matrices | 1.2x | Low |
| **Total Estimated** | **5x - 10x** | **Medium** |

This aligns with the goal of reducing execution time to 5-10 seconds.
