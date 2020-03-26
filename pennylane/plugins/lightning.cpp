#include <numeric>                        // Standard library import for std::accumulate
#include "pybind11/pybind11.h"            // Pybind11 import to define Python bindings
#include "pybind11/stl.h"            // Pybind11 import to define Python bindings

#include "pybind11/numpy.h"            // Pybind11 import to define Python bindings

#include "blas_mat_vec/mat_vec.h"

namespace py = pybind11;

template <typename Sequence>
inline py::array_t<typename Sequence::value_type> as_pyarray(Sequence&& seq) {
    // Move entire object to heap (Ensure is moveable!). Memory handled via Python capsule
    Sequence* seq_ptr = new Sequence(std::move(seq));
    auto capsule = py::capsule(seq_ptr, [](void* p) { delete reinterpret_cast<Sequence*>(p); });
    return py::array(seq_ptr->size(),  // shape of array
                     seq_ptr->data(),  // c-style contiguous strides for Sequence
                     capsule           // numpy array references this parent
    );
}

typedef py::array_t<double, py::array::c_style | py::array::forcecast> numpy_array;

// Managing with the pybind convenient conversion
numpy_array matVecProduct(numpy_array& mat, numpy_array& vec, int& dim1, int& dim2)
{
        py::buffer_info info1 = mat.request();
        auto matPointer = static_cast<double *>(info1.ptr);

        py::buffer_info info2 = vec.request();
        auto vecPointer = static_cast<double *>(info2.ptr);

        // Need to cast mat and vec before

        std::vector<double> a = matvec(matPointer, vecPointer, dim1, dim2);
        // Need to cast b before returning
        // std::vector<double> a({1, 2,});
        auto b = as_pyarray(std::move(a));
        return b;
}


PYBIND11_MODULE(lightning, m)
{
    m.doc() = "Test module for xtensor python bindings";

    m.def("matVecProduct", matVecProduct, "Matrix vector product");
}
