# Copyright 2022 The GPJax Contributors. All Rights Reserved.
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


from itertools import permutations
from typing import Dict, List

import jax.numpy as jnp
import jax.random as jr
import networkx as nx
import numpy as np
import pytest
from jaxtyping import Array, Float

from gpjax.covariance_operator import (
    CovarianceOperator,
    DenseCovarianceOperator,
    DiagonalCovarianceOperator,
    I,
)
from gpjax.kernels import (
    RBF,
    CombinationKernel,
    GraphKernel,
    Kernel,
    Matern12,
    Matern32,
    Matern52,
    Polynomial,
    ProductKernel,
    SumKernel,
    _EigenKernel,
    euclidean_distance,
)
from gpjax.parameters import initialise
from gpjax.types import PRNGKeyType

"""Default values for tests"""
_initialise_key = jr.PRNGKey(123)
_jitter = 100


def test_abstract_kernel():
    # Test initialising abstract kernel raises TypeError with unimplemented __call__ and _init_params methods:
    with pytest.raises(TypeError):
        Kernel()

    # Create a dummy kernel class with __call__ and _init_params methods implemented:
    class DummyKernel(Kernel):
        def __call__(
            self, x: Float[Array, "1 D"], y: Float[Array, "1 D"], params: Dict
        ) -> Float[Array, "1"]:
            return x * params["test"] * y

        def _initialise_params(self, key: PRNGKeyType) -> Dict:
            return {"test": 1.0}

    # Initialise dummy kernel class and test __call__ and _init_params methods:
    dummy_kernel = DummyKernel()
    assert dummy_kernel._initialise_params(_initialise_key) == {"test": 1.0}
    assert dummy_kernel(jnp.array([1.0]), jnp.array([2.0]), {"test": 2.0}) == 4.0


@pytest.mark.parametrize(
    "a, b, distance_to_3dp",
    [
        ([1.0], [-4.0], 5.0),
        ([1.0, -2.0], [-4.0, 3.0], 7.071),
        ([1.0, 2.0, 3.0], [1.0, 1.0, 1.0], 2.236),
    ],
)
def test_euclidean_distance(
    a: List[float], b: List[float], distance_to_3dp: float
) -> None:

    # Convert lists to JAX arrays:
    a: Float[Array, "D"] = jnp.array(a)
    b: Float[Array, "D"] = jnp.array(b)

    # Test distance is correct to 3dp:
    assert jnp.round(euclidean_distance(a, b), 3) == distance_to_3dp


@pytest.mark.parametrize("kernel", [RBF(), Matern12(), Matern32(), Matern52()])
@pytest.mark.parametrize("dim", [1, 2, 5])
@pytest.mark.parametrize("n", [1, 2, 10])
def test_gram(kernel: Kernel, dim: int, n: int) -> None:

    # Gram constructor static method:
    gram = kernel.gram

    # Inputs x:
    x = jnp.linspace(0.0, 1.0, n * dim).reshape(n, dim)

    # Default kernel parameters:
    params = kernel._initialise_params(_initialise_key)

    # Test gram matrix:
    Kxx = gram(kernel, x, params)
    assert isinstance(Kxx, CovarianceOperator)
    assert Kxx.shape == (n, n)


@pytest.mark.parametrize("kernel", [RBF(), Matern12(), Matern32(), Matern52()])
@pytest.mark.parametrize("num_a", [1, 2, 5])
@pytest.mark.parametrize("num_b", [1, 2, 5])
@pytest.mark.parametrize("dim", [1, 2, 5])
def test_cross_covariance(kernel: Kernel, num_a: int, num_b: int, dim: int) -> None:

    # Cross covariance constructor static method:
    cross_cov = kernel.cross_covariance

    # Inputs a, b:
    a = jnp.linspace(-1.0, 1.0, num_a * dim).reshape(num_a, dim)
    b = jnp.linspace(3.0, 4.0, num_b * dim).reshape(num_b, dim)

    # Default kernel parameters:
    params = kernel._initialise_params(_initialise_key)

    # Test cross covariance, Kab:
    Kab = cross_cov(kernel, a, b, params)
    assert isinstance(Kab, jnp.ndarray)
    assert Kab.shape == (num_a, num_b)


@pytest.mark.parametrize("kernel", [RBF(), Matern12(), Matern32(), Matern52()])
@pytest.mark.parametrize("dim", [1, 2, 5])
def test_call(kernel: Kernel, dim: int) -> None:

    # Datapoint x and datapoint y:
    x = jnp.array([[1.0] * dim])
    y = jnp.array([[0.5] * dim])

    # Defualt parameters:
    params = kernel._initialise_params(_initialise_key)

    # Test calling gives an autocovariance value of no dimension between the inputs:
    kxy = kernel(x, y, params)

    assert isinstance(kxy, jnp.DeviceArray)
    assert kxy.shape == ()


