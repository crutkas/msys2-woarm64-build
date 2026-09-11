#include <db.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>

typedef int (*PRED)(void *);
static int calls, stats_calls, promote_after, start_error, stat_error;
static int reported_error, reported_timeout, wrong_master;

static int await_condition(PRED predicate, void *context, long limit)
{
    if (limit != 60) abort();
    for (int i = 0; i < 3; ++i)
        if (predicate(context)) return 1;
    return 0;
}

#include "db-channel-transition-under-test.h"

static int start(DB_ENV *env, int threads, u_int32_t flags)
{
    (void)env;
    if (threads != 0 || flags != DB_REP_MASTER) abort();
    ++calls;
    return start_error;
}

static int statistics(DB_ENV *env, DB_REP_STAT **result, u_int32_t flags)
{
    (void)env;
    if (flags != 0) abort();
    ++stats_calls;
    if (stat_error) return stat_error;
    *result = calloc(1, sizeof(**result));
    if (*result == NULL) abort();
    (*result)->st_status = calls >= promote_after ? DB_REP_MASTER : DB_REP_CLIENT;
    (*result)->st_env_id = 2;
    (*result)->st_master = wrong_master ? 3 : 2;
    return 0;
}

static void report_error(const DB_ENV *env, int error, const char *format, ...)
{
    (void)env; (void)format;
    reported_error = error;
}

static void report_timeout(const DB_ENV *env, const char *format, ...)
{
    (void)env; (void)format;
    ++reported_timeout;
}

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "master transition control failed at %d: %s\n", __LINE__, #expr); return 1; \
} } while (0)

int main(void)
{
    DB_ENV env = {0};
    env.repmgr_start = start;
    env.rep_stat = statistics;
    env.err = report_error;
    env.errx = report_timeout;

    promote_after = 1;
    CHECK(become_master(&env) == 0 && calls == 1 && stats_calls == 1);
    calls = stats_calls = 0; promote_after = 3;
    CHECK(become_master(&env) == 0 && calls == 3 && stats_calls == 3);
    calls = stats_calls = 0; promote_after = 4;
    CHECK(become_master(&env) == DB_TIMEOUT && calls == 3 && reported_timeout == 1);
    calls = stats_calls = 0; promote_after = 1; wrong_master = 1;
    CHECK(become_master(&env) == DB_TIMEOUT && calls == 3 && reported_timeout == 2);
    calls = stats_calls = 0; wrong_master = 0; start_error = EINVAL;
    CHECK(become_master(&env) == EINVAL && calls == 1 && stats_calls == 0 && reported_error == EINVAL);
    calls = stats_calls = 0; start_error = 0; stat_error = EIO;
    CHECK(become_master(&env) == EIO && calls == 1 && stats_calls == 1 && reported_error == EIO);
    puts("DB master transition controls PASS: success delayed timeout wrong-master start-error stat-error");
    return 0;
}
