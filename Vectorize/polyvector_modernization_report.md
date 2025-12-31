# PolyVector Legacy Modernization Report

**Goal:** Identify opportunities to improve `polyvectorization-master` and `src_polyvector` using modern Eigen (3.4+), OpenCV (4.x+), and current C++ standards, based on the original algorithm principles.

## 1. Linear Algebra & Optimization (Eigen)

### Current State
*   **Linear Solver:** Uses `Eigen::ConjugateGradient` with a basic diagonal preconditioner (implicit) for the primary energy optimization in `Optimizer.cpp`.
*   **Non-Linear Solver:** Uses a bundled, seemingly older header-only `LBFGS` implementation in `src_polyvector/LBFGS/`.
*   **Sparse Operations:** Manual construction of sparse matrices via triplets.

### Modernization Opportunities (Eigen 3.4+)

#### A. Advanced Sparse Solvers
Eigen 3.4 introduced significant improvements for sparse solvers.
*   **SimplicialLDLT / SparseLU:** For 2D grid-based Laplacian problems (common in vectorization), direct solvers like `SimplicialLDLT` often outperform iterative `ConjugateGradient` in robustness and sometimes speed for moderate problem sizes (up to ~100k nodes).
    *   *Recommendation:* Benchmark switching `ConjugateGradient` to `SimplicialLDLT` for the `optimizeByLinearSolve` step. It avoids convergence tuning (`param.epsilon`).
*   **SuiteSparse / KLU Support:** Eigen 3.4 adds wrappers for KLU (part of SuiteSparse), optimized for circuit-like sparse matrices.
    *   *Relevance:* The "Frame Field" optimization creates highly structured sparse matrices. KLU might offer speedups if the default Eigen solvers bottleneck.

#### B. Modern L-BFGS
The bundled LBFGS code is functional but likely dated.
*   **`LBFGSpp` (Modern C++):** Transitioning to [LBFGSpp](https://github.com/yixuan/LBFGSpp) (header-only, Eigen-based) would bring C++11/14 standard compliance, better integration with Eigen structures, and potentially properly implemented Box constraints (L-BFGS-B) if future constraints are needed.

#### C. Vectorization & Parallelism
Eigen 3.3/3.4 massively improved internal vectorization (AVX/AVX2/AVX-512).
*   **Action:** Ensure the project compiles with AVX2 enabled (`/arch:AVX2` on MSVC, `-march=native` on GCC). This usually yields a "free" 20-30% speedup for dense matrix operations used in the local step of the optimization.

## 2. Image Processing & Parallelism (OpenCV)

### Current State
*   Uses `Sobel`, `morphologyEx`, `threshold`.
*   Uses standard single-threaded loops for many pixel-wise graph operations.

### Modernization Opportunities

#### A. `cv::parallel_for_` vs OpenMP
The codebase has some manual loops that could be parallelized.
*   **`cv::parallel_for_`:** Replacing manual `for` loops over independent components (e.g., processing connected components) with `cv::parallel_for_` allows utilizing OpenCV's internal thread pool (TBB/pthreads/WinConcurrency).
    *   *Target:* `calculateWeight` involves heavy pixel-wise matrix math. This is a prime candidate for `cv::parallel_for_`.

#### B. Graph API (G-API)
OpenCV 4.x introduced G-API, a graph-based execution model.
*   *Relevance:* The morphological pipeline (close -> open -> threshold) can be expressed as a G-API graph. G-API can fuse kernels to reduce memory bandwidth (keeping data in CPU cache), which is often the bottleneck in image morphology.

## 3. Algorithmic Improvements (Paper Context)

Based on *Bessmeltsev & Solomon (2019)*, the core bottleneck is usually the **Frame Field Smoothness** optimization.

*   **Multigrid Preconditioners:** The paper mentions the solving linear systems. Modern research suggests Algebraic Multigrid (AMG) preconditioners for these types of Laplacian-heavy problems. Eigen doesn't have a built-in AMG, but coupling with a library like **Hypre** or using **Incomplete Cholesky** preconditioning (available in Eigen) usually beats simple diagonal preconditioning.
*   **L2 Reconstruction:** The final polyline construction solves a large linear system. If this is slow, switching to a **supernodal** solver (like `Eigen::CholmodSupernodalLLT` if SuiteSparse is available) is the standard high-performance path.

## Summary of Recommendations (Ranked by Impact)
1.  **Enable AVX2:** Compile with architecture flags. (Low effort, High reward)
2.  **Parallelize Pixel Loops:** Use `cv::parallel_for_` in `calculateWeight`. (Medium effort, Medium reward)
3.  **Switch Linear Solver:** Test `Eigen::SimplicialLDLT` instead of `ConjugateGradient`. (Low effort, Potential robustness gain)
4.  **Update LBFGS:** Replace bundled code with `LBFGSpp` for maintainability. (Medium effort, Maintenance gain)
