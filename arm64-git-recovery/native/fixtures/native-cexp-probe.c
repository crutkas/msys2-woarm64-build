#include <complex.h>
#include <math.h>
#include <stdio.h>

int main(void)
{
    double complex (*volatile operation)(double complex) = cexp;
    volatile double imaginary = 0.5;
    double complex input = imaginary * I;
    puts("calling actual cexp");
    fflush(stdout);
    double complex value = operation(input);
    printf("real=%.17g imaginary=%.17g\n", creal(value), cimag(value));
    return !(fabs(creal(value) - 0.8775825618903728) < 1e-12 &&
             fabs(cimag(value) - 0.479425538604203) < 1e-12);
}
