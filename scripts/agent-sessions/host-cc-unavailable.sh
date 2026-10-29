#!/bin/sh
printf '%s\n' 'Host C linker unavailable: cc is missing or does not resolve to an executable in the public /usr tool tree. Native R4X build pins are unchanged.' >&2
exit 127
