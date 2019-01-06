#!/usr/bin/env python3
import os
import sys
import argparse
import string
import shutil
import random
import socket
import libvirt
import subprocess
import hashlib
import json


my_name = '[v12h]'
my_version = '2'
v12n_home = '/v12n/'
local_libvirt = '/.local/share/libvirt/'
password_size = 12
packer_default = 'debian.json'
dformat = 'qcow2'


class Color:
    OKGREEN = '\033[92m' + my_name
    WARNING = '\033[93m' + my_name
    FAIL = '\033[91m' + my_name
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def check_root_permission():
    """some functions need root permission"""
    if os.geteuid() != 0:
        print(
            Color.FAIL, 'must be root', Color.ENDC
        )
        sys.exit()


def su_as_user(user, command):
    """su as user that runs domain"""
    check_root_permission()
    if user:
        r = subprocess.call([
            'su', '-', user, '-c', command
            ]
        )
        if args.verbose:
            print(
                Color.OKGREEN, command, r, Color.ENDC
            )
    else:
        print(
            Color.WARNING, 'no domain name specified', Color.ENDC
        )
    if r == 0:
        return(True)
    else:
        return(False)


def generate_password(size):
    """generating random password. copied form stack"""
    return ''.join(
        random.choice(
            string.ascii_lowercase + string.digits
        ) for _ in range(size)
    )


def calculate_md5(fname):
    """md5 of the iso. copied form stack"""
    hash_md5 = hashlib.md5()
    with open(fname, 'rb') as f:
        for chunk in iter(
            lambda: f.read(4096), b''
        ):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def choose_vnc_port():
    """
    return available vnc port between 5900 to 5999.
    some copied from stack
    """
    random_port = random.randint(5900, 5999)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('localhost', random_port)) != 0:
            return(random_port)


def new_user(user, user_home):
    """adding linux user"""
    check_root_permission()
    password = generate_password(password_size)
    if args.show:
        print(
            Color.OKGREEN, 'creating user', user,
            'with password', password,  Color.ENDC
        )
    else:
        print(
            Color.OKGREEN, 'creating user', user, Color.ENDC
        )

    r = subprocess.call([
        'useradd', '--comment', 'added_by_v12h', '--create-home',
        '--home-dir', user_home, '--no-user-group', '--group', 'kvm',
        '--key', 'UID_MIN=2001', '--key', 'UID_MAX=2050', user
        ]
    )
    if r == 0:
        print(
            Color.OKGREEN, 'user', user, 'created successfully', Color.ENDC
        )
    else:
        print(
            Color.FAIL, 'adduser failed', Color.ENDC
        )
        sys.exit()
    p1 = subprocess.Popen(
        ['echo', user + ':' + password],
        stdout=subprocess.PIPE
    )
    p2 = subprocess.Popen(
        ['chpasswd'],
        stdin=p1.stdout
    )
    p1.stdout.close()
    output = p2.communicate()[0]
    os.makedirs(
        user_home + local_libvirt
    )
    os.chmod(
        user_home, 0o750
    )
    subprocess.call([
        'chown', '-R', user + ':' + 'kvm', user_home
        ]
    )
    print(
        Color.OKGREEN, '$HOME is', user_home, Color.ENDC
        )


def remove_user(user):
    """removes everything"""
    if not args.yes:
        prompt = input(
            Color.FAIL
            + ' removing user "' + user + '"? (Y or whatever) '
            + Color.ENDC
        )
        if prompt != 'Y':
            sys.exit()
    check_root_permission()
    print(
        Color.FAIL, 'removing user', user, Color.ENDC
    )
    subprocess.call([
        'pkill', '-u', user
        ]
    )
    subprocess.call([
        'deluser', '--remove-home', user
        ]
    )
    print(
        Color.FAIL, 'removing', user, 'home', Color.ENDC
    )
    try:
        shutil.rmtree(v12n_home + user)
    except FileNotFoundError as e:
        print(
            Color.WARNING, v12n_home + user,
            'is already removed. nevermind ...', Color.ENDC
        )


