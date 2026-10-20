"""Kernel density evaluation with bounded temporary arrays."""

import numpy as N


def _kde(data, grid, bandwidth, gaussian):
    n = len(data)
    if n == 0 or bandwidth <= 0:
        return N.zeros_like(grid)
    density = N.zeros_like(grid, dtype=float)
    for start in range(0, n, 4096):
        kernel = (grid[:, None] - data[None, start:start + 4096]) / bandwidth
        if gaussian:
            N.square(kernel, out=kernel)
            kernel *= -0.5
            N.exp(kernel, out=kernel)
        else:
            inside = N.abs(kernel) <= 1
            N.square(kernel, out=kernel)
            N.subtract(1, kernel, out=kernel)
            kernel *= 0.75
            kernel[~inside] = 0
        density += kernel.sum(axis=1)
    normalization = n * bandwidth
    if gaussian:
        normalization *= N.sqrt(2 * N.pi)
    return density / normalization


def gaussian_kde(data, grid, bw):
    return _kde(data, grid, bw, True)


def epanechnikov_kde(data, grid, bw):
    return _kde(data, grid, bw, False)
