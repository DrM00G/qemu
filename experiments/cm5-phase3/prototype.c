#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/timerfd.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
#include "interfaces.h"

static volatile sig_atomic_t running = 1;
static bool configuration, dynamic_library, computation, memory_ok, network_ok, storage_ok, timer_ok;

static void stop(int signo) { (void)signo; running = 0; }
static const char *boolean(bool value) { return value ? "true" : "false"; }
static double monotonic(void)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) { return -1; }
    return now.tv_sec + now.tv_nsec / 1e9;
}

static bool functions_passed(void)
{
    return configuration && dynamic_library && computation && memory_ok && network_ok && storage_ok && timer_ok;
}

static bool report(unsigned long beats, double elapsed, long page_size)
{
    const char *temporary = "/var/log/flight/prototype-result.tmp";
    FILE *file = fopen(temporary, "w");
    if (!file) { return false; }
    fprintf(file, "{\"schema\":1,\"started\":true,\"pid\":%ld,\"page_size\":%ld,"
            "\"systemd_service\":%s,\"heartbeats\":%lu,\"elapsed_seconds\":%.6f,"
            "\"sustained\":%s,\"functions_passed\":%s,\"capabilities\":{"
            "\"configuration\":%s,\"dynamic_library\":%s,\"computation\":%s,"
            "\"memory\":%s,\"virtual_network\":%s,\"writable_storage\":%s,\"timer\":%s},"
            "\"adapters\":{\"spi\":\"unsupported\",\"uart\":\"unsupported\"}}\n",
            (long)getpid(), page_size, boolean(getenv("INVOCATION_ID") != NULL), beats, elapsed,
            boolean(beats >= 50 && elapsed >= 4.9), boolean(functions_passed()),
            boolean(configuration), boolean(dynamic_library), boolean(computation),
            boolean(memory_ok), boolean(network_ok), boolean(storage_ok), boolean(timer_ok));
    bool success = fflush(file) == 0 && fsync(fileno(file)) == 0;
    if (fclose(file)) { success = false; }
    return success && rename(temporary, "/var/log/flight/prototype-result.json") == 0;
}

static bool probe_network(const char *endpoint)
{
    int port = 0;
    char path[256];
    if (!endpoint || sscanf(endpoint, "http://10.0.2.2:%d/%255s", &port, path) != 2 || port < 1 || port > 65535) {
        return false;
    }
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) { return false; }
    struct timeval timeout = { .tv_sec = 10, .tv_usec = 0 };
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    struct sockaddr_in address = { .sin_family = AF_INET, .sin_port = htons((uint16_t)port) };
    inet_pton(AF_INET, "10.0.2.2", &address.sin_addr);
    bool success = connect(fd, (struct sockaddr *)&address, sizeof(address)) == 0;
    char request[512], response[4096];
    int length = snprintf(request, sizeof(request), "GET /%s HTTP/1.0\r\nHost: 10.0.2.2\r\nConnection: close\r\n\r\n", path);
    int sent = 0;
    while (success && sent < length) {
        ssize_t count = send(fd, request + sent, (size_t)(length - sent), MSG_NOSIGNAL);
        if (count <= 0) { success = false; break; }
        sent += (int)count;
    }
    size_t used = 0;
    while (success && used < sizeof(response) - 1) {
        ssize_t count = recv(fd, response + used, sizeof(response) - 1 - used, 0);
        if (count < 0) { success = false; break; }
        if (count == 0) { break; }
        used += (size_t)count;
    }
    response[used] = 0;
    char *body = strstr(response, "\r\n\r\n");
    success = success && strstr(response, " 200 ") && body &&
              strcmp(body + 4, "cm5-phase1-virtual-network-probe-v1\n") == 0;
    close(fd);
    return success;
}

