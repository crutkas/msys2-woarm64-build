#include <sqlite3.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void require(int ok, const char *message) {
    if (!ok) {
        fprintf(stderr, "SQLite helper API failure: %s\n", message);
        exit(1);
    }
}

static void *open_helper(const char *directory, const char *name) {
    char path[2048];
    require(snprintf(path, sizeof(path), "%s/msys-sqlite3%s-0.dll", directory, name) < sizeof(path),
            "helper path length");
    void *module = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!module) fprintf(stderr, "%s: %s\n", path, dlerror());
    require(module != NULL, "load native helper DLL");
    return module;
}

static void *symbol(void *module, const char *name) {
    void *address = dlsym(module, name);
    require(address != NULL, name);
    return address;
}

static int dump_text(const char *text, void *context) {
    return fputs(text, context) < 0 ? 1 : 0;
}

int main(int argc, char **argv) {
    require(argc == 4, "DLL directory, database and dump paths");
    void *cache = open_helper(argv[1], "pcachetrace");
    int (*activate)(FILE *) = (int (*)(FILE *))symbol(cache, "sqlite3PcacheTraceActivate");
    int (*deactivate)(void) = (int (*)(void))symbol(cache, "sqlite3PcacheTraceDeactivate");
    require(activate(stderr) == SQLITE_OK, "activate real page-cache trace before initialization");
    sqlite3 *db = NULL;
    require(sqlite3_open(argv[2], &db) == SQLITE_OK, "helper database");
    require(sqlite3_exec(db, "CREATE TABLE t(value); INSERT INTO t VALUES('native helper');"
                            "PRAGMA mmap_size=8388608;", NULL, NULL, NULL) == SQLITE_OK, "fixture SQL");
    void *normalize = open_helper(argv[1], "normalize");
    char *(*normalize_sql)(const char *) = (char *(*)(const char *))symbol(normalize, "sqlite3_normalize");
    char *first = normalize_sql(" SELECT 123, 'alpha'; ");
    char *second = normalize_sql("select 456,'beta';");
    require(first && second && strcmp(first, second) == 0 && strchr(first, '?'), "normalization semantics");
    sqlite3_free(first);
    sqlite3_free(second);
    void *warm = open_helper(argv[1], "mmapwarm");
    int (*warm_db)(sqlite3 *, const char *) = (int (*)(sqlite3 *, const char *))symbol(warm, "sqlite3_mmap_warm");
    require(warm_db(db, "main") == SQLITE_OK, "warm actual mmap database");
    void *dump = open_helper(argv[1], "dbdump");
    int (*dump_db)(sqlite3 *, const char *, const char *, int (*)(const char *, void *), void *) =
        (int (*)(sqlite3 *, const char *, const char *, int (*)(const char *, void *), void *))
        symbol(dump, "sqlite3_db_dump");
    FILE *stream = fopen(argv[3], "w+");
    require(stream != NULL, "dump output");
    require(dump_db(db, "main", NULL, dump_text, stream) == SQLITE_OK, "dump callback API");
    require(fflush(stream) == 0 && fseek(stream, 0, SEEK_SET) == 0, "rewind SQL dump");
    char text[4096] = {0};
    size_t count = fread(text, 1, sizeof(text) - 1, stream);
    require(count > 0 && strstr(text, "CREATE TABLE") && strstr(text, "native helper"), "dump content");
    require(fclose(stream) == 0, "close dump");
    require(sqlite3_close(db) == SQLITE_OK, "close helper database");
    void *vfs = open_helper(argv[1], "vfslog");
    int (*register_log)(const char *) = (int (*)(const char *))symbol(vfs, "sqlite3_register_vfslog");
    require(register_log(NULL) == SQLITE_OK, "register logging VFS");
    sqlite3_vfs *registered = sqlite3_vfs_find(NULL);
    require(sqlite3_open(argv[2], &db) == SQLITE_OK, "open through logging VFS");
    require(sqlite3_exec(db, "INSERT INTO t VALUES('logged');", NULL, NULL, NULL) == SQLITE_OK,
            "logging VFS transaction");
    require(sqlite3_close(db) == SQLITE_OK, "close logging VFS");
    require(sqlite3_vfs_unregister(registered) == SQLITE_OK, "unregister logging VFS");
    void *stdio_module = open_helper(argv[1], "sqlite3_stdio");
    require(sqlite3_shutdown() == SQLITE_OK, "shutdown traced page cache");
    require(deactivate() == SQLITE_OK, "restore original page-cache methods");
    void *modules[] = {stdio_module, vfs, dump, warm, normalize, cache};
    for (size_t i = 0; i < sizeof(modules) / sizeof(modules[0]); ++i) {
        require(dlclose(modules[i]) == 0, "unload helper DLL");
    }
    puts("sqlite-native-helper-apis-passed");
    return 0;
}
