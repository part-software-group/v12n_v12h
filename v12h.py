#!/usr/bin/env python3
import os
import sys
import argparse
import string
import subprocess
import random
#import libvirt

my_name = "[v12h]"
my_version = ""
v12n_home = "/v12n"
show, password_num = False, 12 

parser = argparse.ArgumentParser()
parser.add_argument( "--list", "-l", help="list vms", action="store_true" )
parser.add_argument( "--status", "-s", help="list with status on|off" )
parser.add_argument( "--new-vm", help="create vm" )
parser.add_argument( "--packer-tmpl", help="{buster,stretch}.json" )
parser.add_argument( "--password", help="password" )
parser.add_argument( "--show", help="show password", action="store_true" )
parser.add_argument( "--virsh", "-i", help="virsh of vm" )
parser.add_argument( "--edit", "-e", help="edit vm xml", nargs=2 )
parser.add_argument( "--console", "-n", help="console to vm", nargs=2 )
parser.add_argument( "--start", "-R", help="start vm", nargs=2 )
parser.add_argument( "--stop", "-S", help="stop vm", nargs=2 )
parser.add_argument( "--set-cpu", help="set vm vpu to (if maxcpu)" )
parser.add_argument( "--set-mem", help="set vm memory to (if maxmem)" )
parser.add_argument( "--add-bridge", help="add bridge on, ex: eth0" )
parser.add_argument( "--bridge-if", help="name of the bridge, ex: br0" )
parser.add_argument( "--bridge-ip", help="ip address to set on bridge" )
parser.add_argument( "--bridge-gw", help="gw address to set on bridge" )
parser.add_argument( "--hv-up", help="rise up", action="store_true" )
parser.add_argument( "--packer-git", help="packer git address" )
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
        r = subprocess.call( [ "su", "-", vm, "-c", command ] )
    else:
        print( bcolors.WARNING + my_name,
               "no vm name specified" + bcolors.ENDC )
    print( my_name, command, r )
    if r == 0:
        return( True )
    else:
        return( False )

def show_pass( user, password ):
    "show password or not"
    check_root()
    if show:
        print( bcolors.OKGREEN + my_name,
               "creating user", user, "with password", password +
               bcolors.ENDC )
        create_user( user, password )
    else:
        print( bcolors.OKGREEN + my_name,
               "creating user", user + bcolors.ENDC )
        create_user( user, password )

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
        print( bcolors.OKGREEN + my_name,
               "user", user, "created successfully" + bcolors.ENDC )
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
    subprocess.call( [ "chown", "-R", user + ":" + "kvm", user_home ] )
    print( bcolors.OKGREEN + my_name, "$HOME is " + user_home + bcolors.ENDC )
    if create_vm( user, user_home ):
        print( bcolors.OKGREEN + my_name,
               "vm created successfully" + bcolors.ENDC )
    else:
        print( bcolors.FAIL + my_name,
               "something went wrong. cleaning ..." + bcolors.ENDC )
        subprocess.call( [ "deluser", "--remove-home", user ] )

def create_vm( vm, user_home ):
    "creating vm with the help of packer"
    packer_json = packer_tmpl
    print( bcolors.OKGREEN + my_name,
           "creating vm with user", vm + bcolors.ENDC )
    su_as_vm( vm, "cp -r /v12n/.packer $HOME" )
    if su_as_vm( vm, "cd " + user_home + "/.packer/qemu/debian&&" +
                 "nano " + packer_json + "&&" + "packer build " + packer_json ):
        return( True )
    else:
        return( False )


def password_gen( size ):
    "generating random password"
    return ''.join( random.choice( string.ascii_lowercase + string.digits ) for _ in range( size ) )

def listdir_nohidden():
    "list all in v12n_home but not hidden and lost+found"
    for f in os.listdir( v12n_home ):
        if not f.startswith( '.' ) and not f == "lost+found":
            yield f