@pytest.mark.parametrize("kern", [RBF(), Matern12(), Matern32(), Matern52()])
@pytest.mark.parametrize("dim", [1, 2, 5])
@pytest.mark.parametrize("ell, sigma", [(0.1, 0.2), (0.5, 0.1), (0.1, 0.5), (0.5, 0.5)])
@pytest.mark.parametrize("n", [1, 2, 5])
def test_pos_def(kern: Kernel, dim: int, ell: float, sigma: float, n: int) -> None:

    # Gram constructor static method:
    gram = kern.gram

    # Create inputs x:
    x = jr.uniform(_initialise_key, (n, dim))
    params = {"lengthscale": jnp.array([ell]), "variance": jnp.array([sigma])}

    # Test gram matrix eigenvalues are positive:
    Kxx = gram(kern, x, params)
    Kxx += I(n) * _jitter
    eigen_values = jnp.linalg.eigvalsh(Kxx.to_dense())
    assert (eigen_values > 0.0).all()


@pytest.mark.parametrize("kernel", [RBF, Matern12, Matern32, Matern52])
@pytest.mark.parametrize("dim", [None, 1, 2, 5, 10])
def test_initialisation(kernel: Kernel, dim: int) -> None:

    if dim is None:
        kern = kernel()
        assert kern.ndims == 1

    else:
        kern = kernel(active_dims=[i for i in range(dim)])
        params = kern._initialise_params(_initialise_key)

        assert list(params.keys()) == ["lengthscale", "variance"]
        assert all(params["lengthscale"] == jnp.array([1.0] * dim))
        assert params["variance"] == jnp.array([1.0])

        if dim > 1:
            assert kern.ard
        else:
            assert not kern.ard


@pytest.mark.parametrize("kernel", [RBF, Matern12, Matern32, Matern52])
def test_dtype(kernel: Kernel) -> None:

    parameter_state = initialise(kernel(), _initialise_key)
    params, *_ = parameter_state.unpack()
    for k, v in params.items():
        assert v.dtype == jnp.float64


@pytest.mark.parametrize("degree", [1, 2, 3])
@pytest.mark.parametrize("dim", [1, 2, 5])
@pytest.mark.parametrize("variance", [0.1, 1.0, 2.0])
@pytest.mark.parametrize("shift", [1e-6, 0.1, 1.0])
@pytest.mark.parametrize("n", [1, 2, 5])
def test_polynomial(
    degree: int, dim: int, variance: float, shift: float, n: int
) -> None:

    x = jnp.linspace(0.0, 1.0, n * dim).reshape(n, dim)

    kern = Polynomial(degree=degree, active_dims=[i for i in range(dim)])
    assert kern.name == f"Polynomial Degree: {degree}"

    params = kern._initialise_params(_initialise_key)
    params["shift"] * shift
    params["variance"] * variance

    gram = kern.gram

    # Test positive definiteness:
    Kxx = gram(kern, x, params)
    Kxx += I(n) * _jitter
    eigen_values, _ = jnp.linalg.eigh(Kxx.to_dense())
    assert (eigen_values > 0).all()
    assert Kxx.shape[0] == x.shape[0]
    assert Kxx.shape[0] == Kxx.shape[1]
    assert list(params.keys()) == ["shift", "variance"]


@pytest.mark.parametrize("kernel", [RBF, Matern12, Matern32, Matern52])
def test_active_dim(kernel: Kernel) -> None:
    dim_list = [0, 1, 2, 3]
    perm_length = 2
    dim_pairs = list(permutations(dim_list, r=perm_length))
    n_dims = len(dim_list)
    key = jr.PRNGKey(123)
    X = jr.normal(key, shape=(20, n_dims))

    for dp in dim_pairs:
        Xslice = X[..., dp]
        ad_kern = kernel(active_dims=dp)
        manual_kern = kernel(active_dims=[i for i in range(perm_length)])

        ad_default_params = ad_kern._initialise_params(key)
        manual_default_params = manual_kern._initialise_params(key)

        k1 = ad_kern.gram(ad_kern, X, ad_default_params)
        k2 = manual_kern.gram(manual_kern, Xslice, manual_default_params)
        assert jnp.all(k1.to_dense() == k2.to_dense())


