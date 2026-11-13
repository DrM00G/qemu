/* Local guest-only helper: bounded read, no mounts, no writes to storage. */
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    unsigned char buf[4096];
    char *end;
    struct stat st;
    uint64_t sector;
    int fd;
    ssize_t n;
    size_t done = 0;

    if (argc != 3) {
        return 2;
    }
    errno = 0;
    sector = strtoull(argv[2], &end, 10);
    if (errno || *end || sector > 30535672) {
        return 2;
    }
    fd = open(argv[1], O_RDONLY | O_CLOEXEC);
    if (fd < 0 || fstat(fd, &st) || !S_ISBLK(st.st_mode)) {
        return 3;
    }
    n = pread(fd, buf, sizeof(buf), sector * 512);
    close(fd);
    if (n != sizeof(buf)) {
        return 4;
    }
    while (done < sizeof(buf)) {
        n = write(STDOUT_FILENO, buf + done, sizeof(buf) - done);
        if (n <= 0) {
            return 5;
        }
        done += n;
    }
    return 0;
}
