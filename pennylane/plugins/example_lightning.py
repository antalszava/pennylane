import pennylane as qml
import numpy as np

dev = qml.device('lightning.qubit', wires=2)

@qml.qnode(dev)
def circuit():
    qml.Hadamard(0)
    qml.CNOT(wires=[0, 1])
    return qml.expval(qml.PauliZ(0) @ qml.PauliZ(1))

print(circuit())