@pytest.mark.parametrize("combination_type", [SumKernel, ProductKernel])
@pytest.mark.parametrize("kernel", [RBF, Matern12, Matern32, Matern52, Polynomial])
@pytest.mark.parametrize("n_kerns", [2, 3, 4])
def test_combination_kernel(
    combination_type: CombinationKernel, kernel: Kernel, n_kerns: int
) -> None:

    n = 20
    kern_list = [kernel() for _ in range(n_kerns)]
    c_kernel = combination_type(kernel_set=kern_list)
    assert len(c_kernel.kernel_set) == n_kerns
    assert len(c_kernel._initialise_params(_initialise_key)) == n_kerns
    assert isinstance(c_kernel.kernel_set, list)
    assert isinstance(c_kernel.kernel_set[0], Kernel)
    assert isinstance(c_kernel._initialise_params(_initialise_key)[0], dict)
    x = jnp.linspace(0.0, 1.0, num=n).reshape(-1, 1)
    Kff = c_kernel.gram(c_kernel, x, c_kernel._initialise_params(_initialise_key))
    assert Kff.shape[0] == Kff.shape[1]
    assert Kff.shape[1] == n


@pytest.mark.parametrize(
    "k1", [RBF(), Matern12(), Matern32(), Matern52(), Polynomial()]
)
@pytest.mark.parametrize(
    "k2", [RBF(), Matern12(), Matern32(), Matern52(), Polynomial()]
)
def test_sum_kern_value(k1: Kernel, k2: Kernel) -> None:
    n = 10
    sum_kernel = SumKernel(kernel_set=[k1, k2])
    x = jnp.linspace(0.0, 1.0, num=n).reshape(-1, 1)
    Kff = sum_kernel.gram(
        sum_kernel, x, sum_kernel._initialise_params(_initialise_key)
    ).to_dense()
    Kff_manual = (
        k1.gram(k1, x, k1._initialise_params(_initialise_key)).to_dense()
        + k2.gram(k2, x, k2._initialise_params(_initialise_key)).to_dense()
    )
    assert jnp.all(Kff == Kff_manual)


@pytest.mark.parametrize(
    "k1", [RBF(), Matern12(), Matern32(), Matern52(), Polynomial()]
)
@pytest.mark.parametrize(
    "k2", [RBF(), Matern12(), Matern32(), Matern52(), Polynomial()]
)
def test_prod_kern_value(k1: Kernel, k2: Kernel) -> None:
    n = 10
    prod_kernel = ProductKernel(kernel_set=[k1, k2])
    x = jnp.linspace(0.0, 1.0, num=n).reshape(-1, 1)
    Kff = prod_kernel.gram(
        prod_kernel, x, prod_kernel._initialise_params(_initialise_key)
    ).to_dense()
    Kff_manual = (
        k1.gram(k1, x, k1._initialise_params(_initialise_key)).to_dense()
        * k2.gram(k2, x, k2._initialise_params(_initialise_key)).to_dense()
    )
    assert jnp.all(Kff == Kff_manual)


def test_graph_kernel():
    n_verticies = 20
    n_edges = 40
    G = nx.gnm_random_graph(n_verticies, n_edges, seed=123)
    L = nx.laplacian_matrix(G).toarray() + jnp.eye(n_verticies) * 1e-12
    kern = GraphKernel(laplacian=L)
    assert isinstance(kern, GraphKernel)
    assert isinstance(kern, _EigenKernel)

    kern_params = kern._initialise_params(_initialise_key)
    assert isinstance(kern_params, dict)
    assert list(sorted(list(kern_params.keys()))) == [
        "lengthscale",
        "smoothness",
        "variance",
    ]
    x = jnp.arange(n_verticies).reshape(-1, 1)
    Kxx = kern.gram(kern, x, kern._initialise_params(_initialise_key))
    assert Kxx.shape == (n_verticies, n_verticies)
    eigen_values, _ = jnp.linalg.eigh(Kxx.to_dense() + jnp.eye(n_verticies) * 1e-8)
    assert all(eigen_values > 0)

    assert kern.num_vertex == n_verticies
    assert kern.evals.shape == (n_verticies, 1)
    assert kern.evecs.shape == (n_verticies, n_verticies)


@pytest.mark.parametrize("kernel", [RBF, Matern12, Matern32, Matern52, Polynomial])
def test_combination_kernel_type(kernel: Kernel) -> None:
    prod_kern = kernel() * kernel()
    assert isinstance(prod_kern, ProductKernel)
    assert isinstance(prod_kern, CombinationKernel)

    add_kern = kernel() + kernel()
    assert isinstance(add_kern, SumKernel)
    assert isinstance(add_kern, CombinationKernel)
