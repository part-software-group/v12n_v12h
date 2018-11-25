#!/usr/bin/env python3
import os
import sys
import argparse
import string
import subprocess
import random
#import libvirt

my_name = "v12h"
my_version = ""
v12n_home = "/v12n"
show, password_num = False, 12 

parser = argparse.ArgumentParser()
parser.add_argument( "--test", "-t", help="testing purpose" )
parser.add_argument( "--list", "-l", help="list vms", action="store_true" )
parser.add_argument( "--status", "-s", help="list with status on|off", nargs=1 )
parser.add_argument( "--new-vm", help="create vm", nargs=1 )
parser.add_argument( "--password", help="password", nargs=1 )
parser.add_argument( "--show", help="show password", action="store_true" )
parser.add_argument( "--packer-git", help="packer git address" )
parser.add_argument( "--virsh", "-i", help="virsh of vm" )
parser.add_argument( "--edit", "-e", help="edit vm xml" )
parser.add_argument( "--console", "-n", help="console to vm" )
parser.add_argument( "--start", "-R", help="start vm" )
parser.add_argument( "--stop", "-S", help="stop vm" )
parser.add_argument( "--set-cpu", help="set vm vpu to (if maxcpu)" )
parser.add_argument( "--set-mem", help="set vm memory to (if maxmem)" )
parser.add_argument( "--add-bridge", help="add bridge on, ex: eth0" )
parser.add_argument( "--bridge-if", help="name of the bridge, ex: br0" )
parser.add_argument( "--bridge-ip", help="ip address to set on bridge" )
args = parser.parse_args()

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def check_root():
    "some functions need root permission"
    if os.geteuid() != 0:
        sys.exit( bcolors.FAIL + my_name +
                  " error: must be root" + bcolors.ENDC )

def su_as_vm( vm, command ):
    "su as user that runs vm"
    check_root()
    if vm:
        subprocess.run( [ "su", "-", vm, "-c", command ] )
    else:
        print( bcolors.WARNING + my_name +
               " no vm name specified" + bcolors.ENDC )

def show_pass( user, password ):
    "show password or not"
    check_root()
    if show:
        print( bcolors.OKGREEN + my_name +
               " creating user", user, "with password", password +
               bcolors.ENDC )
        create_user( user, password )
    else:
        print( bcolors.OKGREEN + my_name +
               " creating user", user + bcolors.ENDC )
        create_user( user, password )
    return

def linux_adduser( user, user_home ):
    r = subprocess.call( [ "useradd", "--comment", "added_by_v12h",
                                     "--create-home", "--home-dir", user_home,
                                     "--no-user-group", "--group", "kvm",
                                     "--key", "UID_MIN=2001",
                                     "--key", "UID_MAX=2050",
                                     user ] )
    if r == 0:
        return( True )
    else:
        return( False )

def create_user( user, password ):
    "creating system user under /v12n as $HOME"
    user_home = v12n_home + "/" + user

    if linux_adduser( user, user_home ):
        print( bcolors.OKGREEN + my_name +
               " user " + user + " created successfuly" + bcolors.ENDC )
    else:
        sys.exit( bcolors.FAIL + my_name +
                  " error: adduser failed" + bcolors.ENDC )

    p1 = subprocess.Popen( [ "echo", user + ":" + password ],
                              stdout=subprocess.PIPE )
    p2 = subprocess.Popen( [ "chpasswd" ], stdin=p1.stdout )
    p1.stdout.close()
    output = p2.communicate()[0]
    os.makedirs( user_home + "/.local/share/libvirt" )
    os.chmod( user_home, 0o750 )
    subprocess.run( [ "chown", "-R", user + ":" + "kvm", user_home ] )
    print( bcolors.OKGREEN + my_name + " $HOME is " + user_home + bcolors.ENDC )
    create_vm( user )

def create_vm( vm ):
    "creating vm with the help of packer"

    print( bcolors.OKGREEN + my_name +
           " creating vm with user " + vm + bcolors.ENDC )
    su_as_vm( vm, "git clone --depth=1 " + packer_git + " packer" )
    su_as_vm( vm, "nano $HOME/packer/qemu/debian/stretch.json" )

def password_gen( size ):
    "generating random password"
    return ''.join( random.choice( string.ascii_lowercase + string.digits ) for _ in range( size ) )

def listdir_nohidden():
    "list all in v12n_home but not hidden and lost+found"
    for f in os.listdir( v12n_home ):
        if not f.startswith( '.' ) and not f == "lost+found":
            yield f

def setup_bridge( br_on, br_if, br_ip ):
    "setting up bridge interface and qemu related stuff"
    check_root()
    bo = str( br_on )
    bf = str( br_if )
    bi = str( br_ip )
    with open( "/etc/network/interfaces.d/" + bf, "w+" ) as br:
        br.write( "auto " + bf + "\n"
                  "iface " + bf + " inet static\n"
                  "  address " + bi + "\n"
                  "  bridge_ports " + bo + "\n"
                  "  bridge_stp off\n"
                  "  bridge_fd 0\n" )
    with open( "/etc/qemu/bridge.conf", "w+" ) as bc:
        bc.write( "allow " + bf + "\n" )
    subprocess.run( [ "ip", "address", "flush", bo, "scope", "global" ] )
    subprocess.run( [ "ifup", bf ] )
    subprocess.run( [ "setcap",
                      "cap_net_admin+ep",
                      "/usr/lib/qemu/qemu-bridge-helper" ] )

if args.virsh:
    su_as_vm( args.virsh, "virsh" )
if args.edit:
    su_as_vm( args.edit, "virsh edit " + args.edit )
if args.console:
    su_as_vm( args.console, "virsh console " + args.console ) 
if args.start:
    su_as_vm( args.start, "virsh start " + args.start ) 
if args.stop:
    su_as_vm( args.stop, "virsh destroy " + args.stop ) 

if args.list and args.status:
    check_root()
    if ( args.status[0] == "on" ):
        state = "state-running"
    elif ( args.status[0] == 'off' ):
        state = "state-shutoff"
    for vm in listdir_nohidden():
        print( bcolors.OKBLUE + "user: " + vm + bcolors.ENDC )
        i = -5
        while i <= len( vm ):
            print( bcolors.OKBLUE + "-", end="" + bcolors.ENDC )
            i += 1
        print()
        su_as_vm( vm, "virsh list --name --" + state )

if args.list and not args.status:
    for vm in listdir_nohidden():
        print( bcolors.OKBLUE + vm + bcolors.ENDC )

if args.show:
    show = True

if args.new_vm:
    if args.password:
        password = args.password[ 0 ]
    else:
        password = password_gen( password_num )

    if args.packer_git:
        packer_git = args.packer_git
    else:
        sys.exit( bcolors.FAIL + my_name +
           " error: packer git address is not specified" + bcolors.ENDC )
    show_pass( user = args.new_vm[ 0 ], password = password )

if args.add_bridge:
    if args.bridge_if:
        if args.bridge_ip:
            setup_bridge( br_on = args.add_bridge,
                          br_if = args.bridge_if,
                          br_ip = args.bridge_ip )
