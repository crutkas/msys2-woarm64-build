#include <db.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/select.h>
#include <time.h>
#include <windows.h>

struct __env;
extern void __os_yield(struct __env *, unsigned long, unsigned long);

static double now(void)
{
    LARGE_INTEGER value, frequency;
    if (!QueryPerformanceCounter(&value) || !QueryPerformanceFrequency(&frequency))
        abort();
    return (double)value.QuadPart / (double)frequency.QuadPart;
}

static int compare(const void *a, const void *b)
{
    double left = *(const double *)a, right = *(const double *)b;
    return (left > right) - (left < right);
}

int main(void)
{
    enum { SAMPLES = 128 };
    const unsigned long requests[] = {0, 1, 2, 1000, 25000};
    typedef LONG (NTAPI *QueryTimerResolution)(PULONG, PULONG, PULONG);
    QueryTimerResolution query = (QueryTimerResolution)GetProcAddress(
        GetModuleHandleW(L"ntdll.dll"), "NtQueryTimerResolution");
    ULONG minimum, maximum, current;
    int major, minor, patch;
    db_version(&major, &minor, &patch);
    if (major != 6 || minor != 2 || patch != 32 || query == NULL ||
        query(&minimum, &maximum, &current) < 0)
        return 1;
    printf("timer_resolution_100ns min=%lu max=%lu current=%lu\n",
        (unsigned long)minimum, (unsigned long)maximum, (unsigned long)current);
    for (int method = 0; method < 2; ++method) {
        for (unsigned int request = 0; request < sizeof(requests) / sizeof(requests[0]); ++request) {
            double samples[SAMPLES], total = 0;
            for (int i = 0; i < SAMPLES; ++i) {
                double start = now();
                if (method == 0)
                    __os_yield(NULL, 0, requests[request]);
                else {
                    struct timeval timeout = {0, (long)requests[request] + 1};
                    if (select(0, NULL, NULL, NULL, &timeout) != 0) {
                        perror("select");
                        return 2;
                    }
                }
                samples[i] = (now() - start) * 1000;
                total += samples[i];
            }
            qsort(samples, SAMPLES, sizeof(double), compare);
            printf("method=%s request_us=%lu samples=%d min_ms=%.6f median_ms=%.6f p95_ms=%.6f mean_ms=%.6f total_ms=%.6f\n",
                method == 0 ? "db_yield" : "select_plus_one", requests[request], SAMPLES,
                samples[0], samples[SAMPLES / 2], samples[(SAMPLES * 95) / 100], total / SAMPLES, total);
            fflush(stdout);
        }
    }
    puts("DB YIELD TIMING COMPLETE: no timer-resolution, mutex-policy or workload changes");
    return 0;
}