def packer_up(user, user_home, dicted):
    """add or edit the json file to user for packer build"""
    packer = dicted['packer']
    shutil.copytree(
        v12n_home + '/.packer/qemu',
        user_home + '/.packer/qemu'
    )
    jtmplfile = user_home + '/.packer/qemu/debian/' + packer
    try:
        with open(jtmplfile, 'r') as json_file:
            json_data = json.load(json_file)
            for key in dicted:
                try:
                    val = dicted[key]
                except KeyError as e:
                    print(
                        Color.FAIL, e, Color.ENDC
                    )
                    remove_user(domain)
                json_data['variables'][key] = val
                if args.verbose:
                    print(
                        Color.OKGREEN, key, 'set to', val, Color.ENDC
                    )
    except FileNotFoundError as e:
        print(
            Color.FAIL, e
        )
        remove_user(user)

    with open(jtmplfile, 'w') as json_file:
        json_file.write(json.dumps(json_data, indent=2))
    print(
        Color.OKGREEN, 'building packer image', Color.ENDC
    )
    if su_as_user(
        user, 'cd ' + user_home + '/.packer/qemu/debian&&'
        + 'packer build ' + packer
    ):
        print(
            Color.OKGREEN, 'image created successfully', Color.ENDC
        )
    else:
        print(
            Color.FAIL, 'problem in build', 'cleaning ...', Color.ENDC
        )
        remove_user(user)


def virt_install(mode, user, dicted):
    """domain installation"""
    domain = user
    disk_opts = 'format=' + dformat + ',bus=virtio,cache=none,io=native,'
    try:
        cpu = dicted['cpu'] + ',maxvcpus=' + dicted['xcpu']
        memory = dicted['memory'] + ',maxmemory=' + dicted['xmemory']
        vnc = 'vnc,port=' + dicted['vnc']
        net = 'bridge=' + dicted['br'] + ',model=virtio'
    except KeyError as e:
        print(
            Color.FAIL, e, Color.ENDC
        )
        remove_user(user)
    default_opts = [
        'virt-install', '--connect', 'qemu:///session', '--noautoconsole',
        '--virt-type', 'kvm', '--cpu', 'host', '--boot', 'hd',
        '--name', domain, '--vcpus', cpu, '--memory', memory, '--network', net,
        '--graphics', vnc, ''
    ]
    cmd_default = ' '.join(default_opts)

    if mode == 'image':
        image_opts = [
            '--disk ',
            disk_opts,
            'path='
        ]
        image_args = [
            '$HOME',
            local_libvirt,
            '/images/',
            dicted['hostname'],
            '.',
            dformat
        ]
        cmd_image = ''.join(image_opts)
        image = ''.join(image_args)
        virt_install_image = cmd_default + cmd_image + image
        print(
            Color.OKGREEN, 'installing image using virt-install', Color.ENDC
        )
        if su_as_user(user, virt_install_image):
            print(
                Color.OKGREEN, "vnc port:", dicted['vnc'], Color.ENDC
            )
            return True
        else:
            return False

    if mode == 'iso':
        poolb = 'pool=default,' + disk_opts + 'size='
        try:
            iso_opts = [
                '--cdrom', dicted['iso'], '--disk', poolb + dicted['size']
            ]
        except KeyError as e:
            print(
                Color.FAIL, 'key', e, 'not found', Color.ENDC
            )
            remove_user(user)
        cmd_iso = ' '.join(iso_opts)
        virt_install_iso = cmd_default + cmd_iso
        if su_as_user(domain, virt_install_iso):
            print(
                Color.OKGREEN, "vnc port:", dicted['vnc'], Color.ENDC
            )
            return True
        else:
            return False


def to_dict(the_list):
    """convert list to dict"""
    the_dict = {}
    first = the_list.split(',')
    i = 0
    while i < len(first):
        try:
            sec = first[i].split('=')
            key = sec[0]
            val = sec[1]
            the_dict[key] = val
            i += 1
        except IndexError:
            print(
                Color.FAIL, 'syntax error', 'use key=value,key=value format',
                Color.ENDC
            )
            sys.exit()
    return(the_dict)


