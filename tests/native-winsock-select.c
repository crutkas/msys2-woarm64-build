#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>

#include <stdio.h>

static int fail(const char *operation)
{
    fprintf(stderr, "%s failed: %d\n", operation, WSAGetLastError());
    return 1;
}

int main(void)
{
    WSADATA data;
    SOCKET listener = INVALID_SOCKET;
    SOCKET client = INVALID_SOCKET;
    SOCKET server = INVALID_SOCKET;
    struct sockaddr_in address = {0};
    int address_length = sizeof(address);
    u_long nonblocking = 1;
    fd_set sockets;
    struct timeval timeout = {5, 0};
    char sent = 'x';
    char received = 0;
    int result = 1;

    if (WSAStartup(MAKEWORD(2, 2), &data) != 0)
        return fail("WSAStartup");
    listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    client = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (listener == INVALID_SOCKET || client == INVALID_SOCKET)
        goto cleanup;
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(listener, (struct sockaddr *)&address, sizeof(address)) == SOCKET_ERROR
            || getsockname(listener, (struct sockaddr *)&address, &address_length) == SOCKET_ERROR
            || listen(listener, 1) == SOCKET_ERROR
            || ioctlsocket(client, FIONBIO, &nonblocking) == SOCKET_ERROR)
        goto cleanup;
    if (connect(client, (struct sockaddr *)&address, sizeof(address)) == SOCKET_ERROR
            && WSAGetLastError() != WSAEWOULDBLOCK)
        goto cleanup;

    FD_ZERO(&sockets);
    FD_SET(client, &sockets);
    if (select(0, NULL, &sockets, NULL, &timeout) != 1 || !FD_ISSET(client, &sockets))
        goto cleanup;

    timeout.tv_sec = 5;
    timeout.tv_usec = 0;
    FD_ZERO(&sockets);
    FD_SET(listener, &sockets);
    if (select(0, &sockets, NULL, NULL, &timeout) != 1 || !FD_ISSET(listener, &sockets))
        goto cleanup;
    server = accept(listener, NULL, NULL);
    if (server == INVALID_SOCKET
            || send(client, &sent, 1, 0) != 1
            || recv(server, &received, 1, 0) != 1
            || received != sent)
        goto cleanup;
    result = 0;

cleanup:
    if (result != 0)
        fail("native Winsock select probe");
    if (server != INVALID_SOCKET)
        closesocket(server);
    if (client != INVALID_SOCKET)
        closesocket(client);
    if (listener != INVALID_SOCKET)
        closesocket(listener);
    WSACleanup();
    return result;
}
