# Copyright 2022 The JaxGaussianProcesses Contributors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

import jax.numpy as jnp
import jax.random as jr
import networkx as nx
from jax.config import config
from gpjax.linops import identity

from gpjax.kernels.non_euclidean import GraphKernel

# Enable Float64 for more stable matrix inversions.
config.update("jax_enable_x64", True)
_initialise_key = jr.PRNGKey(123)
_jitter = 1e-6


def test_graph_kernel():
    # Create a random graph, G, and verice labels, x,
    n_verticies = 20
    n_edges = 40
    G = nx.gnm_random_graph(n_verticies, n_edges, seed=123)
    x = jnp.arange(n_verticies).reshape(-1, 1)

    # Compute graph laplacian
    L = nx.laplacian_matrix(G).toarray() + jnp.eye(n_verticies) * 1e-12

    # Create graph kernel
    kern = GraphKernel(laplacian=L)
    assert isinstance(kern, GraphKernel)
    assert kern.num_vertex == n_verticies
    assert kern.evals.shape == (n_verticies, 1)
    assert kern.evecs.shape == (n_verticies, n_verticies)

    # Unpack kernel computation
    kern.gram

    # Initialise default parameters
    params = kern.init_params(_initialise_key)
    assert isinstance(params, dict)
    assert list(sorted(list(params.keys()))) == [
        "lengthscale",
        "smoothness",
        "variance",
    ]

    # Compute gram matrix
    Kxx = kern.gram(params, x)
    assert Kxx.shape == (n_verticies, n_verticies)

    # Check positive definiteness
    Kxx += identity(n_verticies) * _jitter
    eigen_values = jnp.linalg.eigvalsh(Kxx.to_dense())
    assert all(eigen_values > 0)
