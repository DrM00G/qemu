/* Guest-only read-only loop attachment for the minimal preserved initramfs. */
#include <fcntl.h>
#include <linux/loop.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    struct loop_config config = { 0 };
    struct stat st;
    int data, loop, result;

    if (argc != 3) {
        return 2;
    }
    data = open(argv[2], O_RDONLY | O_CLOEXEC);
    loop = open(argv[1], O_RDWR | O_CLOEXEC);
    if (data < 0 || loop < 0 || fstat(data, &st) || !S_ISREG(st.st_mode)) {
        return 3;
    }
    config.fd = data;
    config.info.lo_flags = LO_FLAGS_READ_ONLY;
    result = ioctl(loop, LOOP_CONFIGURE, &config);
    close(data);
    close(loop);
    return result ? 4 : 0;
}