def check_keys(dicted, which):
    """check dict for the must keys"""
    dom_key_necss = [
        'name',
        'iso'
    ]
    set_key_necss = [
        'cpu',
        'memory',
        'size',
    ]
    bridge_key_necss = [
        'if',
        'br',
        'ip',
        'bg'
    ]
    which_dict = {
        '--new-domain': dom_key_necss,
        '--set': set_key_necss,
        '--add-bridge': bridge_key_necss
    }
    keys = which_dict[which]
    for key in keys:
        if key not in dicted:
            print(
                Color.FAIL, Color.BOLD + which, str(keys), Color.ENDC
            )
            print(
                Color.FAIL, 'you forgot', Color.BOLD, key, Color.ENDC
            )
            sys.exit()
    return(True)


def fix_dict(dicted, domain):
    """auto add some needed keys"""
    key_defaults = {}
    try:
        key_defaults = {
            'format': dformat,
            'packer': '',
            'username': domain,
            'password': domain,
            'xcpu': dicted['cpu'],
            'xmemory': dicted['memory'],
            'vnc': str(choose_vnc_port()),
            'hostname': domain,
            'domain': socket.getfqdn(),
            'md5': calculate_md5(dicted['iso']),
            'apt_proxy': 'debian.asis.io',
            'br': 'br0'
        }
    except KeyError:
        pass
    for keyd in key_defaults:
        try:
            dicted[keyd]
        except KeyError:
            dicted.update({
                keyd: key_defaults[keyd]
                }
            )
    if dicted['packer']:
        dicted.update({
            'packer': packer_default,
            'size': str(int(dicted['size'])*1024)
            }
        )
    return(dicted)


def get_libvirt_conn(domain):
    """connection to libvirt session"""
    try:
        conn = libvirt.open(
            'qemu+unix:///session?socket=' + v12n_home + domain
            + '/.cache/libvirt/libvirt-sock'
        )
    except libvirt.libvirtError as e:
        print(
            Color.FAIL, 'could not connect', Color.ENDC
        )
        sys.exit()
    if conn is None:
        print(
            Color.FAIL,
            'failed to open connection to qemu:///session',
            Color.ENDC
        )
        sys.exit()
    else:
        return(conn)


def domain_vol_info(domain):
    """domain volume info"""
    MBFACTOR = float(1 << 30)
    conn = get_libvirt_conn(domain)
    dom = conn.lookupByName(domain)
    pool = conn.storagePoolLookupByName('images')
    vol = pool.storageVolLookupByName(pool.listVolumes()[0])
    vformat = subprocess.getoutput(
        'qemu-img info -U ' + vol.path()
    )
    vol = {
        'path': vol.path(),
        'format': vformat.split()[4],
        'size': str(round(vol.info()[1]/MBFACTOR)),
        'df': str(round(float(vol.info()[2]) / float(vol.info()[1])*100)) + '%'
    }
    return(vol)


def domain_info(conn, domain, info):
    """domain info"""
    MBFACTOR = float(1 << 10)
    dom = conn.lookupByName(domain)
    dom_status = {
        libvirt.VIR_DOMAIN_RUNNING: 'active',
        libvirt.VIR_DOMAIN_SHUTDOWN: 'shutdown',
        libvirt.VIR_DOMAIN_SHUTOFF: 'destroyed'
    }
    try:
        xcpu = dom.maxVcpus()
    except libvirt.libvirtError:
        xcpu = 'DOMAIN MUST BE ACTIVE'
    vol = domain_vol_info(domain)
    infos = {
        'name': dom.name(),
        'status': dom_status[dom.state()[0]],
        'uuid': dom.UUIDString(),
        'autostart': dom.autostart(),
        'cpu': dom.info()[3],
        'xcpu': xcpu,
        'memory': dom.info()[2]/MBFACTOR,
        'xmemory': dom.info()[1]/MBFACTOR,
        'format': vol['format'],
        'size': vol['size'],
        'df': vol['df'],
        'path': vol['path']
    }
    if info != 'infos':
        try:
            infos = {info: infos[info]}
        except KeyError:
            print(
                Color.FAIL, 'invalid key', info, Color.ENDC
            )
    for info in infos:
        if not args.short:
            print(
                Color.OKGREEN, info + ':', end=' '
            )
        print(
            infos[info], Color.ENDC
        )
    conn.close()


