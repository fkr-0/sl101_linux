/* scripts/sl101-grate-egl-probe.c
 * EGL/GLES2 pbuffer discriminant. This is NOT video output qualification.
 * Compile for ARM/musl on the target with normal EGL/GLES2/Wayland headers;
 * execute only with the SHA-pinned private Mesa runtime under active Sway.
 */
#include <dlfcn.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <wayland-client.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef EGL_PLATFORM_WAYLAND_EXT
#define EGL_PLATFORM_WAYLAND_EXT 0x31D8
#endif

static int fail(const char *stage, int code) {
    fprintf(stderr, "FAIL %s EGL=0x%04x GL=0x%04x\n",
            stage, (unsigned)eglGetError(), (unsigned)glGetError());
    return code;
}

int main(int argc, char **argv) {
    struct wl_display *wl;
    EGLDisplay display;
    EGLConfig config;
    EGLint count = 0, major = 0, minor = 0;
    EGLSurface surface = EGL_NO_SURFACE;
    EGLContext context;
    GLuint framebuffer = 0, texture = 0;
    unsigned char px[4] = {0, 0, 0, 0};
    const EGLint cfg[] = {
        EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE,
        EGL_OPENGL_ES2_BIT, EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8,
        EGL_BLUE_SIZE, 8, EGL_NONE
    };
    const EGLint pb[] = {EGL_WIDTH, 64, EGL_HEIGHT, 64, EGL_NONE};
    const EGLint any_gles2[] = {EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                                EGL_NONE};
    const EGLint ctx[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
    int use_platform, load_desktop_gl;

    if (argc != 2 || (strcmp(argv[1], "native") &&
                       strcmp(argv[1], "platform") &&
                       strcmp(argv[1], "platform-glx"))) {
        fprintf(stderr, "usage: %s native|platform|platform-glx\n", argv[0]);
        return 2;
    }
    use_platform = strcmp(argv[1], "native") != 0;
    load_desktop_gl = !strcmp(argv[1], "platform-glx");
    if (load_desktop_gl) {
        /* Controlled loader A/B: gstgl has DT_NEEDED libGL.so.1.
         * Never replace it or inject a substitute on the live system. */
        if (!dlopen("libGL.so.1", RTLD_NOW | RTLD_GLOBAL)) {
            fprintf(stderr, "dlopen libGL.so.1 failed: %s\n", dlerror());
            return 16;
        }
        fprintf(stderr, "DESKTOP_GL_LOADED=1\n");
    }
    wl = wl_display_connect(NULL);
    if (!wl)
        return fail("wl_display_connect", 3);
    if (use_platform) {
        PFNEGLGETPLATFORMDISPLAYEXTPROC get_platform =
            (PFNEGLGETPLATFORMDISPLAYEXTPROC)
            eglGetProcAddress("eglGetPlatformDisplayEXT");
        if (!get_platform)
            return fail("eglGetPlatformDisplayEXT symbol", 4);
        display = get_platform(EGL_PLATFORM_WAYLAND_EXT, wl, NULL);
    } else {
        display = eglGetDisplay((EGLNativeDisplayType)wl);
    }
    if (display == EGL_NO_DISPLAY)
        return fail("eglGetDisplay", 5);
    if (!eglInitialize(display, &major, &minor))
        return fail("eglInitialize", 6);
    fprintf(stderr, "EGL %d.%d mode=%s vendor=%s\n", major, minor,
            argv[1], eglQueryString(display, EGL_VENDOR));
    if (!eglBindAPI(EGL_OPENGL_ES_API))
        return fail("eglBindAPI", 7);
    if (!eglChooseConfig(display, cfg, &config, 1, &count))
        return fail("eglChooseConfig pbuffer GLES2", 8);
    if (count == 1) {
        surface = eglCreatePbufferSurface(display, config, pb);
        if (surface == EGL_NO_SURFACE)
            return fail("eglCreatePbufferSurface", 9);
    } else {
        const char *exts = eglQueryString(display, EGL_EXTENSIONS);
        fprintf(stderr, "NO_PBUFFER_CONFIG=1 EGL_SURFACELESS=%d\n",
                exts && strstr(exts, "EGL_KHR_surfaceless_context") != NULL);
        if (!exts || !strstr(exts, "EGL_KHR_surfaceless_context"))
            return fail("no pbuffer or surfaceless support", 8);
        if (!eglChooseConfig(display, any_gles2, &config, 1, &count) || count != 1)
            return fail("eglChooseConfig any GLES2", 8);
    }
    context = eglCreateContext(display, config, EGL_NO_CONTEXT, ctx);
    if (context == EGL_NO_CONTEXT)
        return fail("eglCreateContext", 10);
    if (!eglMakeCurrent(display, surface, surface, context))
        return fail("eglMakeCurrent", 11);
    const char *vendor = (const char *)glGetString(GL_VENDOR);
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    fprintf(stderr, "GL_VENDOR=%s GL_RENDERER=%s\n",
            vendor ? vendor : "(null)", renderer ? renderer : "(null)");
    if (!vendor || !renderer || !strstr(vendor, "Grate") ||
        !strstr(renderer, "Tegra"))
        return fail("unqualified GPU vendor/renderer", 12);
    /* Offscreen FBO pixel oracle: a successful clear is GPU activity,
     * but proves neither shader conversion nor visible video in Sway. */
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 64, 64, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    glGenFramebuffers(1, &framebuffer);
    glBindFramebuffer(GL_FRAMEBUFFER, framebuffer);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                           GL_TEXTURE_2D, texture, 0);
    GLenum fb_status = glCheckFramebufferStatus(GL_FRAMEBUFFER);
    fprintf(stderr, "GPU_FBO_STATUS=0x%04x\n", (unsigned)fb_status);
    if (fb_status != GL_FRAMEBUFFER_COMPLETE)
        return fail("FBO incomplete", 17);
    glViewport(0, 0, 64, 64);
    glClearColor(1.f, 0.f, 0.f, 1.f);
    glClear(GL_COLOR_BUFFER_BIT);
    if (glGetError() != GL_NO_ERROR)
        return fail("glClear", 13);
    glReadPixels(32, 32, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px);
    if (glGetError() != GL_NO_ERROR)
        return fail("glReadPixels", 14);
    fprintf(stderr, "GPU_FBO_RGBA=%u,%u,%u,%u\n",
            px[0], px[1], px[2], px[3]);
    if (px[0] < 240 || px[1] > 15 || px[2] > 15 || px[3] < 240)
        return fail("pbuffer pixel mismatch", 15);
    glDeleteFramebuffers(1, &framebuffer);
    glDeleteTextures(1, &texture);
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(display, context);
    if (surface != EGL_NO_SURFACE)
        eglDestroySurface(display, surface);
    eglTerminate(display);
    wl_display_disconnect(wl);
    fprintf(stderr, "PASS EGL_GLES2_FBO mode=%s\n", argv[1]);
    return 0;
}
