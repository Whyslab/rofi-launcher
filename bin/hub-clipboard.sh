#!/bin/sh
# CTRL+J — тот же хаб, сразу на разделе буфера обмена.
exec "$(dirname "$(readlink -f "$0")")/hub.sh" clip
