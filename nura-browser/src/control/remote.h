/* SPDX-License-Identifier: MIT */
#ifndef NURABROWSER_REMOTE_H
#define NURABROWSER_REMOTE_H

/* Called only for the explicit --remote mode of the existing browser ELF.
 * No WebView is constructed and no second public executable is created. */
int nurabrowser_remote_main(int argc, char **argv);

#endif
