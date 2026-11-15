#!/bin/sh
# Instala el portal en el UNO Q. Ejecutar dentro de la placa:
#   sh /home/arduino/edu-portal/install.sh
set -e
cd /home/arduino/edu-portal

# 1. Copiar dnsmasq y las librerias que no trae la imagen Python
mkdir -p hostlib
cp /usr/sbin/dnsmasq hostlib/
for l in libnetfilter_conntrack.so.3 libnftables.so.1 libnfnetlink.so.0 \
         libmnl.so.0 libnftnl.so.11 libxtables.so.12 libjansson.so.4; do
  cp -L /lib/aarch64-linux-gnu/$l hostlib/
done

# 2. Wi-Fi: IP fija 192.168.4.1 sin el DHCP de NetworkManager (lo hace el
#    contenedor) y reintentos infinitos al arrancar
nmcli connection modify Edu-Wifi \
  ipv4.method manual ipv4.addresses 192.168.4.1/24 \
  connection.autoconnect yes connection.autoconnect-priority 100 \
  connection.autoconnect-retries 0
nmcli radio wifi on
nmcli connection up Edu-Wifi

# 3. Lanzar el portal
docker compose up -d
sleep 3
docker ps --filter name=edu-portal --format '{{.Names}}: {{.Status}}'
