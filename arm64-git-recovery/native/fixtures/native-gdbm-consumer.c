#include <gdbm.h>
#include <gdbm/ndbm.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <windows.h>

_Static_assert(sizeof(long) == 8, "MSYS LP64 long required");
_Static_assert(sizeof(void *) == 8, "Native 64-bit pointers required");
_Static_assert(sizeof(FILETIME) == 8, "Windows FILETIME layout required");
_Static_assert(GDBM_VERSION_MAJOR == 1 && GDBM_VERSION_MINOR == 26,
               "GDBM 1.26 headers required");

static unsigned int checks;

static void require(int condition, const char *operation)
{
    ++checks;
    if (!condition) {
        fprintf(stderr, "FAIL %s: errno=%d gdbm_errno=%d\n",
                operation, errno, (int)gdbm_errno);
        exit(1);
    }
}

static void native_database(void)
{
    GDBM_FILE db = gdbm_open("native-api.gdbm", 0, GDBM_NEWDB, 0600, NULL);
    require(db != NULL, "gdbm_open create");
    const char payload[] = {'n', 'a', 't', 'i', 'v', 'e', '\0', '6', '4'};
    for (unsigned int i = 0; i != 64; ++i) {
        char key_text[32];
        int length = snprintf(key_text, sizeof(key_text), "key-%02u", i);
        datum key = {key_text, length};
        datum value = {(char *)payload, sizeof(payload)};
        require(gdbm_store(db, key, value, GDBM_INSERT) == 0, "gdbm_store insert");
        datum fetched = gdbm_fetch(db, key);
        require(fetched.dptr != NULL && fetched.dsize == sizeof(payload)
                && memcmp(fetched.dptr, payload, sizeof(payload)) == 0,
                "gdbm_fetch binary payload");
        free(fetched.dptr);
    }
    unsigned int seen = 0;
    for (datum key = gdbm_firstkey(db); key.dptr != NULL;) {
        datum next = gdbm_nextkey(db, key);
        ++seen;
        free(key.dptr);
        key = next;
    }
    require(seen == 64, "gdbm_firstkey/nextkey count");
    datum key = {"key-00", 6};
    datum replacement = {"replacement", 11};
    require(gdbm_store(db, key, replacement, GDBM_REPLACE) == 0, "gdbm_store replace");
    require(gdbm_sync(db) == 0, "gdbm_sync");
    require(gdbm_close(db) == 0, "gdbm_close writer");
    db = gdbm_open("native-api.gdbm", 0, GDBM_WRITER, 0, NULL);
    require(db != NULL, "gdbm_open persistent database");
    datum fetched = gdbm_fetch(db, key);
    require(fetched.dptr != NULL && fetched.dsize == replacement.dsize
            && memcmp(fetched.dptr, replacement.dptr, replacement.dsize) == 0,
            "gdbm_fetch after reopen");
    free(fetched.dptr);
    require(gdbm_delete(db, key) == 0 && !gdbm_exists(db, key), "gdbm_delete");
    fetched = gdbm_fetch(db, key);
    require(fetched.dptr == NULL && gdbm_errno == GDBM_ITEM_NOT_FOUND, "deleted key absent");
    require(gdbm_close(db) == 0, "gdbm_close final");
}

