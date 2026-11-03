/* Read-only ARMHF/glibc Grate EGLDevice + GBM diagnostic.
 *
 * Compile within the Debian ARMHF Mesa build environment:
 *   arm-linux-gnueabihf-gcc -Wall -Wextra -O2 -o /tmp/sl101-egl-device-probe \
 *     scripts/sl101-grate-egl-device-probe.c -lEGL -lgbm -lwayland-client -ldl
 *
 * Run inside the private Debian root with the matched Grate overlay:
 *   LD_LIBRARY_PATH=/opt/grate-glibc/usr/lib/arm-linux-gnueabihf \
 *     /tmp/sl101-egl-device-probe /dev/dri/renderD128
 *   # Run against the same Wayland socket used by Cog:
 *   /tmp/sl101-egl-device-probe --wayland
 *
 * Does not create a window, draw, or swap; EGL/GBM initialization may
 * still issue ordinary driver ioctls. Run only in a permitted session.
 */
#define _GNU_SOURCE
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <gbm.h>
#include <wayland-client.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>

static void
origin(const char *label, void *symbol)
{
   Dl_info info;
   if (symbol && dladdr(symbol, &info) && info.dli_fname)
      fprintf(stderr, "library %s: %s\n", label, info.dli_fname);
   else
      fprintf(stderr, "library %s: unknown\n", label);
}

static int
has_extension(const char *extensions, const char *name)
{
   const size_t length = strlen(name);
   if (!extensions)
      return 0;
   while (*extensions) {
      while (*extensions == ' ')
         extensions++;
      if (strncmp(extensions, name, length) == 0 &&
          (extensions[length] == ' ' || extensions[length] == 0))
         return 1;
      extensions = strchr(extensions, ' ');
      if (!extensions)
         break;
   }
   return 0;
}

static int
fail_egl(const char *stage)
{
   fprintf(stderr, "FAIL %s EGL error=0x%04x\n", stage, eglGetError());
   return 1;
}

int
main(int argc, char **argv)
{
   const char *node = argc > 1 ? argv[1] : "/dev/dri/renderD128";
   PFNEGLGETPLATFORMDISPLAYEXTPROC get_display;
   PFNEGLQUERYDISPLAYATTRIBEXTPROC query_display;
   PFNEGLQUERYDEVICESTRINGEXTPROC query_device;
   struct gbm_device *gbm = NULL;
   struct wl_display *wayland = NULL;
   EGLenum platform;
   void *native_display;
   EGLDisplay display;
   EGLint major, minor;
   EGLAttrib device = 0;
   const char *extensions;
   int fd = -1;
   int result = 1;

   if (strcmp(node, "--wayland") == 0) {
      wayland = wl_display_connect(NULL);
      if (!wayland) {
         fprintf(stderr, "FAIL wl_display_connect (check WAYLAND_DISPLAY/XDG_RUNTIME_DIR)\n");
         return 2;
      }
      platform = EGL_PLATFORM_WAYLAND_EXT;
      native_display = wayland;
   } else {
      fd = open(node, O_RDWR | O_CLOEXEC);
      if (fd < 0) {
         perror(node);
         return 2;
      }
      gbm = gbm_create_device(fd);
      if (!gbm) {
         fprintf(stderr, "FAIL gbm_create_device(%s)\n", node);
         close(fd);
         return 3;
      }
      platform = EGL_PLATFORM_GBM_KHR;
      native_display = gbm;
      fprintf(stderr, "GBM backend: %s\n", gbm_device_get_backend_name(gbm));
   }
   origin("libEGL", (void *)eglGetProcAddress);
   origin("libgbm", (void *)gbm_create_device);

   get_display = (PFNEGLGETPLATFORMDISPLAYEXTPROC)
      eglGetProcAddress("eglGetPlatformDisplayEXT");
   query_display = (PFNEGLQUERYDISPLAYATTRIBEXTPROC)
      eglGetProcAddress("eglQueryDisplayAttribEXT");
   query_device = (PFNEGLQUERYDEVICESTRINGEXTPROC)
      eglGetProcAddress("eglQueryDeviceStringEXT");
   if (!get_display || !query_display || !query_device) {
      fprintf(stderr, "FAIL missing EGL_EXT_platform_base/device_query entrypoints\n");
      goto done;
   }
   origin("eglQueryDisplayAttribEXT", (void *)query_display);

   display = get_display(platform, native_display, NULL);
   if (display == EGL_NO_DISPLAY) {
      result = fail_egl("eglGetPlatformDisplayEXT");
      goto done;
   }
   if (!eglInitialize(display, &major, &minor)) {
      result = fail_egl("eglInitialize");
      goto done;
   }
   fprintf(stderr, "EGL version: %d.%d\n", major, minor);
   extensions = eglQueryString(display, EGL_EXTENSIONS);
   fprintf(stderr, "EGL display extensions: %s\n",
           extensions ? extensions : "(null)");
   if (!query_display(display, EGL_DEVICE_EXT, &device)) {
      result = fail_egl("eglQueryDisplayAttribEXT(EGL_DEVICE_EXT)");
      goto terminate;
   }
   if (!device) {
      fprintf(stderr, "FAIL EGL_DEVICE_EXT returned EGL_NO_DEVICE_EXT\n");
      goto terminate;
   }
   fprintf(stderr, "EGLDevice: %p\n", (void *)(uintptr_t)device);
   extensions = query_device((EGLDeviceEXT)(uintptr_t)device, EGL_EXTENSIONS);
   fprintf(stderr, "EGL device extensions: %s\n",
           extensions ? extensions : "(null)");
   if (!has_extension(extensions, "EGL_EXT_device_drm")) {
      fprintf(stderr, "FAIL device does not advertise EGL_EXT_device_drm\n");
      goto terminate;
   }
   const char *drm_path =
      query_device((EGLDeviceEXT)(uintptr_t)device, EGL_DRM_DEVICE_FILE_EXT);
   fprintf(stderr, "EGL DRM node: %s\n", drm_path ? drm_path : "(null)");
   if (!drm_path) {
      fprintf(stderr, "FAIL device has no DRM path\n");
      goto terminate;
   }
   fprintf(stderr, "PASS EGLDevice query on initialized %s display\n",
           wayland ? "Wayland" : "GBM");
   result = 0;

terminate:
   eglTerminate(display);
done:
   if (gbm)
      gbm_device_destroy(gbm);
   if (wayland)
      wl_display_disconnect(wayland);
   if (fd >= 0)
      close(fd);
   return result;
}