def setup_bridge( br_on, br_if, br_ip, br_bg ):
    "setting up bridge interface and qemu related stuff"
    check_root()
    bo = str( br_on )
    bf = str( br_if )
    bi = str( br_ip )
    bg = str( br_bg )
    subprocess.call( [ "mv", "/etc/network/interfaces",
                             "/etc/network/interfaces.old" ] )
    with open( "/etc/network/interfaces", "w+" ) as lo:
        lo.write( "# added by v12h\n"
                  "auto lo\n"
                  "iface lo inet loopback\n"
                  "source-directory /etc/network/interfaces.d\n" )
    with open( "/etc/network/interfaces.d/" + bf, "w+" ) as br:
        br.write( "# added by v12h\n"
                  "auto " + bf + "\n"
                  "iface " + bf + " inet static\n"
                  "  address " + bi + "\n"
                  "  gateway " + bg + "\n"
                  "  bridge_ports " + bo + "\n"
                  "  bridge_stp off\n"
                  "  bridge_fd 0\n" )
    with open( "/etc/qemu/bridge.conf", "w+" ) as bc:
        bc.write( "# added by v12h\n"
                  "allow " + bf + "\n" )
    subprocess.call( [ "ip", "address", "flush", bo, "scope", "global" ] )
    subprocess.call( [ "ifup", bf ] )
    subprocess.call( [ "setcap",
                      "cap_net_admin+ep",
                      "/usr/lib/qemu/qemu-bridge-helper" ] )

def hv_up():
    "setup all needed for a host to be a kvm hv"
    check_root()
    if not os.path.exists( v12n_home ):
        os.makedirs( v12n_home + "/.iso" )
    if not os.path.exists( "/etc/qemu" ):
        os.makedirs( "/etc/qemu" )
        print( bcolors.OKGREEN + my_name, v12n_home,
               "created" + bcolors.ENDC )
    subprocess.call( [ "apt-get", "update" ] )
    subprocess.call( [ "apt-get", "--yes", "--no-install-recommends", "install",
                       "atop", "htop", "git", "screen", "udhcpd", "packer",
                       "parted", "qemu-utils", "qemu-kvm", "libguestfs-tools",
                        "libvirt-clients", "libvirt-daemon-system",
                        "virtinst", "bridge-utils" ] )
    subprocess.call( [ "git", "-C", v12n_home, "clone",
                       "--depth", "1", packer_git, v12n_home + "/.packer" ] )

if args.virsh:
    su_as_vm( args.virsh, "virsh" )
if args.edit:
    su_as_vm( args.edit[ 0 ], "virsh edit " + args.edit[ 1 ] )
if args.console:
    su_as_vm( args.console[ 0 ], "virsh console " + args.console[ 1 ] )
if args.start:
    su_as_vm( args.start[ 0 ], "virsh start " + args.start[ 1 ] )
if args.stop:
    su_as_vm( args.stop[ 0 ], "virsh destroy " + args.stop[ 1 ] )

if args.list and args.status:
    check_root()
    if  args.status == "on":
        state = "state-running"
    elif args.status == "off":
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
    user = args.new_vm
    if args.packer_tmpl:
        packer_tmpl = args.packer_tmpl
    else:
        sys.exit( bcolors.FAIL + my_name +
                " error: packer template name is not specified" + bcolors.ENDC )

    if args.password:
        password = args.password
    else:
        password = password_gen( password_num )
    show_pass( user, password )

if args.add_bridge:
    if args.bridge_if:
        if args.bridge_ip:
            if args.bridge_gw:
                setup_bridge( br_on = args.add_bridge,
                    br_if = args.bridge_if,
                    br_ip = args.bridge_ip,
                    br_bg = args.bridge_gw )

if args.hv_up:
    if args.packer_git:
        packer_git = args.packer_git
    else:
        sys.exit( bcolors.FAIL + my_name +
                  " error: packer git address is not specified" + bcolors.ENDC )
    hv_up()