int main(int argc, char **argv)
{
    bool once = argc == 2 && strcmp(argv[1], "--once") == 0;
    if (argc > 1 && !once) { fprintf(stderr, "usage: %s [--once]\n", argv[0]); return 2; }
    signal(SIGTERM, stop);
    signal(SIGINT, stop);
    long page_size = sysconf(_SC_PAGESIZE);
    printf("FSW_STARTED {\"pid\":%ld,\"page_size\":%ld}\n", (long)getpid(), page_size);
    fflush(stdout);
    char config[4096];
    FILE *file = fopen("/opt/fsw/config.json", "r");
    size_t size = file ? fread(config, 1, sizeof(config) - 1, file) : 0;
    if (file) { fclose(file); }
    config[size] = 0;
    char *interval = strstr(config, "\"interval_ms\"");
    int interval_ms = interval && strchr(interval, ':') ? atoi(strchr(interval, ':') + 1) : 0;
    configuration = size > 0 && interval_ms == 100 && strstr(config, "/var/log/flight") != NULL;
    void *library = dlopen("/opt/fsw/libflightmath.so", RTLD_NOW | RTLD_LOCAL);
    void *math = dlopen("libm.so.6", RTLD_NOW | RTLD_LOCAL);
    uint64_t (*square_sum)(unsigned int) = library ? (uint64_t (*)(unsigned int))dlsym(library, "flight_square_sum") : NULL;
    double (*square_root)(double) = math ? (double (*)(double))dlsym(math, "sqrt") : NULL;
    dynamic_library = square_sum && square_root;
    volatile uint64_t value = 0;
    for (uint64_t i = 0; i < 100000; ++i) { value += i * i; }
    computation = dynamic_library && value == UINT64_C(333328333350000) &&
                  square_sum(1000) == UINT64_C(332833500) && square_root(81.0) == 9.0;
    size_t bytes = 16 * 1024 * 1024;
    unsigned char *buffer = malloc(bytes);
    memory_ok = buffer && page_size > 0;
    if (memory_ok) {
        for (size_t offset = 0; offset < bytes; offset += (size_t)page_size) { buffer[offset] = (unsigned char)((offset / (size_t)page_size) % 251); }
        for (size_t offset = 0; offset < bytes; offset += (size_t)page_size) {
            if (buffer[offset] != (unsigned char)((offset / (size_t)page_size) % 251)) { memory_ok = false; }
        }
    }
    free(buffer);
    file = fopen("/var/log/flight/prototype-state.txt", "w+");
    storage_ok = false;
    if (file) {
        char state[64];
        fputs("synthetic flight state v1\n", file);
        bool synced = fflush(file) == 0 && fsync(fileno(file)) == 0;
        rewind(file);
        storage_ok = synced && fgets(state, sizeof(state), file) && strcmp(state, "synthetic flight state v1\n") == 0;
        fclose(file);
    }
    network_ok = probe_network(getenv("PHASE3_ENDPOINT"));
    int timer = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC);
    struct itimerspec period = { .it_interval = { .tv_sec = 0, .tv_nsec = 100000000 },
                                 .it_value = { .tv_sec = 0, .tv_nsec = 100000000 } };
    timer_ok = timer >= 0 && timerfd_settime(timer, 0, &period, NULL) == 0;
    double started = monotonic();
    if (!functions_passed()) {
        report(0, 0, page_size);
        fprintf(stderr, "FSW_FAILURE: inspect per-capability result in LOGS\n");
        return 1;
    }
    FILE *heartbeat = fopen("/var/log/flight/heartbeat.jsonl", "a");
    if (!heartbeat) { storage_ok = false; report(0, 0, page_size); return 1; }
    unsigned long beats = 0;
    while (running) {
        uint64_t expirations;
        ssize_t received = read(timer, &expirations, sizeof(expirations));
        if (received < 0 && errno == EINTR) { continue; }
        if (received != sizeof(expirations)) { timer_ok = false; break; }
        ++beats;
        double elapsed = monotonic() - started;
        if (fprintf(heartbeat, "{\"pid\":%ld,\"beat\":%lu,\"elapsed_seconds\":%.6f,\"expirations\":%" PRIu64 "}\n",
                    (long)getpid(), beats, elapsed, expirations) < 0 || fflush(heartbeat)) {
            storage_ok = false;
            break;
        }
        if (beats % 50 == 0) {
            if (!report(beats, elapsed, page_size)) { storage_ok = false; break; }
            if (beats == 50) { printf("FSW_FUNCTIONS_PASS {\"heartbeats\":50,\"elapsed_seconds\":%.6f}\n", elapsed); fflush(stdout); }
            if (once) { break; }
        }
    }
    report(beats, monotonic() - started, page_size);
    fclose(heartbeat);
    close(timer);
    if (library) { dlclose(library); }
    if (math) { dlclose(math); }
    return functions_passed() ? 0 : 1;
}