def domain_action(conn, domain, act, n):
    """do some stuff on domain"""
    dom = conn.lookupByName(domain)
    acts = {
        'start': 'dom.create()',
        'stop': 'dom.destroy()',
        'autostart': 'dom.setAutostart(',
        'cpu': 'dom.setVcpus(',
        'memory': 'dom.setMemory('
    }
    try:
        if args.verbose:
            print(act)
        if n == 0:
            exec(acts[act])
        else:
            exec(acts[act] + n + ')')
        print(
            Color.OKGREEN, dom.name(), act, 'set successfull', Color.ENDC
        )
    except libvirt.libvirtError as e:
        pass
    conn.close()


def domain_vol_resize(domain, size, root):
    """domain volume resize"""
    size = size + 'g'
    vol = domain_vol_info(domain)
    volold = vol['path']
    volnew = volold + '.new'
    volformat = vol['format']
    volroot = root
    cmd_create_disk = [
        'truncate -s ', 'qemu-img create -f qcow2 -o preallocation=metadata '
    ]
    if volformat == 'raw':
        cmd_create_disk = cmd_create_disk[0] + size + ' ' + volnew
    elif volformat == 'qcow2':
        cmd_create_disk = cmd_create_disk[1] + volnew + ' ' + size

    subprocess.getoutput(cmd_create_disk)
    r = subprocess.call([
        'virt-resize', '--expand', volroot, volold, volnew
        ]
    )
    if r == 0:
        print(
            Color.OKGREEN, 'successfully resized in:', volnew, Color.ENDC
        )
    else:
        print(
            Color.FAIL, 'error in resize', Color.ENDC
        )


def hv_up(packer_git):
    """setup all needed for a host to be a kvm hv"""
    check_root_permission()
    if not os.path.exists(v12n_home):
        os.makedirs(v12n_home + '/.iso')
    if not os.path.exists('/etc/qemu'):
        os.makedirs('/etc/qemu')
        print(
            Color.OKGREEN, v12n_home, 'created' + Color.ENDC
        )

    subprocess.call(['apt-get', 'update'])
    subprocess.call([
        'apt-get', '--yes', '--no-install-recommends', 'install',
        'atop', 'htop', 'git', 'screen', 'udhcpd', 'packer', 'parted',
        'qemu-utils', 'qemu-kvm', 'libguestfs-tools', 'libvirt-clients',
        'libvirt-daemon-system', 'virtinst', 'bridge-utils'
        ]
    )
    subprocess.call([
        'git', '-C', v12n_home, 'clone', '--depth', '1', packer_git, v12n_home
        + '.packer'
        ]
    )


def setup_bridge(brigdict):
    """setting up bridge interface and qemu related stuff"""
    check_root_permission()
    bo = brigdict['if']
    bf = brigdict['br']
    bi = brigdict['ip']
    bg = brigdict['bg']
    subprocess.call(
        ['mv', '/etc/network/interfaces', '/etc/network/interfaces.old']
    )
    with open('/etc/network/interfaces', 'w+') as lo:
        lo.write(
            '# added by v12h\n'
            'auto lo\n'
            'iface lo inet loopback\n'
            'source-directory /etc/network/interfaces.d\n'
        )
    with open('/etc/network/interfaces.d/' + bf, 'w+') as br:
        br.write(
            '# added by v12h\n'
            'auto ' + bf + '\n'
            'iface ' + bf + ' inet static\n'
            '  address ' + bi + '\n'
            '  gateway ' + bg + '\n'
            '  bridge_ports ' + bo + '\n'
            '  bridge_stp off\n'
            '  bridge_fd 0\n'
        )

    with open('/etc/qemu/bridge.conf', 'w+') as bc:
        bc.write(
            '# added by v12h\n'
            'allow ' + bf + '\n'
        )
    subprocess.call([
        'ip', 'address', 'flush', bo, 'scope', 'global'
        ]
    )
    subprocess.call([
        'ifup', bf
        ]
    )
    subprocess.call([
        'setcap', 'cap_net_admin+ep', '/usr/lib/qemu/qemu-bridge-helper'
        ]
    )


