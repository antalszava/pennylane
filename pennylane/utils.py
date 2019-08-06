# Copyright 2018 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Utilities
=========

**Module name:** :mod:`pennylane.utils`

.. currentmodule:: pennylane.utils

This module contains utilities and auxiliary functions, which are shared
across the PennyLane submodules.

.. raw:: html

    <h3>Summary</h3>

.. autosummary::
    _flatten
    _unflatten
    unflatten
    _inv_dict
    _get_default_args
    expand
    to_DiGraph

.. raw:: html

    <h3>Code details</h3>
"""
from collections import namedtuple
from collections.abc import Iterable
import numbers
import inspect
import itertools

import autograd.numpy as np
import networkx as nx

from pennylane.variable import Variable


Command = namedtuple("Command", ["name", "op"])


def _flatten(x):
    """Iterate through an arbitrarily nested structure, flattening it in depth-first order.

    See also :func:`_unflatten`.

    Args:
        x (array, Iterable, other): each element of the Iterable may itself be an iterable object

    Yields:
        other: elements of x in depth-first order
    """
    if isinstance(x, np.ndarray):
        yield from _flatten(x.flat)  # should we allow object arrays? or just "yield from x.flat"?
    elif isinstance(x, Iterable) and not isinstance(x, (str, bytes)):
        for item in x:
            yield from _flatten(item)
    else:
        yield x


def _unflatten(flat, model):
    """Restores an arbitrary nested structure to a flattened iterable.

    See also :func:`_flatten`.

    Args:
        flat (array): 1D array of items
        model (array, Iterable, Number): model nested structure

    Returns:
        (other, array): first elements of flat arranged into the nested
        structure of model, unused elements of flat
    """
    if isinstance(model, (numbers.Number, Variable, str)):
        return flat[0], flat[1:]
    elif isinstance(model, np.ndarray):
        idx = model.size
        res = np.array(flat)[:idx].reshape(model.shape)
        return res, flat[idx:]
    elif isinstance(model, Iterable):
        res = []
        for x in model:
            val, flat = _unflatten(flat, x)
            res.append(val)
        return res, flat
    else:
        raise TypeError("Unsupported type in the model: {}".format(type(model)))


def unflatten(flat, model):
    """Wrapper for :func:`_unflatten`.
    """
    # pylint:disable=len-as-condition
    res, tail = _unflatten(np.asarray(flat), model)
    if len(tail) != 0:
        raise ValueError("Flattened iterable has more elements than the model.")
    return res


def _inv_dict(d):
    """Reverse a dictionary mapping.

    Returns multimap where the keys are the former values,
    and values are sets of the former keys.

    Args:
        d (dict[a->b]): mapping to reverse

    Returns:
        dict[b->set[a]]: reversed mapping
    """
    ret = {}
    for k, v in d.items():
        ret.setdefault(v, set()).add(k)
    return ret


def _get_default_args(func):
    """Get the default arguments of a function.

    Args:
        func (function): a valid Python function

    Returns:
        dict: dictionary containing the argument name and tuple
        (positional idx, default value)
    """
    signature = inspect.signature(func)
    return {
        k: (idx, v.default)
        for idx, (k, v) in enumerate(signature.parameters.items())
        if v.default is not inspect.Parameter.empty
    }


def expand(U, wires, num_wires):
    r"""Expand a multi-qubit operator into a full system operator.

    Args:
        U (array): :math:`2^n \times 2^n` matrix where n = len(wires).
        wires (Sequence[int]): Target subsystems (order matters! the
            left-most Hilbert space is at index 0).

    Returns:
        array: :math:`2^N\times 2^N` matrix. The full system operator.
    """
    if num_wires == 1:
        # total number of wires is 1, simply return the matrix
        return U

    N = num_wires
    wires = np.asarray(wires)

    if np.any(wires < 0) or np.any(wires >= N) or len(set(wires)) != len(wires):
        raise ValueError("Invalid target subsystems provided in 'wires' argument.")

    if U.shape != (2 ** len(wires), 2 ** len(wires)):
        raise ValueError("Matrix parameter must be of size (2**len(wires), 2**len(wires))")

    # generate N qubit basis states via the cartesian product
    tuples = np.array(list(itertools.product([0, 1], repeat=N)))

    # wires not acted on by the operator
    inactive_wires = list(set(range(N)) - set(wires))

    # expand U to act on the entire system
    U = np.kron(U, np.identity(2 ** len(inactive_wires)))

    # move active wires to beginning of the list of wires
    rearranged_wires = np.array(list(wires) + inactive_wires)

    # convert to computational basis
    # i.e., converting the list of basis state bit strings into
    # a list of decimal numbers that correspond to the computational
    # basis state. For example, [0, 1, 0, 1, 1] = 2^3+2^1+2^0 = 11.
    perm = np.ravel_multi_index(tuples[:, rearranged_wires].T, [2] * N)

    # permute U to take into account rearranged wires
    return U[:, perm][perm]


def to_DiGraph(queue, observables):
    """Convert a queue and observables to a directed acyclic graph.

    The resulting graph has nodes representing quantum operations,
    and edges representing dependent/successor operations.

    Each node is labelled by an integer corresponding to the position
    in the queue; note attributes are used to store information about the node:

    * ``'name'`` *(str)*: name of the quantum operation (e.g., ``'PauliZ'``)

    * ``'op'`` *(Operation or Observable)*: modes the operation acts on

    Args:
        queue (list[Operation]): the quantum operations to apply
        observables (list[Observable]): the quantum observables to measure

    Returns:
        networkx.DiGraph: the directed acyclic graph representing
        the quantum program
    """
    grid = {}

    for idx, op in enumerate(queue + observables):
        cmd = Command(name=op.name, op=op)

        for q in set(op.wires):
            # Add cmd to the grid to the end of the line r.ind.
            if q not in grid:
                # add a new line to the circuit
                grid[q] = []

            grid[q].append([idx, cmd])

    G = nx.DiGraph()

    for q, cmds in grid.items():
        if cmds:
            # add the first operation on the wire that does not depend on anything
            attrs = cmds[0][1]._asdict()
            G.add_node(cmds[0][0], **attrs)

        for i in range(1, len(cmds)):
            # add the edge between the operations, and the operation nodes themselves
            if cmds[i][0] not in G:
                attrs = cmds[i][1]._asdict()
                G.add_node(cmds[i][0], **attrs)

            G.add_edge(cmds[i - 1][0], cmds[i][0])

    return G
