/* Host-only deliberately mocked EGL/export/sync path; NEVER hardware evidence. */
#define _GNU_SOURCE
#define eglQueryString mock_eglQueryString
#define eglGetProcAddress mock_eglGetProcAddress
#define ioctl mock_ioctl
#define poll mock_poll
#include "sl101-wpe-readback.c"
#undef eglQueryString
#undef eglGetProcAddress
#undef ioctl
#undef poll

#include <stdarg.h>
#include <stdio.h>

static int source_fd=-1;
static int source_pitch=4100;
static uint64_t source_modifier=0;
static int fence_status=1;

static EGLBoolean EGLAPIENTRY fake_query(EGLDisplay d, EGLImageKHR i,
                                         int *f, int *p, EGLuint64KHR *m)
{
    (void)d;(void)i;
    *f=0x34325258; *p=1; *m=source_modifier;
    return EGL_TRUE;
}
static EGLBoolean EGLAPIENTRY fake_export(EGLDisplay d, EGLImageKHR i,
                                         int *fd, EGLint *pitch, EGLint *off)
{
    (void)d;(void)i;
    *fd=dup(source_fd); *pitch=source_pitch; *off=0;
    return *fd>=0 ? EGL_TRUE : EGL_FALSE;
}
const char * mock_eglQueryString(EGLDisplay display, EGLint name)
{
    (void)display; (void)name;
    return "EGL_KHR_image_base EGL_MESA_image_dma_buf_export";
}
__eglMustCastToProperFunctionPointerType EGLAPIENTRY
mock_eglGetProcAddress(const char *name)
{
    if (!strcmp(name,"eglExportDMABUFImageQueryMESA"))
        return (__eglMustCastToProperFunctionPointerType)fake_query;
    if (!strcmp(name,"eglExportDMABUFImageMESA"))
        return (__eglMustCastToProperFunctionPointerType)fake_export;
    return NULL;
}
int mock_ioctl(int fd, unsigned long request, ...)
{
    va_list args; void *arg;
    (void)fd;
    va_start(args,request); arg=va_arg(args,void *); va_end(args);
    if (request == SYNC_IOC_FILE_INFO) {
        struct sync_file_info *info=arg;
        info->status=fence_status; info->num_fences=1;
        return 0;
    }
    if (request == DMA_BUF_IOCTL_SYNC) return 0;
    errno=EINVAL; return -1;
}
int mock_poll(struct pollfd *fds, nfds_t nfds, int timeout)
{
    (void)timeout;
    if (nfds!=1) return -1;
    fds[0].revents=POLLIN;
    return 1;
}

int main(void)
{
    FILE *f=tmpfile();
    if (!f) return 10;
    source_fd=fileno(f);
    unsigned char row[4100]={0};
    for (size_t i=0;i<4096;i+=4) {
        row[i]=0x11; row[i+1]=0x22; row[i+2]=0x33; row[i+3]=0xff;
    }
    for (int y=0;y<720;y++)
        if (fwrite(row,1,4100,f)!=4100) return 11;
    fflush(f);

    struct sl101_rb_snapshot out={0};
    enum sl101_rb_result result=sl101_rb_readback(
        (EGLDisplay)(uintptr_t)1,(EGLImageKHR)(uintptr_t)1,1024,720,source_fd,&out);
    if (result!=SL101_RB_OK_CONDITIONAL || out.len!=1024u*720u*4 ||
        out.metadata.pitch!=4100 || out.metadata.modifier!=0 ||
        out.bytes[0]!=0x11 || out.bytes[1]!=0x22 ||
        out.bytes[4]!=0x11 || out.bytes[4096]!=0x11)
        return 12;
    sl101_rb_free(&out);
    if (out.bytes || out.len) return 13;

    source_modifier=0x100000000000001ull;
    result=sl101_rb_readback((EGLDisplay)(uintptr_t)1,
        (EGLImageKHR)(uintptr_t)1,1024,720,source_fd,&out);
    if (result!=SL101_RB_UNSUPPORTED) return 14;
    source_modifier=0;
    fence_status=0;
    result=sl101_rb_readback((EGLDisplay)(uintptr_t)1,
        (EGLImageKHR)(uintptr_t)1,1024,720,source_fd,&out);
    if (result!=SL101_RB_SYNC_FAILED) return 15;
    fclose(f);
    puts("MOCK_LINEAR_COPY_PASS non64_pitch=4100 modifier_reject=PASS fence_reject=PASS");
    return 0;
}
