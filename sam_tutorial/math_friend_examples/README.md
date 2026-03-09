# Python for a Mathematician: Simple Examples

These examples are intentionally short and readable.

Run any file with:

```bash
python3 <filename.py>
```

Suggested order:
1. `01_functions_and_numbers.py`
2. `02_sequences_and_series.py`
3. `03_matrices_as_lists.py`
4. `04_newton_method.py`
5. `05_points_vectors_and_triangles.py`
6. `06_transformations_in_plane.py`
7. `07_polygon_shoelace.py`
8. `08_fourier_ratio_basics.py`
9. `09_bi_fourier_ratio_subgroup.py`
10. `10_uncertainty_support_demo.py`
11. `11_sparse_spectrum_approximation.py`

Geometry-focused files:
- `05_points_vectors_and_triangles.py`: distances, dot product, triangle area
- `06_transformations_in_plane.py`: translation, rotation, reflection
- `07_polygon_shoelace.py`: polygon area and orientation

Fourier-ratio files inspired by `FRdiscrete.pdf`:
- `fourier_utils.py`: unitary DFT/IDFT helpers and norms
- `08_fourier_ratio_basics.py`: computes `FR(f)` and checks `1 <= FR <= sqrt(N)`
- `09_bi_fourier_ratio_subgroup.py`: demonstrates `FR_bi(f) = min(FR(f), FR(f_hat))`
- `10_uncertainty_support_demo.py`: support-size products in time vs frequency
- `11_sparse_spectrum_approximation.py`: sparse Fourier approximation experiment

Full documentation for all Python files in `sam_tutorial/`:
- `../PYTHON_CODE_DOCUMENTATION.md`
