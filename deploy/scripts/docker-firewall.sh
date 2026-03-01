#!/usr/bin/env bash
# Re-apply DOCKER-USER iptables rules after Docker (re)starts.
# Docker recreates its chains on daemon restart, which may clear
# custom DOCKER-USER rules even if iptables-persistent saved them.
set -euo pipefail

# Detect the default network interface from the routing table.
IFACE=$(ip -o route get 8.8.8.8 | sed -n 's/.*dev \([^ ]*\).*/\1/p')
if [ -z "$IFACE" ]; then
  echo "ERROR: could not detect default network interface"
  exit 1
fi
echo "Detected default interface: $IFACE"

# IPv4: flush and rebuild DOCKER-USER chain
iptables -F DOCKER-USER
iptables -A DOCKER-USER -i "$IFACE" -p tcp --dport 80 -j ACCEPT
iptables -A DOCKER-USER -i "$IFACE" -p tcp --dport 443 -j ACCEPT
iptables -A DOCKER-USER -i "$IFACE" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A DOCKER-USER -i "$IFACE" -j DROP
iptables -A DOCKER-USER -j RETURN

# IPv6: flush and rebuild DOCKER-USER chain
ip6tables -F DOCKER-USER
ip6tables -A DOCKER-USER -i "$IFACE" -p tcp --dport 80 -j ACCEPT
ip6tables -A DOCKER-USER -i "$IFACE" -p tcp --dport 443 -j ACCEPT
ip6tables -A DOCKER-USER -i "$IFACE" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
ip6tables -A DOCKER-USER -i "$IFACE" -j DROP
ip6tables -A DOCKER-USER -j RETURN

echo "DOCKER-USER firewall rules applied on $IFACE"