def main():
    user = os.environ.get('USER')
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--new-domain',
        '-n',
        help='add new domain'
    )
    parser.add_argument(
        '--set',
        '-s',
        nargs='?',
        const=user,
        help='set domain attributes'
    )
    parser.add_argument(
        '--show',
        action='store_true',
        help='show password'
    )
    parser.add_argument(
        '--start',
        '-r',
        nargs='?',
        const=user,
        help='start domain'
    )
    parser.add_argument(
        '--stop',
        '-d',
        nargs='?',
        const=user,
        help='stop domain'
    )
    parser.add_argument(
        '--info',
        '-i',
        nargs='?',
        const='infos',
        help='domain info'
    )
    parser.add_argument(
        '--short',
        action='store_true',
        help='short info'
    )
    parser.add_argument(
        '--add-bridge',
        help='if=?,br=?,ip=?,bg=?'
    )
    parser.add_argument(
        '--hv-up',
        action='store_true',
        help='rise up'
    )
    parser.add_argument(
        '--packer-git',
        help='packer git address'
    )
    parser.add_argument(
        '--new-user',
        help='add new user'
    )
    parser.add_argument(
        '--remove-user',
        help='remove everthing'
    )
    parser.add_argument(
        '--yes',
        action='store_true',
        help='yes to remove'
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='verbose'
    )

    global args
    args = parser.parse_args()

    if args.new_user:
        user = args.new_user
        user_home = v12n_home + user
        new_user(user, user_home)

    if args.remove_user:
        remove_user(args.remove_user)

    if args.set:
        if args.new_domain:
            dictdom = to_dict(args.new_domain)
            dictset = to_dict(args.set)
            check_keys(
                dictdom, '--new-domain'
            )
            check_keys(
                dictset, '--set'
            )
            user = dictdom['name']
            user_home = v12n_home + user
            dicted = fix_dict(
                dict(dictset, **dictdom), user
            )
            new_user(user, user_home)
            if dicted['packer'] == '':
                virt_install(
                    'iso', user, dicted
                )
            else:
                packer_up(
                    user, user_home, dicted
                )
                virt_install(
                    'image', user, dicted
                )
        else:
            dictset = to_dict(args.set)
            for key in dictset:
                try:
                    domain_action(
                        get_libvirt_conn(user), user, key, dictset[key]
                    )
                except KeyError:
                    if key == 'size':
                        try:
                            root = dictset['root']
                        except KeyError:
                            root = '/dev/sda1'
                        domain_vol_resize(
                            user, dictset['size'], root
                        )
                        sys.exit()
                    else:
                        print(
                            Color.FAIL, 'invalid key:', key, Color.ENDC
                        )
                        sys.exit()
                    pass

    if args.new_domain and args.set is None:
        print(
            Color.FAIL, 'use --set', Color.ENDC
        )

    if len(sys.argv) < 2:
        parser.print_help()
        print(
            Color.OKGREEN, 'version:', my_version, Color.ENDC
        )
    if args.start:
        domain_action(
            get_libvirt_conn(user), user, 'start', 0
        )
    if args.stop:
        domain_action(
            get_libvirt_conn(user), user, 'stop', 0
        )
    if args.info:
        info = args.info
        domain_info(
            get_libvirt_conn(user), user, info
        )

    if args.add_bridge:
        brigdict = to_dict(args.add_bridge)
        check_keys(
            brigdict, '--add-bridge'
        )
        setup_bridge(brigdict)

    if args.hv_up:
        if args.packer_git:
            hv_up(args.packer_git)
        else:
            print(
                Color.FAIL, 'packer git address is not specified', Color.ENDC
            )
            sys.exit()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        sys.exit()
    except KeyboardInterrupt:
        sys.exit()
