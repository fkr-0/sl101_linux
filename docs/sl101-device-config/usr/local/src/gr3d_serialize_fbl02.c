/* fbl02 GR3D serialisation prototype: deliberately disabled.
 *
 * DO NOT DEPLOY OR ENABLE. This translation unit exports no ioctl()
 * interposer, so loading it cannot capture unrelated DRM calls.
 *
 * Original prototype assumed DRM ioctl nr 0x48 identified a Tegra GR3D
 * submission, dereferenced user syncpts without validated ABI, and kept a
 * flock on the caller-owned fd. close/dup/fd reuse can drop that flock;
 * submit/wait ordering, wraparound and cross-process lifetime were also
 * unproven. A correct replacement requires explicit device, channel and
 * submission identity, owned open-description lifetime, and proven GPU
 * completion before releasing a lock or freeing in-flight BOs.
 *
 * This fail-inactive sentinel intentionally performs NO serialization and
 * MUST NOT be represented as a graphics safety fix.
 */
#include <errno.h>
int sl101_gr3d_fbl02_disabled(void) { return -ENOTSUP; }
