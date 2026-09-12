#include <pthread.h>

#ifdef __cplusplus
extern "C"
#endif
int db_native_link_probe(void)
{
    pthread_mutex_t mutex;
    return pthread_mutex_init(&mutex, 0) ||
        pthread_mutex_lock(&mutex) || pthread_mutex_unlock(&mutex) ||
        pthread_mutex_destroy(&mutex);
}
