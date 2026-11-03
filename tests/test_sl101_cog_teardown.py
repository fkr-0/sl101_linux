"""Host-only candidate tests: compiled model != Cog-linked regression."""
import pathlib, subprocess, tempfile, unittest, shutil
ROOT = pathlib.Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/cog-0.18.5/teardown/cog-0.18.5-release-lifetime.patch"
SRC = ROOT / "work/scanout-followups-20261103/cog-teardown/cog-src"
COMMIT = "5d7c720e4f16360a0412a949a1a3f4209e81b9ec"
FILES = ["platform/drm/cog-drm-modeset-renderer.c", "platform/drm/cog-drm-renderer.h", "platform/drm/cog-platform-drm.c"]
C = r"""
#include <assert.h>
#include <stdio.h>
typedef struct {int token,pending,events,alive,stopped,released,destroyed,reenter;} State;
void release(State *s) { if(!s->token)return; s->token=0; ++s->released;
  if(s->reenter){s->reenter=0;release(s);} }
void stop(State *s) {if(s->stopped)return; s->stopped=1; s->events=0;
  s->pending=0;release(s);if(s->alive){s->alive=0;++s->destroyed;}}
void reject(State *s){assert(s->pending);--s->pending;release(s);}
int main(void) {
  State term={.token=1,.pending=1,.events=1,.alive=1};
  stop(&term);stop(&term);
  assert(term.released==1 && term.destroyed==1 && !term.pending && !term.events);
  State fail={.token=1,.pending=1,.alive=1};reject(&fail);stop(&fail);
  assert(fail.released==1 && fail.destroyed==1);
  State reentrant={.token=1,.alive=1,.reenter=1};
  release(&reentrant);release(&reentrant);stop(&reentrant);
  assert(reentrant.released==1 && reentrant.destroyed==1);
  State empty={.alive=1};stop(&empty);stop(&empty);
  assert(empty.destroyed==1 && empty.released==0);
  puts("compiled lifecycle model: PASS");return 0;
}
"""
class TestCogTeardown(unittest.TestCase):
    def test_compiled_model(self):
        cc=shutil.which("cc")
        if not cc: self.skipTest("cc unavailable")
        with tempfile.TemporaryDirectory(prefix="sl101-cog-test-") as t:
            p=pathlib.Path(t); (p/"test.c").write_text(C)
            subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",str(p/"test.c"),"-o",str(p/"test")],check=True,capture_output=True)
            r=subprocess.run([str(p/"test")],check=True,capture_output=True,text=True)
            self.assertIn("PASS",r.stdout)
    def test_patch_scope(self):
        content=PATCH.read_text()
        self.assertEqual(content.count("diff --git "),3)
        self.assertNotIn("sl101-cog-wpe-enter-kms",content)
        for token in ["g_source_destroy(self->drm_source)", "free_flip_data(data)", "cog_drm_exportable_owner_destroy", "g_steal_pointer(&buffer->export.resource)"]:
            self.assertIn(token,content)
    def test_strict_apply_and_reverse(self):
        if not (SRC/".git").exists(): self.skipTest("isolated pinned source unavailable")
        head=subprocess.run(["git","-C",str(SRC),"rev-parse","HEAD"],check=True,capture_output=True,text=True).stdout.strip()
        self.assertEqual(head,COMMIT)
        with tempfile.TemporaryDirectory(prefix="sl101-cog-apply-") as t:
            dest=pathlib.Path(t);subprocess.run(["git","init","-q",str(dest)],check=True)
            originals={}
            for name in FILES:
                original=subprocess.run(["git","-C",str(SRC),"show",COMMIT+":"+name],check=True,capture_output=True).stdout
                originals[name]=original;p=dest/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(original)
            for flags in [["--check"],[],["--reverse","--check"],["--reverse"]]:
                subprocess.run(["git","-C",str(dest),"apply",*flags,str(PATCH)],check=True,capture_output=True)
            for name in FILES:self.assertEqual((dest/name).read_bytes(),originals[name])
if __name__=="__main__":unittest.main()
