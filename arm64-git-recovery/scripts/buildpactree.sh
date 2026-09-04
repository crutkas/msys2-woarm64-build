#!/bin/bash
cd /tmp/pacman-contrib || exit 1
cat > /tmp/pt_config.h <<'EOF'
#define PACKAGE_VERSION "1.10.6"
#define PACKAGE "pacman-contrib"
#define _GNU_SOURCE 1
EOF
gcc -include /tmp/pt_config.h -o /tmp/pactree src/pactree.c -I. -lalpm 2>&1 | head -25
if [ -f /tmp/pactree ]; then echo "PACTREE BUILT"; /tmp/pactree 2>&1 | head -3; fi
