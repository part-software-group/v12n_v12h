#!/usr/bin/env python3
import os
import argparse
import string
import subprocess
import random
#import libvirt

v12n_home = "/v12n"
show, password_num = False, 12 

parser = argparse.ArgumentParser()
parser.add_argument( "--list", "-l", help="list vms", action="store_true" )
parser.add_argument( "--status", "-s", help="list with status on|off", nargs=1 )
parser.add_argument( "--create-user", "-a", help="create user", nargs=1 )
parser.add_argument( "--create-vm", "-m", help="create vm", nargs=1 )
parser.add_argument( "--password", "-p", help="password", nargs=1 )
parser.add_argument( "--show", "-w", help="show password", action="store_true" )
parser.add_argument( "--console", "-n", help="console to vm" )
parser.add_argument( "--start", "-r", help="start vm" )
parser.add_argument( "--stop", "-D", help="stop vm" )
parser.add_argument( "--add-bridge", "-b",
                     help="adding bridge stuff",
                     action="store_true" )
parser.add_argument( "--bridge-ip", "-I", help="ip address to set on bridge" )
args = parser.parse_args()

def check_root():
    "some functions need root permission"
    if os.geteuid() != 0:
        exit( "error: not root" )

def su_as_vm( vm, command ):
    "su as user that runs vm"
    check_root()
    if vm:
        subprocess.run( [ "su", "-", vm, "-c", command ] )
    else:
        print( "no vm name specified" )

def create_user( user, password ):
    "creating system user under /v12n as $HOME"
    user_home = v12n_home + "/" + user
    subprocess.run( [ "adduser", "--quiet", "--disabled-password",
                      "--gecos", "User", "--ingroup", "kvm",
                      "--home", user_home, "--firstuid", "2001",
                      "--lastuid", "2050", user ] )
    p1 = subprocess.Popen( [ "echo", user + ":" + password ],
                              stdout=subprocess.PIPE )
    p2 = subprocess.Popen( [ "chpasswd" ], stdin=p1.stdout )
    p1.stdout.close()
    output = p2.communicate()[0]
    os.makedirs( user_home + "/.local/share/libvirt" )
    os.chmod( user_home, 0o750 )
    subprocess.run( [ "chown", "-R", user + ":" + "kvm", user_home ] )

def show_pass( user, password ):
    "show password or not"
    check_root()
    if show:
        print( "creating user", user, "with password", password )
        create_user( user, password )
    else:
        print( "creating user", user )
        create_user( user, password )
    return

def create_vm( vm ):
    "creating vm with the help of packer"
    print( "creating vm", vm )
    return

def password_gen( size ):
    "generating random password"
    return ''.join( random.choice( string.ascii_lowercase + string.digits ) for _ in range( size ) )

def listdir_nohidden():
    "list all in v12n_home but not hidden and lost+found"
    for f in os.listdir( v12n_home ):
        if not f.startswith( '.' ) and not f == "lost+found":
            yield f

def setup_bridge( br_ip ):
    "setting up bridge interface and qemu related stuff"
    check_root()
    with open( "/etc/network/inetrfaces.d/br0", "w" ) as br:
        br.write( "auto br0\n"
                  "iface br0 inet static\n"
                  "  address " + br_ip + "\n"
                  "  bridge_ports eth0\n"
                  "  bridge_stp off\n"
                  "  bridge_fd 0\n" )
    with open( "/etc/qemu/bridge.conf", "w" ) as bc:
        bc.write( "allow br0\n" )
    subprocess.run( [ "ip", "address", "flush", "eth0", "scope", "global" ] )
    subprocess.run( [ "ifup", "br0" ] )
    subprocess.run( [ "setcap",
                      "cap_net_admin+ep",
                      "/usr/lib/qemu/qemu-bridge-helper" ] )

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
        print( "user: " + vm )
        i = -5
        while i <= len( vm ):
            print( "-", end="" )
            i += 1
        print()
        su_as_vm( vm, "virsh list --name --" + state )

if args.list and not args.status:
    for vm in listdir_nohidden():
        print( vm )

if args.show:
    show = True

if args.create_user:
    if args.password:
        password = args.password[0]
    else:
        password = password_gen( password_num )
    show_pass( user = args.create_user[0], password = password )

if args.create_vm: 
    create_vm( vm = args.create_vm[0] )

if args.add_bridge:
    if args.bridge_ip:
        setup_bridge( br_ip = args.bridge_ip )
    else:
        exit( "error: no ip address defined" )
