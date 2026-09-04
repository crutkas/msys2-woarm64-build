/* NON-FUNCTIONAL STUB for git-credential-manager.
 * This binary is a toolchain-proof PLACEHOLDER. It manages NO credentials.
 * It exists only so the MinGit packaging tooling has a valid ARM64 PE to list
 * in the git-credential-manager package slot. Any attempt to use it as a real
 * credential helper exits non-zero with a clear message, so it can never
 * silently masquerade as working credential storage.
 */
#include <stdio.h>
int main(int argc, char **argv)
{
    fprintf(stderr,
        "git-credential-manager: NON-FUNCTIONAL STUB (toolchain-proof placeholder).\n"
        "This build manages no credentials. Install a real credential helper.\n");
    (void)argc; (void)argv;
    return 1;
}
