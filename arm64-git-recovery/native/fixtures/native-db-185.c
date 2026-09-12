#include <db_185.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    DB *db = dbopen("compat185.db", O_CREAT | O_RDWR, 0600, DB_BTREE, NULL);
    DBT key = {(void *)"key", 3}, value = {(void *)"native185", 10}, found = {0};
    if (db == NULL || db->put(db, &key, &value, R_NOOVERWRITE) != 0 ||
        db->get(db, &key, &found, 0) != 0 || found.size != value.size ||
        memcmp(found.data, value.data, value.size) != 0 ||
        db->seq(db, &key, &found, R_FIRST) != 0 || db->close(db) != 0) {
        fputs("DB 185 assertion failed\n", stderr);
        return 1;
    }
    puts("DB 185 PASS: dbopen put get seq close");
    return 0;
}
