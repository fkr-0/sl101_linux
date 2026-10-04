#!/usr/bin/env python3
"""Build a scanout-only BO-flag correction against the exact accepted archive."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess

BASE_SHA = '68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade'
RESOURCE_SHA = 'b5cc9cc61debe2c75a624b6a2f9f2384cac1e244ef6bbe68089d507d7e37a2c8'
ARCHIVE_SHA = '6f09746e9c79e218a6287986a2adcd4c0827f5c74d9859171865d1380b5fe240'


def correct_scanout_flags(source):
    marker = '   if (template->target != PIPE_BUFFER) {'
    if source.count(marker) != 1 or source.count('flags = DRM_TEGRA_GEM_CREATE_BOTTOM_UP;') != 2:
        raise ValueError('unexpected resource allocation source')
    return source.replace(marker, '''   /* Scanout buffers already contain top-down compositor rows.  The legacy
    * BOTTOM_UP GEM flag makes Tegra DRM add REFLECT_Y during atomic scanout.
    * Keep offscreen/render-target conventions unchanged. */
   if (template->bind & PIPE_BIND_SCANOUT)
      flags &= ~DRM_TEGRA_GEM_CREATE_BOTTOM_UP;

''' + marker)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    accepted = repo / 'work/sl101-compositor-semantics-20261003/blend-build'
    driver = repo / 'work/sl101-compositor-semantics-20261003/driver/grate'
    mesa = repo / 'tmp/sl101-nura/gpu-egl-20260930-r2/tex-split-diag/build-pseq-final/mesa-25.0.7'
    build = mesa / 'build'
    sdk = repo / 'tmp/sl101-nura/work/chroot_native'
    sysroot = repo / 'tmp/sl101-nura/work/chroot_buildroot_armv7'
    if (sha(accepted / 'libgallium-25.0.7.so') != BASE_SHA
            or sha(driver / 'grate_resource.c') != RESOURCE_SHA
            or sha(accepted / 'libgrate-blend.a') != ARCHIVE_SHA):
        raise SystemExit('accepted artifact/source provenance mismatch')
    prefix = ['bwrap', '--bind', str(sdk), '/', '--dev-bind', '/dev', '/dev', '--proc', '/proc',
              '--tmpfs', '/home', '--dir', '/home/user', '--dir', '/home/user/code',
              '--bind', '/home/user/code', '/home/user/code', '--bind', str(sysroot), '/mnt/sysroot',
              '--chdir', str(build)]

    def run(argv, label):
        (output / (label + '.argv.json')).write_text(json.dumps(argv, indent=2) + '\n')
        subprocess.run(prefix + argv, check=True, timeout=180)

    commands = subprocess.check_output(['ninja', '-t', 'commands', 'src/gallium/drivers/grate/libgrate.a'], cwd=build, text=True).splitlines()
    original = 'src/gallium/drivers/grate/libgrate.a.p/grate_resource.c.o'
    compile_argv = next(shlex.split(line) for line in commands if f' -o {original} ' in line)
    link_argv = shlex.split(subprocess.check_output(['ninja', '-t', 'commands', 'src/gallium/targets/dri/libgallium-25.0.7.so'], cwd=build, text=True).splitlines()[-1])
    for i, value in enumerate(link_argv):
        link_argv[i] = value.replace('/home/pmos/build/src/mesa-25.0.7/build', str(build)).replace('/home/pmos/build/src/mesa-25.0.7/src', str(mesa / 'src'))
    link_argv = ['-Wl,-rpath,/opt/grate-mesa25/lib' if value.startswith('-Wl,-rpath,') else value for value in link_argv]
    archive_index = link_argv.index('src/gallium/drivers/grate/libgrate.a')
    output_index = link_argv.index('-o') + 1
    link_argv[archive_index] = str(accepted / 'libgrate-blend.a')
    link_argv[output_index] = str(output / 'baseline-control.so')
    run(link_argv, 'baseline-link')
    # Retain the relink control: linker symbol ordering can differ without source changes.
    shutil.copytree(driver, output / 'grate-src')
    source = output / 'grate-src/grate_resource.c'
    source.write_text(correct_scanout_flags(source.read_text()))
    obj = output / 'grate_resource.c.o'
    compile_argv[compile_argv.index('-o') + 1] = str(obj)
    compile_argv[compile_argv.index('-c') + 1] = str(source)
    run(compile_argv, 'resource-compile')
    archive = output / 'libgrate-scanout.a'
    shutil.copyfile(accepted / 'libgrate-blend.a', archive)
    run(['gcc-ar', 'r', str(archive), str(obj)], 'archive-replace')
    run(['gcc-ranlib', str(archive)], 'archive-index')
    link_argv[archive_index] = str(archive)
    library = output / 'libgallium-25.0.7.so'
    link_argv[output_index] = str(library)
    run(link_argv, 'candidate-link')
    manifest = {'baseline_sha256': BASE_SHA, 'baseline_archive_sha256': ARCHIVE_SHA,
                'baseline_relink_sha256': sha(output / 'baseline-control.so'),
                'source_sha256': sha(source), 'resource_object_sha256': sha(obj),
                'libgallium_sha256': sha(library), 'scope': 'clear legacy BOTTOM_UP only for PIPE_BIND_SCANOUT'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest))

if __name__ == '__main__':
    main()
