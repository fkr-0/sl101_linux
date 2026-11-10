project('nura-browser', 'c',
  version: '0.1.0',
  meson_version: '>=0.63',
  default_options: ['c_std=c11', 'warning_level=3', 'werror=true'])

# Explicit cross-worker source inventory; never glob or silently skip a lane.
# Engine/navigation/control are owned and implemented by workers A/B/C.
browser_sources = files(
  'src/engine/main.c',
  'src/engine/engine.c',
  'src/engine/options.c',
  'src/navigation/navigation.c',
  'src/navigation/state.c',
  'src/navigation/url.c',
  'src/control/control.c',
)

glib = dependency('glib-2.0', version: '>=2.70', required: true)
gio = dependency('gio-2.0', required: true)
gio_unix = dependency('gio-unix-2.0', required: true) # <gio/gunixsocketaddress.h>
gobject = dependency('gobject-2.0', required: true)
webkit = dependency('wpe-webkit-2.0', version: '>=2.54.0', required: true)
platform = dependency('wpe-platform-2.0', required: true)
json_glib = dependency('json-glib-1.0', required: true)

if get_option('armhf_qualification')
  if not meson.is_cross_build()
    error('armhf_qualification requires an actual Meson cross build')
  endif
  if host_machine.cpu_family() != 'arm' or host_machine.system() != 'linux'
    error('ARMHF target must be Linux on ARM, never a native host build')
  endif
  if not meson.get_compiler('c').has_multi_arguments('-march=armv7-a', '-mfpu=vfpv3-d16', '-mfloat-abi=hard')
    error('Cross C compiler does not support required Tegra2 hard-float/VFPv3-D16 flags')
  endif
endif

inc = include_directories('include')
executable('nurabrowser-core', browser_sources,
  include_directories: inc,
  dependencies: [glib, gio, gio_unix, gobject, webkit, platform, json_glib],
  install: true,
  install_dir: get_option('libexecdir') / 'nura-browser')

# The ONLY future public command. No sl101-browse compatibility shim.
install_data('scripts/launch.sh',
  install_dir: get_option('bindir'),
  rename: ',browse',
  install_mode: 'rwxr-xr-x')

py = import('python').find_installation('python3')
test('offline-qualification', py,
  args: ['-m', 'unittest', 'discover', '-s', meson.project_source_root() / 'tests',
         '-p', 'test_*.py', '-v'],
  env: ['NURABROWSER_SOURCE_DIR=' + meson.project_source_root()],
  timeout: 120)

+# These three scripts compile/run only small native GLib test doubles on the
+# build host. They never invoke a cross-built ARM executable or any device.
+shell = find_program('sh')
+test('engine-options-host', shell,
+  args: [meson.project_source_root() / 'src/engine/tests/run-host-smoke.sh'],
+  timeout: 120)
+test('navigation-host', shell,
+  args: [meson.project_source_root() / 'src/navigation/tests/run-host-tests.sh'],
+  timeout: 120)
+test('control-ipc-host', shell,
+  args: [meson.project_source_root() / 'src/control/tests/run-host-tests.sh'],
+  timeout: 120)