static void ndbm_database(void)
{
    DBM *db = dbm_open("native-ndbm", O_RDWR | O_CREAT | O_TRUNC, 0600);
    require(db != NULL, "dbm_open create");
    for (unsigned int i = 0; i != 32; ++i) {
        char key_text[32];
        int length = snprintf(key_text, sizeof(key_text), "ndbm-%02u", i);
        datum key = {key_text, length};
        datum value = {"compat\0value", 12};
        require(dbm_store(db, key, value, DBM_INSERT) == 0, "dbm_store insert");
        datum fetched = dbm_fetch(db, key);
        require(fetched.dptr != NULL && fetched.dsize == value.dsize
                && memcmp(fetched.dptr, value.dptr, value.dsize) == 0,
                "dbm_fetch binary payload");
    }
    unsigned int seen = 0;
    for (datum key = dbm_firstkey(db); key.dptr != NULL; key = dbm_nextkey(db))
        ++seen;
    require(seen == 32 && !dbm_error(db), "dbm iteration");
    dbm_close(db);
    db = dbm_open("native-ndbm", O_RDWR, 0);
    require(db != NULL, "dbm_open persistent database");
    datum key = {"ndbm-00", 7};
    datum fetched = dbm_fetch(db, key);
    require(fetched.dptr != NULL && fetched.dsize == 12, "dbm_fetch after reopen");
    require(dbm_delete(db, key) == 0, "dbm_delete");
    require(dbm_fetch(db, key).dptr == NULL && !dbm_error(db), "deleted NDBM key absent");
    dbm_close(db);
}

static void verify_moved_databases(void)
{
    GDBM_FILE db = gdbm_open("native-api.gdbm", 0, GDBM_READER, 0, NULL);
    require(db != NULL, "reopen moved GDBM database");
    unsigned int count = 0;
    for (datum key = gdbm_firstkey(db); key.dptr != NULL;) {
        datum next = gdbm_nextkey(db, key);
        ++count;
        free(key.dptr);
        key = next;
    }
    require(count == 63, "moved GDBM persistent record count");
    datum key = {"key-01", 6};
    datum value = gdbm_fetch(db, key);
    require(value.dptr != NULL && value.dsize == 9
            && memcmp(value.dptr, "native\0" "64", 9) == 0, "moved GDBM persisted bytes");
    free(value.dptr);
    require(gdbm_close(db) == 0, "close moved GDBM reader");
    DBM *compat = dbm_open("native-ndbm", O_RDONLY, 0);
    require(compat != NULL, "reopen moved NDBM database");
    count = 0;
    for (key = dbm_firstkey(compat); key.dptr != NULL; key = dbm_nextkey(compat))
        ++count;
    require(count == 31, "moved NDBM persistent record count");
    key.dptr = "ndbm-01";
    key.dsize = 7;
    value = dbm_fetch(compat, key);
    require(value.dptr != NULL && value.dsize == 12
            && memcmp(value.dptr, "compat\0value", 12) == 0, "moved NDBM persisted bytes");
    dbm_close(compat);
}

int main(int argc, char **argv)
{
    require(argc == 1 || argc == 3 || (argc == 4 && strcmp(argv[3], "--existing") == 0),
            "optional ready, release, and moved-data check");
    require(gdbm_version_number[0] == GDBM_VERSION_MAJOR
            && gdbm_version_number[1] == GDBM_VERSION_MINOR
            && gdbm_version_number[2] == GDBM_VERSION_PATCH,
            "installed header/runtime version identity");
    if (argc == 4)
        verify_moved_databases();
    native_database();
    ndbm_database();
    if (argc >= 3) {
        FILETIME creation, end, kernel, user;
        require(GetProcessTimes(GetCurrentProcess(), &creation, &end, &kernel, &user) != 0,
                "process creation identity");
        FILE *ready = fopen(argv[1], "wx");
        require(ready != NULL, "fresh module-observation handshake");
        unsigned long long birth = ((unsigned long long)creation.dwHighDateTime << 32)
                                 | creation.dwLowDateTime;
        require(fprintf(ready, "%lu %llu\n", (unsigned long)GetCurrentProcessId(), birth) > 0,
                "write process generation");
        require(fclose(ready) == 0, "flush process generation");
        unsigned int waits;
        for (waits = 0; waits != 2400; ++waits) {
            if (access(argv[2], F_OK) == 0)
                break;
            if (errno != ENOENT)
                require(0, "release-file lookup");
            usleep(50000);
        }
        require(waits != 2400, "bounded module-observation release");
    }
    printf("PASS native GDBM and NDBM: checks=%u long=%zu pointer=%zu version=%s\n",
           checks, sizeof(long), sizeof(void *), gdbm_version);
    return 0;
}
