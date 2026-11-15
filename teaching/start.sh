#!/bin/bash
# Arranca DNS+DHCP (dnsmasq) y el servidor web. Si uno cae, el contenedor
# sale y Docker lo reinicia (restart: always).
mkdir -p /var/lib/misc
/portal/hostlib/dnsmasq -k --conf-file=/portal/dnsmasq.conf &
python3 -u /portal/server.py &
wait -n
echo "Un proceso del portal ha terminado; reiniciando contenedor" >&2
exit 1
