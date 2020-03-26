#include <vector>
#include <iostream>


//compile with:
//g++ matrix_vector.cpp -o matrix_vector -lblas

extern "C" {
  void dgemv_(const char *TRANSA, const int *m, const int *n, double *alpha,
	      double *A, const int *k, double *v, const int *incv, double *beta,
	      double *b, const int *incb);
}


/**
 * Compute matrix vector A*v = b
 *
 * @param A matrix of size m by n
 * @param v vector of size n
 * @param m row size of matrix
 * @param n column size of matrix
 *
 * @return A*v
 */
std::vector<double> matvec(std::vector<double> &A, std::vector<double> &v,
                           int m, int n) {
  std::vector<double> b(m);
  char ytran = 'T';
  int dimM = m;
  int dimN = n;
  int incb = 1;
  int incv = 1;
  double alpha = 1.;
  double beta = 0.;
  dgemv_(&ytran, &dimN, &dimM, &alpha, A.data(), &dimN, v.data(), &incv, &beta,
         b.data(), &incb);
  return b;
}

int main(int argc, char *argv[]) {

  std::vector<double> A = {1,0,1,
			   0,2,0,
			   2,0,3};

  std::vector<double> v =
  { 1.1,
    2.2,
    3.3 };

  std::vector<double> b = matvec(A,v,3,3);

  for (int i = 0; i < b.size(); i++){
    std::cout << b[i] << " " << std::endl;
  }
  
  return 0;
}
