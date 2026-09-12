#include <cstdio>
#include <vector>

extern "C" int pipeline_value(void);

int main()
{
    std::vector<int> values{pipeline_value(), 8};
    if (values[0] + values[1] != 50)
        return 1;
    std::puts("PASS: native ARM64 C/C++ package executable reached main");
    return 0;
}
