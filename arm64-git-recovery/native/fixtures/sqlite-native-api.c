#define SQLITE_ENABLE_SESSION 1
#define SQLITE_ENABLE_PREUPDATE_HOOK 1
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(sizeof(long) == 8, "MSYS LP64 long required");
_Static_assert(sizeof(void *) == 8, "ARM64 pointers required");

static void check(int value, const char *message) {
    if (!value) {
        fprintf(stderr, "SQLite native API failure: %s\n", message);
        exit(1);
    }
}

static void sql(sqlite3 *db, const char *text) {
    char *error = NULL;
    int rc = sqlite3_exec(db, text, NULL, NULL, &error);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "SQL failed (%d): %s: %s\n", rc, text, error ? error : sqlite3_errmsg(db));
        sqlite3_free(error);
        exit(1);
    }
}

static sqlite3_int64 scalar(sqlite3 *db, const char *text) {
    sqlite3_stmt *statement = NULL;
    check(sqlite3_prepare_v2(db, text, -1, &statement, NULL) == SQLITE_OK, text);
    check(sqlite3_step(statement) == SQLITE_ROW, "scalar row");
    sqlite3_int64 result = sqlite3_column_int64(statement, 0);
    check(sqlite3_step(statement) == SQLITE_DONE, "scalar done");
    check(sqlite3_finalize(statement) == SQLITE_OK, "scalar finalize");
    return result;
}

static int conflict(void *context, int reason, sqlite3_changeset_iter *iterator) {
    (void)context;
    (void)reason;
    (void)iterator;
    return SQLITE_CHANGESET_ABORT;
}

int main(int argc, char **argv) {
    sqlite3 *db = NULL, *copy = NULL;
    sqlite3_session *session = NULL;
    check(argc == 2, "private database path argument");
    check(sqlite3_libversion_number() == 3053004, "pinned SQLite version");
    check(sqlite3_threadsafe() == 1, "threadsafe library");
    check(sqlite3_open(argv[1], &db) == SQLITE_OK, "open file database");
    sql(db, "PRAGMA journal_mode=WAL; CREATE TABLE records(id INTEGER PRIMARY KEY,value TEXT);");
    check(sqlite3session_create(db, "main", &session) == SQLITE_OK, "session create");
    check(sqlite3session_attach(session, "records") == SQLITE_OK, "session attach");
    sql(db, "BEGIN; INSERT INTO records VALUES(1,'native'),(2,'arm64'),(3,'sqlite'); COMMIT;");
    check(scalar(db, "SELECT count(*) FROM records") == 3, "transaction row count");
    check(scalar(db, "SELECT sqrt(81)+pow(2,3)") == 17, "native floating point math");
    check(scalar(db, "SELECT json_extract('{\"answer\":42}','$.answer')") == 42, "JSON");
    sql(db, "CREATE VIRTUAL TABLE search USING fts5(value); INSERT INTO search VALUES('native arm64 sqlite');");
    check(scalar(db, "SELECT count(*) FROM search WHERE search MATCH 'arm64'") == 1, "FTS5");
    sql(db, "CREATE VIRTUAL TABLE bounds USING rtree(id,x0,x1); INSERT INTO bounds VALUES(1,0.5,2.5);");
    check(scalar(db, "SELECT count(*) FROM bounds WHERE x0<1 AND x1>2") == 1, "RTree floating point");
    check(scalar(db, "SELECT count(*)>0 FROM dbstat") == 1, "DBSTAT virtual table");
    check(scalar(db, "SELECT length(data)=4096 FROM sqlite_dbpage WHERE pgno=1") == 1, "DBPAGE virtual table");
    sql(db, "ANALYZE;");
    check(scalar(db, "SELECT count(*) FROM sqlite_schema WHERE name='sqlite_stat4'") == 1, "STAT4");
    check(sqlite3_open(":memory:", &copy) == SQLITE_OK, "open changeset target");
    sql(copy, "CREATE TABLE records(id INTEGER PRIMARY KEY,value TEXT);");
    int size = 0;
    void *changes = NULL;
    check(sqlite3session_changeset(session, &size, &changes) == SQLITE_OK && size > 0, "session changeset");
    check(sqlite3changeset_apply(copy, size, changes, NULL, conflict, NULL) == SQLITE_OK, "changeset apply");
    check(scalar(copy, "SELECT count(*) FROM records") == 3, "changeset semantic result");
    sqlite3_free(changes);
    sqlite3session_delete(session);
    sql(db, "UPDATE records SET value='updated' ORDER BY id LIMIT 1; DELETE FROM records ORDER BY id DESC LIMIT 1;");
    check(scalar(db, "SELECT count(*) FROM records") == 2, "update/delete limit");
    const char *datatype = NULL, *collation = NULL;
    int notnull = 0, primary = 0, autoincrement = 0;
    check(sqlite3_table_column_metadata(db, "main", "records", "id", &datatype, &collation,
                                       &notnull, &primary, &autoincrement) == SQLITE_OK && primary == 1,
          "column metadata");
    check(sqlite3_close(copy) == SQLITE_OK, "close target");
    check(sqlite3_close(db) == SQLITE_OK, "close database");
    printf("sqlite-native-api-passed version=%s long=%zu pointer=%zu\n",
           sqlite3_libversion(), sizeof(long), sizeof(void *));
    return 0;
}
