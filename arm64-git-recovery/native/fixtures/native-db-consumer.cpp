#include <db_cxx.h>
#include <cerrno>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <cstdio>
#include <unistd.h>
#define NOMINMAX
#include <windows.h>

static_assert(sizeof(void *) == 8 && sizeof(long) == 8, "MSYS LP64 required");

static void require(bool value)
{
    if (!value) throw std::runtime_error("DB C++ API assertion failed");
}

int main(int argc, char **argv)
{
    if (argc > 2 || (argc == 2 && std::strcmp(argv[1], "data-only") != 0 && std::strcmp(argv[1], "hold") != 0)) {
        std::cerr << "usage: native-db-consumer [data-only|hold]" << std::endl;
        return 2;
    }
    try {
        DbEnv env(u_int32_t{0});
        env.open(".", DB_CREATE | DB_INIT_MPOOL | DB_INIT_LOCK | DB_INIT_LOG |
            DB_INIT_TXN | DB_PRIVATE, 0700);
        Db db(&env, 0);
        db.open(nullptr, "cpp.db", nullptr, DB_BTREE, DB_CREATE | DB_AUTO_COMMIT, 0600);
        char key_data[] = "cpp-key", value_data[] = "native-cxx-value";
        Dbt key(key_data, sizeof(key_data)), value(value_data, sizeof(value_data)), result;
        DbTxn *txn = nullptr;
        env.txn_begin(nullptr, &txn, 0);
        require(db.put(txn, &key, &value, DB_NOOVERWRITE) == 0);
        txn->abort();
        require(db.get(nullptr, &key, &result, 0) == DB_NOTFOUND);
        env.txn_begin(nullptr, &txn, 0);
        require(db.put(txn, &key, &value, DB_NOOVERWRITE) == 0);
        txn->commit(0);
        require(db.get(nullptr, &key, &result, 0) == 0);
        require(result.get_size() == sizeof(value_data) &&
            std::memcmp(result.get_data(), value_data, sizeof(value_data)) == 0);
        Dbc *cursor = nullptr;
        db.cursor(nullptr, &cursor, 0);
        require(cursor->get(&key, &result, DB_FIRST) == 0);
        require(cursor->get(&key, &result, DB_NEXT) == DB_NOTFOUND);
        cursor->close();
        db.close(0);
        env.close(0);
        std::cout << "DB C++ DATA PASS: LP64 Btree transaction cursor" << std::endl;
        if (argc == 2 && std::strcmp(argv[1], "data-only") == 0) return 0;
        bool caught = false;
        try {
            Db absent(nullptr, 0);
            absent.open(nullptr, "does-not-exist.db", nullptr, DB_BTREE, DB_RDONLY, 0);
        } catch (const DbException &error) {
            require(error.get_errno() == ENOENT);
            caught = true;
        }
        require(caught);
        std::cout << "DB C++ PASS: LP64 Btree transaction cursor DbException" << std::endl;
        if (argc == 2) {
            FILE *ready = std::fopen("ready", "w");
            require(ready != nullptr);
            require(std::fprintf(ready, "%lu\n", static_cast<unsigned long>(GetCurrentProcessId())) > 0);
            require(std::fclose(ready) == 0);
            for (int i = 0; i < 3000; ++i) {
                if (access("continue", F_OK) == 0) return 0;
                usleep(10000);
            }
            throw std::runtime_error("Native module observer did not release the held fixture");
        }
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << std::endl;
        return 1;
    }
}
