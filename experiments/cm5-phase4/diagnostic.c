/* Local research diagnostic; never submit as an upstream QEMU contribution. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/spi/spidev.h>

static int failures;
static void result(const char *name, const char *status, int error, long bytes)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    printf("{\"test\":\"%s\",\"status\":\"%s\",\"errno\":%d,\"bytes\":%ld,\"monotonic_ns\":%lld}\n",
           name, status, error, bytes, (long long)t.tv_sec*1000000000+t.tv_nsec);
    fflush(stdout);
    if (!strcmp(status,"FAIL")) failures++;
}
static void storage(const char *path)
{
    unsigned char tx[4096], rx[4096];
    for (size_t i=0;i<sizeof(tx);i++) tx[i]=(i*31+7)%251;
    int fd=open(path,O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC,0600);
    int e=errno; ssize_t n=-1; int ok=0;
    if(fd>=0) {
        n=write(fd,tx,sizeof(tx)); e=errno;
        if(n==sizeof(tx) && !fsync(fd) && lseek(fd,0,SEEK_SET)==0) {
            n=read(fd,rx,sizeof(rx)); e=errno;
            ok=n==sizeof(rx) && !memcmp(tx,rx,sizeof(rx));
        }
        close(fd);
        /* Deliberately retain the created test file as evidence. */
    }
    result("file_fsync_readback",ok?"PASS":"FAIL",ok?0:e,n);
}
static void network_test(int type, const char *name, const char *port_env)
{
    const char *port=getenv(port_env);
    if(!port) { result(name,"NOT_TESTED",0,0); return; }
    int fd=socket(AF_INET,type|SOCK_NONBLOCK,0), e=errno, ok=0;
    ssize_t n=-1;
    if(fd>=0) {
        struct sockaddr_in a={.sin_family=AF_INET,.sin_port=htons(atoi(port))};
        inet_pton(AF_INET,"10.0.2.2",&a.sin_addr);
        int c=connect(fd,(struct sockaddr*)&a,sizeof(a)); e=errno;
        struct pollfd p={.fd=fd,.events=POLLOUT};
        if(!c || (errno==EINPROGRESS && poll(&p,1,2000)>0)) {
            socklen_t len=sizeof(e); e=0;
            if(!getsockopt(fd,SOL_SOCKET,SO_ERROR,&e,&len) && !e) {
                unsigned char tx[]={16,32,48,64},rx[4];
                n=send(fd,tx,4,MSG_NOSIGNAL); e=errno;
                p.events=POLLIN;
                if(n==4 && poll(&p,1,2000)>0) {
                    n=recv(fd,rx,4,0);e=errno;
                    ok=n==4 && !memcmp(tx,rx,4);
                } else e=ETIMEDOUT;
            }
        }
        close(fd);
    }
    result(name,ok?"PASS":"FAIL",ok?0:e,n);
}
int main(int argc,char **argv)
{
    if(argc!=5) { fprintf(stderr,"usage: diagnostic LOGS_NEW_FILE UART_OR_- SPI_OR_- DURATION_SECONDS\n"); return 2; }
    char *end; long duration=strtol(argv[4],&end,10);
    if(*end || duration<1 || duration>3600) return 2;
    result("startup","PASS",0,getpid());
    long page=sysconf(_SC_PAGESIZE);
    result("page_16k",page==16384?"PASS":"FAIL",0,page);
    void *lib=dlopen("libm.so.6",RTLD_NOW);
    double (*root)(double)=lib?(double(*)(double))dlsym(lib,"sqrt"):NULL;
    result("dynamic_library",root && root(81)==9?"PASS":"FAIL",0,0);
    if(lib) dlclose(lib);
    size_t size=1024*1024; unsigned char *b=malloc(size); int ok=b!=NULL;
    if(b) {
        for(size_t i=0;i<size;i++) b[i]=(i*13)%251;
        for(size_t i=0;i<size;i++) if(b[i]!=(i*13)%251) ok=0;
        free(b);
    }
    result("memory",ok?"PASS":"FAIL",0,size);
    storage(argv[1]);
    /* Optional native verified-FSW read; default Phase 4--8 CLI is unchanged. */
    const char *fsw_device=getenv("CM5_FSW_DEVICE");
    if(fsw_device) {
        const char *block=getenv("CM5_FSW_BLOCK");
        unsigned char data[4096];
        int fsw_fd=open(fsw_device,O_RDONLY|O_CLOEXEC);
        off_t offset=block?(off_t)strtoull(block,NULL,10)*4096:0;
        ssize_t got=fsw_fd>=0?pread(fsw_fd,data,sizeof(data),offset):-1;
        result("fsw_verified_read",got==sizeof(data)?"PASS":"FAIL",got<0?errno:0,got);
        if(fsw_fd>=0)close(fsw_fd);
    }
    errno=0; int fd=open("/cm5-deliberately-missing-file",O_RDONLY);
    result("missing_file",fd<0 && errno==ENOENT?"PASS":"FAIL",fd<0?errno:0,0);
    if(fd>=0)close(fd);
    network_test(SOCK_STREAM,"tcp_echo","CM5_TCP_PORT");
    network_test(SOCK_DGRAM,"udp_echo","CM5_UDP_PORT");
    if(getenv("CM5_ROOT_TEST")) {
        errno=0; fd=open("/media/root-ro/cm5-sealed-probe",O_WRONLY|O_CREAT|O_EXCL,0600);
        int e=errno;
        result("sealed_lower",fd<0 && e==EROFS?"PASS":"FAIL",fd<0?e:0,0);
        if(fd>=0)close(fd);
        fd=open("/etc/os-release",O_RDONLY); char contents[4096];
        ssize_t n=fd>=0?read(fd,contents,sizeof(contents)):-1;
        result("os_file_read",n>0?"PASS":"FAIL",n<0?errno:0,n);
        if(fd>=0)close(fd);
    }
    unsigned char tx[]={0x10,0x20,0x30,0x40},rx[4]={0};
    if(strcmp(argv[2],"-")) {
        fd=open(argv[2],O_RDWR|O_NOCTTY|O_NONBLOCK);
        int e=errno; ssize_t n=-1;
        if(fd>=0) {
            struct termios t;
            if(!tcgetattr(fd,&t)) { cfmakeraw(&t); t.c_cflag |= CLOCAL|CREAD; t.c_cflag &= ~CRTSCTS; tcsetattr(fd,TCSANOW,&t); tcflush(fd,TCIFLUSH); }
            n=write(fd,tx,4); e=errno;
            size_t used=0;
            while(n==4 && used<4) {
                struct pollfd p={.fd=fd,.events=POLLIN};
                if(poll(&p,1,5000)<=0) {e=ETIMEDOUT; break;}
                ssize_t r=read(fd,rx+used,4-used);
                if(r<=0) {e=errno;break;} used+=r;
            }
            ok=n==4 && used==4 && !memcmp(tx,rx,4);
            close(fd);
        } else ok=0;
        result("uart_loopback",ok?"PASS":"FAIL",ok?0:e,n);
    } else result("uart","UNSUPPORTED",0,0);
    if(strcmp(argv[3],"-")) {
        fd=open(argv[3],O_RDWR); int e=errno; int n=-1;
        if(fd>=0) {
            struct spi_ioc_transfer x={.tx_buf=(uintptr_t)tx,.rx_buf=(uintptr_t)rx,.len=4,
                                      .speed_hz=100000,.bits_per_word=8};
            n=ioctl(fd,SPI_IOC_MESSAGE(1),&x); e=errno; close(fd);
        }
        result("spi_loopback",n==4 && !memcmp(tx,rx,4)?"PASS":"FAIL",n<0?e:0,n);
    } else result("spi","UNSUPPORTED",0,0);
    result("i2c","UNSUPPORTED",0,0); result("gpio","UNSUPPORTED",0,0);
    for(long i=0;i<duration;i++) {
        struct timespec delay={.tv_sec=1};
        while(nanosleep(&delay,&delay) && errno==EINTR) {}
        result("heartbeat","PASS",0,i+1);
    }
    result("exit",failures?"FAIL":"PASS",0,failures);
    return failures?1:0;
}
