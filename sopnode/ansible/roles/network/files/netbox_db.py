import argparse
import yaml
from ipaddress import ip_network
import re
import pynetbox

def parseParameters():
  """
  Parse user parameters

  :returns: tuple. (str Netbox server name, port: int Netbox port, str Authentication token to connect to Netbox API)
  """
  parser = argparse.ArgumentParser()
  parser.add_argument('--server', help='Netbox server', required=True)
  parser.add_argument('--port', help='Netbox port', required=True)
  parser.add_argument('--token', help='Netbox authentication token', required=True)
  args = parser.parse_args()

  server = args.server
  port = args.port
  token = args.token

  return server, port, token

def get_netbox_db(netbox):
  """
  Build knowledge base from Netbox inventory

  :arg dict netbox: A dictionnary with Netbox server, port, and access token.
                    Mendatory keys are
                      - `server`: str the server name (e.g., netbox.example.com)
                      - `port`: int (e.g., 80)
                      - `token`: str  (e.g., 123456789abcdef0123)
  :returns: dict.
  """
  # Connect to Netbox
  nb = pynetbox.api('http://{}:{}'.format(netbox['server'], netbox['port']), token=netbox['token'])

  # Get all interfaces
  interfaces = get_interfaces(nb)

  # Link IP addresses to interfaces
  ip_to_interface(nb, interfaces)

  # Link interfaces to devices
  devices = get_devices(nb, interfaces)

  # Determine all the IP prefixes and their IP range
  dhcp_prefixes = build_dhcp_prefixes(nb)

  # Put knowledge together
  db = {
    'prefixes': dhcp_prefixes,
    'devices': { device['name']: device for device in devices.values()}
    }

  return db

def build_dhcp_prefixes(nb):
  """
  List all IP prefixes and their associated IP ranges.

  :arg pynetbox.core.api.Api nb: pynetbox entry point

  :returns: list.
  """
  dhcp_prefixes = []
  for prefix in nb.ipam.prefixes.all():
    prefix_db = {
                'prefix': prefix.prefix,
                'is_pool': prefix.is_pool,
                'ranges': []
              }
    net = ip_network(prefix.prefix)

    # check for IPAM ip ranges covered by the prefix and add them in the ranges
    # associated to the prefix
    for ip_range in nb.ipam.ip_ranges.all():
      start = ip_network(ip_range.start_address, strict=False)
      end =   ip_network(ip_range.end_address, strict=False)

      if start == end == net:
        s = re.sub('\/\d+', '', ip_range.start_address)
        e = re.sub('\/\d+', '', ip_range.end_address)
        prefix_db['ranges'].append({'start_address': s, 'end_address':e})

    dhcp_prefixes.append(prefix_db)

  return dhcp_prefixes

def get_devices(nb, interfaces):
  """
  Get all devices, with their associated network interfaces

  :arg pynetbox.core.api.Api nb: pynetbox entry point
  :arg dict interfaces: interfaces database

  :returns: dict.
  """
  devices = {}

  for interface in nb.dcim.interfaces.all():
    deviceid = interface.device.id
    device = nb.dcim.devices.get(deviceid)
    device_db = devices.setdefault(deviceid, {'id': deviceid, 'name': device.name, 'interfaces': []})
    interface_db = interfaces[interface.id]
    interface_db['device_name'] = interface.device.name

    device_db['interfaces'].append(interface_db)

  return devices

def ip_to_interface(nb, interfaces):
  """
  Associate IP information to network interfaces

  :arg pynetbox.core.api.Api nb: pynetbox entry point
  :arg dict interfaces: interfaces database
  """
  for ip in nb.ipam.ip_addresses.all():
    ifid = ip.assigned_object_id
    if ifid is not None:
      interface = nb.dcim.interfaces.get(ifid)
      iface = interfaces[interface.id]
      iface['ip_addresses'].append(ip.address)

def get_interfaces(nb):
  """
  Get all interfaces from the knowledge base

  :arg pynetbox.core.api.Api nb: pynetbox entry point

  :returns: dict.
  """
  interfaces = {}
  for interface in nb.dcim.interfaces.all():
    mac = interface.mac_address
    interfaces.setdefault(interface.id, {'id': interface.id, 'ifname': interface.name, 'mac': mac.lower() if mac is not None else mac, 'ip_addresses': []})
  
  return interfaces

if __name__ == "__main__":
  server, port, token = parseParameters()

  db = get_netbox_db(netbox = {'server': server, 'port': port, 'token': token})

  # Dump the database in YAML
  print(yaml.dump(db))