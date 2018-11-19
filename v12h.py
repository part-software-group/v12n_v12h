#!/usr/bin/python3
# https://docs.python.org/3/howto/argparse.html
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
parser.add_argument( "--create-user", "-cu", help="create user", nargs=1 )
parser.add_argument( "--create-vm", "-cv", help="create vm", nargs=1 )
parser.add_argument( "--password", "-p", help="password", nargs=1 )
parser.add_argument( "--show", "-w", help="show password", action="store_true" )
parser.add_argument( "--console", "-c", help="console to vm" )
parser.add_argument( "--start", "-S", help="start vm" )
parser.add_argument( "--stop", "-P", help="stop vm" )
args = parser.parse_args()

def check_root():
    if os.geteuid() != 0:
        exit( "error: not root" )

def su_as_vm( vm, command ):
    check_root()
    if vm:
        subprocess.run( ["su", "-", vm, "-c", command] )
    else:
        print( "no vm name specified" )

def linux_adduser( user, password ):
    user_home = v12n_home + "/" + user
    subprocess.run( ["adduser", "--quiet", "--disabled-password", 
                     "--gecos", "User", "--ingroup", "kvm",
                     "--home", user_home, "--firstuid", "2001", 
                     "--lastuid", "2050", user] )
    p1 = subprocess.Popen( ["echo", user + ":" + password], 
                            stdout=subprocess.PIPE )
    p2 = subprocess.Popen( ["chpasswd"], stdin=p1.stdout )
    p1.stdout.close()
    output = p2.communicate()[0]
    os.makedirs( user_home + "/.local/share/libvirt" )
    os.chmod( user_home, 0o750 )
    subprocess.run( ["chown", "-R", user + ":" + "kvm", user_home] )

def create_user( user, password ):
    "creating system user under /v12n as $HOME"
    check_root()
    if show:
        print( "creating user", user, "with password", password )
        linux_adduser( user, password )
    else:
        print( "creating user", user )
        linux_adduser( user, password )
    return

def create_vm( vm ):
    "creating vm with the help of packer"
    print( "creating vm", vm )
    return

def password_gen( size ):
    return ''.join( random.choice( string.ascii_lowercase + string.digits ) for _ in range( size ) )

def listdir_nohidden():
    for f in os.listdir( v12n_home ):
        if not f.startswith( '.' ):
            yield f

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
    create_user( user = args.create_user[0], 
                 password = password )

if args.create_vm: 
    create_vm( vm = args.create_vm[0] )

