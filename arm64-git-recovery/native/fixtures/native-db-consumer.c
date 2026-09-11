#define DB_DBM_HSEARCH 1
#include <db.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define REQUIRE(expr) do { if (!(expr)) { \
    fprintf(stderr, "DB C assertion failed at %d: %s\n", __LINE__, #expr); return 1; \
} } while (0)

_Static_assert(sizeof(void *) == 8 && sizeof(long) == 8, "MSYS LP64 required");

static int database(DBTYPE type, const char *filename)
{
    DB_ENV *env = NULL;
    DB *db = NULL;
    DB_TXN *txn = NULL;
    DBC *cursor = NULL;
    DBT key = {0}, data = {0}, found = {0};
    char value[] = "native-arm64-db";
    int count = 0, result;
    REQUIRE(db_env_create(&env, 0) == 0);
    REQUIRE(env->open(env, ".", DB_CREATE | DB_INIT_MPOOL | DB_INIT_LOCK |
        DB_INIT_LOG | DB_INIT_TXN | DB_PRIVATE, 0700) == 0);
    REQUIRE(db_create(&db, env, 0) == 0);
    REQUIRE(db->open(db, NULL, filename, NULL, type, DB_CREATE | DB_AUTO_COMMIT, 0600) == 0);
    key.data = (void *)"key"; key.size = 3;
    data.data = value; data.size = sizeof(value);
    REQUIRE(env->txn_begin(env, NULL, &txn, 0) == 0);
    REQUIRE(db->put(db, txn, &key, &data, DB_NOOVERWRITE) == 0);
    REQUIRE(txn->abort(txn) == 0);
    REQUIRE(db->get(db, NULL, &key, &found, 0) == DB_NOTFOUND);
    REQUIRE(env->txn_begin(env, NULL, &txn, 0) == 0);
    REQUIRE(db->put(db, txn, &key, &data, DB_NOOVERWRITE) == 0);
    REQUIRE(db->put(db, txn, &key, &data, DB_NOOVERWRITE) == DB_KEYEXIST);
    REQUIRE(txn->commit(txn, 0) == 0);
    REQUIRE(db->get(db, NULL, &key, &found, 0) == 0);
    REQUIRE(found.size == data.size && memcmp(found.data, value, data.size) == 0);
    REQUIRE(db->cursor(db, NULL, &cursor, 0) == 0);
    while ((result = cursor->get(cursor, &key, &found, DB_NEXT)) == 0) ++count;
    REQUIRE(result == DB_NOTFOUND && count == 1);
    REQUIRE(cursor->close(cursor) == 0);
    REQUIRE(db->close(db, 0) == 0);
    REQUIRE(db_create(&db, env, 0) == 0);
    REQUIRE(db->open(db, NULL, filename, NULL, type, DB_AUTO_COMMIT, 0600) == 0);
    key.data = (void *)"key"; key.size = 3;
    REQUIRE(db->get(db, NULL, &key, &found, 0) == 0 && found.size == sizeof(value));
    REQUIRE(db->del(db, NULL, &key, DB_AUTO_COMMIT) == 0);
    REQUIRE(db->close(db, 0) == 0);
    REQUIRE(env->close(env, 0) == 0);
    return 0;
}

int main(void)
{
    int major, minor, patch;
    DBM *dbm;
    datum key = {(char *)"key", 3}, value = {(char *)"dbm-native", 11}, found;
    db_version(&major, &minor, &patch);
    REQUIRE(major == 6 && minor == 2 && patch == 32);
    REQUIRE(database(DB_BTREE, "btree.db") == 0);
    REQUIRE(database(DB_HASH, "hash.db") == 0);
    dbm = dbm_open("compat-dbm", O_CREAT | O_RDWR, 0600);
    REQUIRE(dbm != NULL);
    REQUIRE(dbm_store(dbm, key, value, DBM_INSERT) == 0);
    found = dbm_fetch(dbm, key);
    REQUIRE(found.dsize == value.dsize && memcmp(found.dptr, value.dptr, value.dsize) == 0);
    REQUIRE(dbm_firstkey(dbm).dptr != NULL);
    REQUIRE(dbm_delete(dbm, key) == 0 && dbm_fetch(dbm, key).dptr == NULL);
    dbm_close(dbm);
    puts("DB C PASS: LP64 version Btree Hash txn-abort txn-commit cursor reopen DBM");
    return 0;
}
