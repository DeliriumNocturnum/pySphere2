# pySphere script used for load balancing memory utilization across hosts in vSphere 5.x
# Written by Jacob Schwartz: jake@schwartzpub.com
# 02/2014

from pysphere import *
import math

# Connect to vCenter Server
s = VIServer()
s.connect("<server>", "<user>", "<pass>")

# Define properties for virtual machines and hosts
vmproperties = s._retrieve_properties_traversal(property_names=["name",
"config.hardware.memoryMB", "runtime.host", "runtime.powerState"], obj_type="VirtualMachine")

hostproperties = s._retrieve_properties_traversal(property_names=["config.host",
"summary.quickStats.overallMemoryUsage", "hardware.memorySize"], obj_type="HostSystem")

clusterproperties = s._retrieve_properties_traversal(property_names=["name", "host"], obj_type="ClusterComputeResource")

vms = []
hosts = []
clusters = []
staging = {}

# Define tolerance in % of memory utilization: the greatest span of utilization that is allowed between any two hosts as an int()
tolerance = float(10)

# Class definitions for hosts and vms
class host(object):
	def __init__(self, mor, memtotal, memuse, mempct):
		self.mor = mor
		self.memtotal = int(memtotal)
		self.memuse = int(memuse)
		self.mempct = float(mempct)

class vm(object):
	def __init__(self, name, mem, host, state):
		self.name = name
		self.memalloc = int(mem)
		self.host = host
		self.state = state
		self.staged = False

class cluster(object):
	def __init__(self, name, hosts):
		self.name = name
		self.hosts = hosts
		
# Create host and vm objects
def getproperties():
	for p in vmproperties:
		for prop in p.PropSet:
			if prop.Name == "name": name = prop.Val
			if prop.Name == "config.hardware.memoryMB": memory = prop.Val
			if prop.Name == "runtime.host": owner = prop.Val
			if prop.Name == "runtime.powerState": power = prop.Val
		if power != "poweredOn": continue
		else: vms.append(vm(name, memory, owner, power))

	for p in hostproperties:
		for prop in p.PropSet:
			if prop.Name == "config.host": hostmor = prop.Val
			if prop.Name == "summary.quickStats.overallMemoryUsage": memuse = float(prop.Val)
			if prop.Name == "hardware.memorySize": memutil = float((prop.Val / 1024) / 1024)
		percent = "%.2f" % (100 * (memuse / memutil)) 
		hosts.append(host(hostmor, memutil, memuse, percent))

	for p in clusterproperties:
		for prop in p.PropSet:
			if prop.Name == "name": name = prop.Val
			if prop.Name == "host": chosts = prop.Val.ManagedObjectReference
		clusters.append(cluster(name, chosts))

# Determine where to move virtual machines to balance cluster
def balance(vms, hosts, tolerance):
	for x in hosts:
		for y in hosts:
			for hostlist in (c.hosts for c in clusters):
				hl = hostlist
			if x.mor == y.mor or not all(h in hl for h in [str(x.mor), str(y.mor)]): pass
			elif (x.mempct - y.mempct) > tolerance:
				for vm in vms:
					if vm.memalloc < (x.memuse - y.memuse) and vm.host == x.mor:
						print "Staging ", vm.name, " to migrate to ", y.mor, "..."
						staging[vm.name] = y.mor
						vm.staged = True
						vm.host = y.mor
						x.memuse -= vm.memalloc
						y.memuse += vm.memalloc	
	if any(vm.staged for vm in vms):
		migrate()
		balance(vms, hosts, tolerance)
	else: print "Nothing to migrate..."

# Wash lists for host and vm and cluster objects, repopulate
def updatevalues():
	del vms[:]
	del hosts[:]
	del clusters[:]
	getproperties()
	return

# Migrate vms
def migrate():
	for vmstage in staging.keys():
		vmuse = s.get_vm_by_name(vmstage)
		vmuse.migrate(host=staging[vmstage])
		if any(vm.name == vmstage for vm in vms): vm.staged = False
	updatevalues()
	return

# Run balance
getproperties()
balance(vms, hosts, tolerance)

# Disconnect from vCenter Server
s.disconnect()
