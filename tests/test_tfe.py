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
Unit tests for the :mod:`pennylane.interface.tfe` QNode interface.
"""

import pytest

import numpy as np

try:
    import tensorflow as tf
    import tensorflow.contrib.eager as tfe
    tf.enable_eager_execution()
except ImportError as e:
    pass

import pennylane as qml

from pennylane.qnode import _flatten, unflatten, QNode, QuantumFunctionError
from pennylane.plugins.default_qubit import CNOT, Rotx, Roty, Rotz, I, Y, Z
from pennylane._device import DeviceError


def expZ(state):
    return np.abs(state[0]) ** 2 - np.abs(state[1]) ** 2

@pytest.fixture()
def skip_if_no_tf_support(tf_support):
    if not tf_support:
        pytest.skip("Skipped, no tfe support")   


@pytest.mark.usefixtures("skip_if_no_tf_support")
class TestTFEQNodeExceptions():
    """TFEQNode basic tests."""

    def test_qnode_fails_on_wrong_return_type(self, qubit_device_2_wires):
        """The qfunc must return only Expectations"""
        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def qf(x):
            qml.RX(x, wires=[0])
            return qml.expval(qml.PauliZ(0)), 0.3

        with pytest.raises(QuantumFunctionError, match='must return either'):
            qf(tfe.Variable(0.5))

    def test_qnode_fails_on_expval_not_returned(self, qubit_device_2_wires):
        """All expectation values in the qfunc must be returned"""

        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def qf(x):
            qml.RX(x, wires=[0])
            ex = qml.expval(qml.PauliZ(1))
            return qml.expval(qml.PauliZ(0))

        with pytest.raises(QuantumFunctionError, match='All measured observables'):
            qf(tfe.Variable(0.5))

    def test_qnode_fails_on_wrong_expval_order(self, qubit_device_2_wires):
        """Expvals must be returned in the order they were created in"""

        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def qf(x):
            qml.RX(x, wires=[0])
            ex = qml.expval(qml.PauliZ(1))
            return qml.expval(qml.PauliZ(0)), ex

        with pytest.raises(QuantumFunctionError, match='All measured observables'):
            qf(tfe.Variable(0.5))

    def test_qnode_fails_on_gates_after_measurements(self, qubit_device_2_wires):
        """Gates have to precede measurements"""

        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def qf(x):
            qml.RX(x, wires=[0])
            ev = qml.expval(qml.PauliZ(1))
            qml.RY(0.5, wires=[0])
            return ev

        with pytest.raises(QuantumFunctionError, match='gates must precede'):
            qf(tfe.Variable(0.5))

    def test_qnode_fails_on_multiple_measurements_of_same_wire(self, qubit_device_2_wires):
        """A wire can only be measured once"""
        
        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def qf(x):
            qml.RX(x, wires=[0])
            qml.CNOT(wires=[0, 1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1)), qml.expval(qml.PauliX(0))

        with pytest.raises(QuantumFunctionError, match='can only be measured once'):
            qf(tfe.Variable(0.5))

    def test_qnode_fails_on_qfunc_with_too_many_wires(self, qubit_device_2_wires):
        """The device must have sufficient wires for the qfunc"""

        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def qf(x):
            qml.RX(x, wires=[0])
            qml.CNOT(wires=[0, 2])
            return qml.expval(qml.PauliZ(0))

        with pytest.raises(QuantumFunctionError, match='applied to invalid wire'):
            qf(tfe.Variable(0.5))

    def test_qnode_fails_on_combination_of_cv_and_qbit_ops(self, qubit_device_1_wire):
        """CV and discrete operations must not be mixed"""
        
        @qml.qnode(qubit_device_1_wire, interface='tfe')
        def qf(x):
            qml.RX(x, wires=[0])
            qml.Displacement(0.5, 0, wires=[0])
            return qml.expval(qml.PauliZ(0))

        with pytest.raises(QuantumFunctionError, match='Continuous and discrete'):
            qf(tfe.Variable(0.5))

    def test_qnode_fails_for_cv_ops_on_qubit_device(self, qubit_device_1_wire):
        """A qubit device cannot execute CV operations"""

        @qml.qnode(qubit_device_1_wire, interface='tfe')
        def qf(x):
            qml.Displacement(0.5, 0, wires=[0])
            return qml.expval(qml.X(0))

        with pytest.raises(DeviceError, match='Gate [a-zA-Z]+ not supported on device'):
            qf(tfe.Variable(0.5))

    def test_qnode_fails_for_cv_observables_on_qubit_device(self, qubit_device_1_wire):
        """A qubit device cannot measure CV observables"""

        @qml.qnode(qubit_device_1_wire, interface='tfe')
        def qf(x):
            return qml.expval(qml.X(0))

        with pytest.raises(DeviceError, match='Observable [a-zA-Z]+ not supported on device'):
            qf(tfe.Variable(0.5))


@pytest.mark.usefixtures("skip_if_no_tf_support")
class TestTFEQNodeParameterHandling:
    """Test that the TFEQNode properly handles the parameters of qfuncs"""

    def test_qnode_fanout(self, qubit_device_1_wire, tol):
        """Tests that qnodes can compute the correct function when the same parameter is used in multiple gates."""

        @qml.qnode(qubit_device_1_wire, interface='tfe')
        def circuit(reused_param, other_param):
            qml.RX(reused_param, wires=[0])
            qml.RZ(other_param, wires=[0])
            qml.RX(reused_param, wires=[0])
            return qml.expval(qml.PauliZ(0))

        thetas = tf.linspace(-2*np.pi, 2*np.pi, 7)

        for reused_param in thetas:
            for theta in thetas:
                other_param = theta ** 2 / 11
                y_eval = circuit(reused_param, other_param)
                Rx = Rotx(reused_param.numpy())
                Rz = Rotz(other_param.numpy())
                zero_state = np.array([1.,0.])
                final_state = (Rx @ Rz @ Rx @ zero_state)
                y_true = expZ(final_state)

                assert np.allclose(y_eval, y_true, atol=tol, rtol=0)

    def test_qnode_array_parameters_scalar_return(self, qubit_device_1_wire, tol):
        """Test that QNode can take arrays as input arguments, and that they interact properly with TensorFlow.
           Test case for a circuit that returns a scalar."""

        # The objective of this test is not to check if the results are correctly calculated, 
        # but to check that the interoperability of the different return types works.
        @qml.qnode(qubit_device_1_wire, interface='tfe')
        def circuit(dummy1, array, dummy2):
            qml.RY(0.5 * array[0,1], wires=0)
            qml.RY(-0.5 * array[1,1], wires=0)
            return qml.expval(qml.PauliX(0))  # returns a scalar

        grad_target = (np.array(1.), np.array([[0.5,  0.43879, 0], [0, -0.43879, 0]]), np.array(-0.4))
        cost_target = 1.03257

        args = (tfe.Variable(0.46), tfe.Variable([[2., 3., 0.3], [7., 4., 2.1]]), tfe.Variable(-0.13))

        def cost(x, array, y):
            c = tf.cast(circuit(tf.constant(0.111), array, tf.constant(4.5)), tf.float32)
            
            return c +0.5*array[0,0] +x -0.4*y

        with tf.GradientTape() as tape:
            cost_res = cost(*args)
            grad_res = np.array([i.numpy() for i in tape.gradient(cost_res, [args[0], args[2]])])

        assert np.allclose(cost_res.numpy(), cost_target, atol=tol, rtol=0)
        assert np.allclose(grad_res, np.fromiter(grad_target[::2], dtype=np.float32), atol=tol, rtol=0)

    def test_qnode_array_parameters_1_vector_return(self, qubit_device_1_wire, tol):
        """Test that QNode can take arrays as input arguments, and that they interact properly with TensorFlow
           Test case for a circuit that returns a 1-vector."""

        # The objective of this test is not to check if the results are correctly calculated, 
        # but to check that the interoperability of the different return types works.
        @qml.qnode(qubit_device_1_wire, interface='tfe')
        def circuit(dummy1, array, dummy2):
            qml.RY(0.5 * array[0,1], wires=0)
            qml.RY(-0.5 * array[1,1], wires=0)
            return qml.expval(qml.PauliX(0)),  # note the comma, returns a 1-vector

        grad_target = (np.array(1.), np.array([[0.5,  0.43879, 0], [0, -0.43879, 0]]), np.array(-0.4))
        cost_target = 1.03257

        args = (tfe.Variable(0.46), tfe.Variable([[2., 3., 0.3], [7., 4., 2.1]]), tfe.Variable(-0.13))

        def cost(x, array, y):
            c = tf.cast(circuit(tf.constant(0.111), array, tf.constant(4.5)), tf.float32)
            c = c[0]  # get a scalar
            return c +0.5*array[0,0] +x -0.4*y

        with tf.GradientTape() as tape:
            cost_res = cost(*args)
            grad_res = np.array([i.numpy() for i in tape.gradient(cost_res, [args[0], args[2]])])

        assert np.allclose(cost_res.numpy(), cost_target, atol=tol, rtol=0)
        assert np.allclose(grad_res, np.fromiter(grad_target[::2], dtype=np.float32), atol=tol, rtol=0)

    def test_qnode_array_parameters_2_vector_return(self, qubit_device_2_wires, tol):
        """Test that QNode can take arrays as input arguments, and that they interact properly with TensorFlow
           Test case for a circuit that returns a 2-vector."""

        # The objective of this test is not to check if the results are correctly calculated, 
        # but to check that the interoperability of the different return types works.
        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def circuit(dummy1, array, dummy2):
            qml.RY(0.5 * array[0,1], wires=0)
            qml.RY(-0.5 * array[1,1], wires=0)
            qml.RY(array[1,0], wires=1)
            return qml.expval(qml.PauliX(0)), qml.expval(qml.PauliX(1))  # returns a 2-vector

        grad_target = (np.array(1.), np.array([[0.5,  0.43879, 0], [0, -0.43879, 0]]), np.array(-0.4))
        cost_target = 1.03257

        args = (tfe.Variable(0.46), tfe.Variable([[2., 3., 0.3], [7., 4., 2.1]]), tfe.Variable(-0.13))

        def cost(x, array, y):
            c = tf.cast(circuit(tf.constant(0.111), array, tf.constant(4.5)), tf.float32)
            c = c[0]  # get a scalar
            return c +0.5*array[0,0] +x -0.4*y

        with tf.GradientTape() as tape:
            cost_res = cost(*args)
            grad_res = np.array([i.numpy() for i in tape.gradient(cost_res, [args[0], args[2]])])

        assert np.allclose(cost_res.numpy(), cost_target, atol=tol, rtol=0)
        assert np.allclose(grad_res, np.fromiter(grad_target[::2], dtype=np.float32), atol=tol, rtol=0)


    def test_array_parameters_evaluate(self, qubit_device_2_wires, tol):
        """Test that array parameters gives same result as positional arguments."""
        a, b, c = tf.constant(0.5), tf.constant(0.54), tf.constant(0.3)

        def ansatz(x, y, z):
            qml.QubitStateVector(np.array([1, 0, 1, 1])/np.sqrt(3), wires=[0, 1])
            qml.Rot(x, y, z, wires=0)
            qml.CNOT(wires=[0, 1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliY(1))

        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def circuit1(x, y, z):
            return ansatz(x, y, z)

        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def circuit2(x, array):
            return ansatz(x, array[0], array[1])

        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def circuit3(array):
            return ansatz(*array)

        positional_res = circuit1(a, b, c)
        array_res1 = circuit2(a, tfe.Variable([b, c]))
        array_res2 = circuit3(tfe.Variable([a, b, c]))

        assert np.allclose(positional_res.numpy(), array_res1.numpy(), atol=tol, rtol=0)
        assert np.allclose(positional_res.numpy(), array_res2.numpy(), atol=tol, rtol=0)

    def test_multiple_expectation_different_wires(self, qubit_device_2_wires, tol):
        """Tests that qnodes return multiple expectation values."""
        a, b, c = tfe.Variable(0.5), tfe.Variable(0.54), tfe.Variable(0.3)

        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def circuit(x, y, z):
            qml.RX(x, wires=[0])
            qml.RZ(y, wires=[0])
            qml.CNOT(wires=[0, 1])
            qml.RY(y, wires=[0])
            qml.RX(z, wires=[0])
            return qml.expval(qml.PauliY(0)), qml.expval(qml.PauliZ(1))

        res = circuit(a, b, c)

        out_state = np.kron(Rotx(c.numpy()), I) @ np.kron(Roty(b.numpy()), I) @ CNOT \
            @ np.kron(Rotz(b.numpy()), I) @ np.kron(Rotx(a.numpy()), I) @ np.array([1, 0, 0, 0])

        ex0 = np.vdot(out_state, np.kron(Y, I) @ out_state)
        ex1 = np.vdot(out_state, np.kron(I, Z) @ out_state)
        ex = np.array([ex0, ex1])

        assert np.allclose(ex, res.numpy(), atol=tol, rtol=0)

    def test_multiple_keywordargs_used(self, qubit_device_2_wires, tol):
        """Tests that qnodes use multiple keyword arguments."""

        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def circuit(w, x=None, y=None):
            qml.RX(x, wires=[0])
            qml.RX(y, wires=[1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        c = circuit(tf.constant(1.), x=np.pi, y=np.pi)

        assert np.allclose(c.numpy(), [-1., -1.], atol=tol, rtol=0)

    def test_multidimensional_keywordargs_used(self, qubit_device_2_wires, tol):
        """Tests that qnodes use multi-dimensional keyword arguments."""
        def circuit(w, x=None):
            qml.RX(x[0], wires=[0])
            qml.RX(x[1], wires=[1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        circuit = qml.QNode(circuit, qubit_device_2_wires).to_tfe()

        c = circuit(tf.constant(1.), x=[np.pi, np.pi])
        assert np.allclose(c.numpy(), [-1., -1.], atol=tol, rtol=0)

    def test_keywordargs_for_wires(self, qubit_device_2_wires, tol):
        """Tests that wires can be passed as keyword arguments."""
        default_q = 0

        def circuit(x, q=default_q):
            qml.RY(x, wires=0)
            return qml.expval(qml.PauliZ(q))

        circuit = qml.QNode(circuit, qubit_device_2_wires).to_tfe()

        c = circuit(tf.constant(np.pi), q=1)
        assert np.allclose(c, 1., atol=tol, rtol=0)

        c = circuit(tf.constant(np.pi))
        assert np.allclose(c.numpy(), -1., atol=tol, rtol=0)

    def test_keywordargs_used(self, qubit_device_1_wire, tol):
        """Tests that qnodes use keyword arguments."""

        def circuit(w, x=None):
            qml.RX(x, wires=[0])
            return qml.expval(qml.PauliZ(0))

        circuit = qml.QNode(circuit, qubit_device_1_wire).to_tfe()

        c = circuit(tf.constant(1.), x=np.pi)
        assert np.allclose(c.numpy(), -1., atol=tol, rtol=0)

    def test_mixture_numpy_tensors(self, qubit_device_2_wires, tol):
        """Tests that qnodes work with python types and tensors."""

        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def circuit(w, x, y):
            qml.RX(x, wires=[0])
            qml.RX(y, wires=[1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        c = circuit(tf.constant(1.), np.pi, np.pi).numpy()
        assert np.allclose(c, [-1., -1.], atol=tol, rtol=0)

    def test_keywordarg_updated_in_multiple_calls(self, qubit_device_2_wires):
        """Tests that qnodes update keyword arguments in consecutive calls."""

        def circuit(w, x=None):
            qml.RX(w, wires=[0])
            qml.RX(x, wires=[1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        circuit = qml.QNode(circuit, qubit_device_2_wires).to_tfe()

        c1 = circuit(tf.constant(0.1), x=tf.constant(0.))
        c2 = circuit(tf.constant(0.1), x=np.pi)
        assert c1[1] != c2[1]

    def test_keywordarg_passes_through_classicalnode(self, qubit_device_2_wires, tol):
        """Tests that qnodes' keyword arguments pass through classical nodes."""

        def circuit(w, x=None):
            qml.RX(w, wires=[0])
            qml.RX(x, wires=[1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        circuit = qml.QNode(circuit, qubit_device_2_wires).to_tfe()

        def classnode(w, x=None):
            return circuit(w, x=x)

        c = classnode(tf.constant(0.), x=np.pi)
        assert np.allclose(c.numpy(), [1., -1.], atol=tol, rtol=0)

    def test_keywordarg_gradient(self, qubit_device_2_wires, tol):
        """Tests that qnodes' keyword arguments work with gradients"""

        def circuit(x, y, input_state=np.array([0, 0])):
            qml.BasisState(input_state, wires=[0, 1])
            qml.RX(x, wires=[0])
            qml.RY(y, wires=[0])
            return qml.expval(qml.PauliZ(0))

        circuit = qml.QNode(circuit, qubit_device_2_wires).to_tfe()

        x = 0.543
        y = 0.45632
        expected_grad = np.array([np.sin(x)*np.cos(y), np.sin(y)*np.cos(x)])

        x_t = tfe.Variable(x)
        y_t = tfe.Variable(y)

        # test first basis state against analytic result
        with tf.GradientTape() as tape:
            c = circuit(x_t, y_t, input_state=np.array([0, 0]))
            grads = np.array(tape.gradient(c, [x_t, y_t]))

        assert np.allclose(grads, -expected_grad, atol=tol, rtol=0)

        # test third basis state against analytic result
        with tf.GradientTape() as tape:
            c = circuit(x_t, y_t, input_state=np.array([1, 0]))
            grads = np.array(tape.gradient(c, [x_t, y_t]))

        assert np.allclose(grads, expected_grad, atol=tol, rtol=0)

        # test first basis state via the default keyword argument against analytic result
        with tf.GradientTape() as tape:
            c = circuit(x_t, y_t)
            grads = np.array(tape.gradient(c, [x_t, y_t]))

        assert np.allclose(grads, -expected_grad, atol=tol, rtol=0)


@pytest.mark.usefixtures("skip_if_no_tf_support")
class TestIntegration():
    """Integration tests to ensure the TensorFlow QNode agrees with the NumPy QNode"""

    def test_qnode_evaluation_agrees(self, qubit_device_2_wires, tol):
        """Tests that simple example is consistent."""

        @qml.qnode(qubit_device_2_wires, interface='autograd')
        def circuit(phi, theta):
            qml.RX(phi[0], wires=0)
            qml.RY(phi[1], wires=1)
            qml.CNOT(wires=[0, 1])
            qml.PhaseShift(theta[0], wires=0)
            return qml.expval(qml.PauliZ(0))

        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def circuit_tfe(phi, theta):
            qml.RX(phi[0], wires=0)
            qml.RY(phi[1], wires=1)
            qml.CNOT(wires=[0, 1])
            qml.PhaseShift(theta[0], wires=0)
            return qml.expval(qml.PauliZ(0))

        phi = [0.5, 0.1]
        theta = [0.2]

        phi_t = tfe.Variable(phi)
        theta_t = tfe.Variable(theta)

        autograd_eval = circuit(phi, theta)
        tfe_eval = circuit_tfe(phi_t, theta_t)
        assert np.allclose(autograd_eval, tfe_eval.numpy(), atol=tol, rtol=0)

    def test_qnode_gradient_agrees(self, qubit_device_2_wires, tol):
        """Tests that simple gradient example is consistent."""

        @qml.qnode(qubit_device_2_wires, interface='autograd')
        def circuit(phi, theta):
            qml.RX(phi[0], wires=0)
            qml.RY(phi[1], wires=1)
            qml.CNOT(wires=[0, 1])
            qml.PhaseShift(theta[0], wires=0)
            return qml.expval(qml.PauliZ(0))

        @qml.qnode(qubit_device_2_wires, interface='tfe')
        def circuit_tfe(phi, theta):
            qml.RX(phi[0], wires=0)
            qml.RY(phi[1], wires=1)
            qml.CNOT(wires=[0, 1])
            qml.PhaseShift(theta[0], wires=0)
            return qml.expval(qml.PauliZ(0))

        phi = [0.5, 0.1]
        theta = [0.2]

        phi_t = tfe.Variable(phi)
        theta_t = tfe.Variable(theta)

        dcircuit = qml.grad(circuit, [0, 1])
        autograd_grad = dcircuit(phi, theta)

        dcircuit = tfe.gradients_function(circuit_tfe)
        tfe_grad = dcircuit(phi_t, theta_t)

        assert np.allclose(autograd_grad[0], tfe_grad[0], atol=tol, rtol=0)
        assert np.allclose(autograd_grad[1], tfe_grad[1], atol=tol, rtol=0)
