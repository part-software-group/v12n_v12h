#!/usr/bin/env python3
import os, sys, argparse, string, shutil, random
import socket, libvirt, subprocess, hashlib, json

my_name = '[v12h]'
my_version = '1'
v12n_home = '/v12n/'
local_libvirt = '/.local/share/libvirt/'
show, password_num = False, 12
packer_default = 'debian.json'

class bcolors:
    OKGREEN = '\033[92m' + my_name
    WARNING = '\033[93m' + my_name
    FAIL = '\033[91m' + my_name
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def check_root():
    """some functions need root permission"""
    if os.geteuid() != 0:
        sys.exit(bcolors.FAIL + ' error: must be root' + bcolors.ENDC)

def su_user(user, command):
    """su as user that runs domain"""
    check_root()
    if user:
        r = subprocess.call(['su', '-', user, '-c', command])
        if args.verbose:
            print(bcolors.OKGREEN, command, r, bcolors.ENDC)
    else:
        print(bcolors.WARNING, 'no domain name specified' + bcolors.ENDC)
    if r == 0:
        return(True)
    else:
        return(False)

def password_gen(size):
    """generating random password. copied form stack"""
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(size))

def md5(fname):
    """md5 the iso. copied form stack"""
    hash_md5 = hashlib.md5()
    with open(fname, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def vnc_port():
    """return available vnc port between 5900 to 5999. some copied from stack"""
    random_port = random.randint(5900, 5999)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('localhost', random_port)) != 0:
            return(random_port)

def new_user(user, user_home):
    """adding linux user"""
    check_root()
    password = password_gen(password_num)
    if args.show:
        print(bcolors.OKGREEN,
              'creating user', user, 'with password', password +
              bcolors.ENDC)
    else:
        print(bcolors.OKGREEN, 'creating user', user + bcolors.ENDC)
    r = subprocess.call(['useradd', '--comment', 'added_by_v12h',
                         '--create-home', '--home-dir', user_home,
                         '--no-user-group', '--group', 'kvm',
                         '--key', 'UID_MIN=2001',
                         '--key', 'UID_MAX=2050',
                         user])
    if r == 0:
        print(bcolors.OKGREEN,
              'user', user, 'created successfully' + bcolors.ENDC)
    else:
        sys.exit(bcolors.FAIL + ' error: adduser failed' + bcolors.ENDC)
    p1 = subprocess.Popen(['echo', user + ':' + password],
                           stdout = subprocess.PIPE)
    p2 = subprocess.Popen(['chpasswd' ], stdin = p1.stdout)
    p1.stdout.close()
    output = p2.communicate()[0]
    os.makedirs(user_home + local_libvirt)
    os.chmod(user_home, 0o750)
    subprocess.call(['chown', '-R', user + ':' + 'kvm', user_home])
    print(bcolors.OKGREEN, '$HOME is ' + user_home + bcolors.ENDC)

def remove_user(user):
    """removes everything"""
    if args.yes == False:
        prompt = input(bcolors.FAIL + ' removing user "' +
                       user + '"? (Y or whatever) ' + bcolors.ENDC)
        if prompt != 'Y':
            sys.exit()
    check_root()
    print( bcolors.FAIL, 'removing user', user, bcolors.ENDC)
    subprocess.call(['pkill', '-u', user])
    subprocess.call(['deluser', '--remove-home', user])
    print( bcolors.FAIL, 'removing', user, 'home', bcolors.ENDC)
    try:
        shutil.rmtree(v12n_home + user)
    except FileNotFoundError as e:
        sys.exit(bcolors.WARNING + v12n_home + user +
                 ' is already removed. nevermind ...' + bcolors.ENDC)

def packer_up(user, user_home, dicted):
    packer = dicted['packer']
    shutil.copytree(v12n_home + '/.packer/qemu', user_home + '/.packer/qemu')
    jtmplfile = user_home + '/.packer/qemu/debian/' + packer
    try:
        with open(jtmplfile, 'r') as json_file:
            json_data = json.load(json_file)
            for key in dicted:
                try:
                    val = dicted[key]
                except KeyError as e:
                    print(bcolors.FAIL, e, bcolors.ENDC)
                    remove_user(domain)
                json_data['variables'][key] = val
                if args.verbose:
                    print(bcolors.OKGREEN, key + ' set to ' + val, bcolors.ENDC)
    except FileNotFoundError as e:
        print(bcolors.FAIL, e)
        remove_user(user)
    with open(jtmplfile, 'w') as json_file:
        json_file.write(json.dumps(json_data, indent = 2))
    print(bcolors.OKGREEN, 'building packer image', bcolors.ENDC)
    if su_user(user, 'cd ' + user_home + '/.packer/qemu/debian&&' +
                'packer build ' + packer):
        print(bcolors.OKGREEN, 'image created successfully' + bcolors.ENDC)
    else:
        print(bcolors.FAIL, 'error: problem in build',
              'cleaning ...' + bcolors.ENDC)
        remove_user(user)

def virt_install(mode, user, dicted):
    domain = user
    try:
        cpu = dicted['cpu'] + ',maxvcpus=' + dicted['xcpu']
        memory = dicted['memory'] + ',maxmemory=' + dicted['xmemory']
        vnc = 'vnc,port=' + dicted['vnc']
        net = 'bridge=' + dicted['br'] + ',model=virtio'
    except KeyError as e:
        print(bcolors.FAIL, e, bcolors.ENDC)
        remove_user(user)
    default_opts = ['virt-install', '--connect', 'qemu:///session',
                    '--noautoconsole', '--virt-type', 'kvm', '--cpu', 'host',
                    '--boot', 'hd', '--name', domain, '--vcpus', cpu,
                    '--memory', memory, '--network', net,
                    '--graphics', vnc, '']
    cmd_default = ' '.join(default_opts)
    if mode == 'image':
        image_opts = ['--disk',
                      'format=raw,bus=virtio,cache=none,io=native,path=']
        image_args = ['$HOME', local_libvirt, '/images/',
                      dicted['hostname'], '.raw']
        cmd_image = ' '.join(image_opts)
        image = ''.join(image_args)
        virt_install_image = cmd_default + cmd_image + image
        print(bcolors.OKGREEN, 'installing image using virt-install',
              bcolors.ENDC)
        if su_user(user, virt_install_image):
            print(bcolors.OKGREEN, "vnc port:", dicted['vnc'], bcolors.ENDC)
            return True
        else:
            return False
    if mode == 'iso':
        poolb = 'pool=default,format=raw,bus=virtio,cache=none,io=native,size='
        try:
            poolz = ',size=' + dicted['size']
            iso_opts = ['--cdrom', dicted['iso'], '--disk',
                        poolb + dicted['size']]
        except KeyError as e:
            print(bcolors.FAIL, 'key', e, 'not found', bcolors.ENDC)
            remove_user(user)
        cmd_iso = ' '.join(iso_opts)
        virt_install_iso = cmd_default + cmd_iso
        if su_user(domain, virt_install_iso):
            print(bcolors.OKGREEN, "vnc port:", dicted['vnc'], bcolors.ENDC)
            return True
        else:
            return False

def to_dict(the_list):
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
            print('error in', the_list)
            sys.exit(bcolors.FAIL + ' use key=value,key=value format' +
                     bcolors.ENDC)
    return(the_dict)

def check_keys(dicted, which):
    dom_key_necss = ['name', 'iso']
    set_key_necss = ['cpu', 'memory', 'size', 'br']
    bridge_key_necss = ['if', 'br', 'ip', 'bg']
    which_dict = {'--new-domain': dom_key_necss,
                 '--set': set_key_necss,
                 '--add-bridge': bridge_key_necss}
    keys = which_dict[which]
    for key in keys:
        if key not in dicted:
            print(bcolors.FAIL, bcolors.BOLD + which,
                  str(keys), bcolors.ENDC)
            sys.exit(bcolors.FAIL + ' you forgot ' + bcolors.BOLD +
                     key + bcolors.ENDC)
    return(True)

def fix_dict(dicted, domain):
    key_defaults = {}
    try:
        key_defaults = {'username': domain, 'password': domain,
                        'vnc': str(vnc_port()), 'xcpu': dicted['cpu'],
                        'xmemory': dicted['memory'], 'hostname': domain,
                        'domain': socket.getfqdn(), 'md5': md5(dicted['iso']),
                        'apt_proxy': 'debian.asis.io', 'packer': ''}
    except KeyError:
       pass
    for keyd in key_defaults:
        try:
            dicted[keyd]
            if dicted['packer'] == 'default':
                dicted.update({'packer':packer_default})
        except KeyError:
            pass
            dicted.update({keyd:key_defaults[keyd]})
    return(dicted)

def get_conn(domain):
    try:
        conn = libvirt.open('qemu+unix:///session?socket=' +
                            v12n_home + domain +
                            '/.cache/libvirt/libvirt-sock')
    except libvirt.libvirtError as e:
        sys.exit(bcolors.FAIL + ' could not connect' + bcolors.ENDC)
    if conn == None:
        sys.exit(bcolors.FAIL +
                 ' failed to open connection to qemu:///session' +
                 bcolors.ENDC)
    else:
        return(conn)

def dom_info(conn, domain):
    dom = conn.lookupByName(domain)
    dom_status = {libvirt.VIR_DOMAIN_RUNNING: 'active',
                  libvirt.VIR_DOMAIN_SHUTDOWN: 'shutdown',
                  libvirt.VIR_DOMAIN_SHUTOFF: 'destroyed'}
    try:
        xcpu = dom.maxVcpus()
    except libvirt.libvirtError:
        xcpu = 'DOMAIN MUST BE ACTIVE'
    MBFACTOR = float(1<<10)
    infos = {'name': dom.name(),
             'status': dom_status[dom.state()[0]],
             'cpu': dom.info()[3],
             'max cpu': xcpu,
             'memory': dom.info()[2]/MBFACTOR,
             'max memory': dom.info()[1]/MBFACTOR,
             'autostart': dom.autostart(),
             'uuid': dom.UUIDString()}
    for info in infos:
        print(bcolors.OKGREEN, info + ':', infos[info], bcolors.ENDC)
    conn.close()

def dom_act(conn, domain, act, n):
    dom = conn.lookupByName(domain)
    acts = {'start': 'dom.create()',
            'stop': 'dom.destroy()',
            'autostart': 'dom.setAutostart(',
            'cpu': 'dom.setVcpus(',
            'memory': 'dom.setMemory('}
    try:
        if args.verbose:
            print(act)
        if n == 0:
            exec(acts[act])
        else:
            print(n)
            exec(acts[act] + n + ')')
        print(bcolors.OKGREEN, dom.name(), act, 'set successfull', bcolors.ENDC)
    except libvirt.libvirtError as e:
        pass
    conn.close()

def hv_up(packer_git):
    """setup all needed for a host to be a kvm hv"""
    check_root()
    if not os.path.exists(v12n_home):
        os.makedirs(v12n_home + '/.iso')
    if not os.path.exists('/etc/qemu'):
        os.makedirs('/etc/qemu')
        print(bcolors.OKGREEN, v12n_home, 'created' + bcolors.ENDC)
    subprocess.call(['apt-get', 'update'])
    subprocess.call(['apt-get', '--yes', '--no-install-recommends', 'install',
                     'atop', 'htop', 'git', 'screen', 'udhcpd', 'packer',
                     'parted', 'qemu-utils', 'qemu-kvm', 'libguestfs-tools',
                     'libvirt-clients', 'libvirt-daemon-system',
                     'virtinst', 'bridge-utils' ] )
    subprocess.call(['git', '-C', v12n_home, 'clone',
                     '--depth', '1', packer_git, v12n_home + '.packer'])

def setup_bridge(brigdict):
    """setting up bridge interface and qemu related stuff"""
    check_root()
    bo = brigdict['if']
    bf = brigdict['br']
    bi = brigdict['ip']
    bg = brigdict['bg']
    subprocess.call(['mv', '/etc/network/interfaces',
                           '/etc/network/interfaces.old'])
    with open('/etc/network/interfaces', 'w+') as lo:
        lo.write('# added by v12h\n'
                 'auto lo\n'
                 'iface lo inet loopback\n'
                 'source-directory /etc/network/interfaces.d\n')
    with open('/etc/network/interfaces.d/' + bf, 'w+') as br:
        br.write('# added by v12h\n'
                 'auto ' + bf + '\n'
                 'iface ' + bf + ' inet static\n'
                 '  address ' + bi + '\n'
                 '  gateway ' + bg + '\n'
                 '  bridge_ports ' + bo + '\n'
                 '  bridge_stp off\n'
                 '  bridge_fd 0\n')
    with open('/etc/qemu/bridge.conf', 'w+') as bc:
        bc.write('# added by v12h\n'
                 'allow ' + bf + '\n')
    subprocess.call(['ip', 'address', 'flush', bo, 'scope', 'global'])
    subprocess.call(['ifup', bf])
    subprocess.call(['setcap',
                     'cap_net_admin+ep',
                     '/usr/lib/qemu/qemu-bridge-helper'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--new-domain', '-n', help = 'add new domain')
    parser.add_argument('--set', '-s', help = 'set domain attributes',
                        nargs = '?', const = os.environ.get('USER'))
    parser.add_argument('--show', help = 'show password', action = 'store_true')
    parser.add_argument('--start', '-r', help = 'start domain',
                        nargs = '?', const = os.environ.get('USER'))
    parser.add_argument('--stop', '-d', help = 'stop domain',
                        nargs = '?', const = os.environ.get('USER'))
    parser.add_argument('--info', '-i', help = 'domain info',
                        nargs = '?', const = os.environ.get('USER'))
    parser.add_argument('--add-bridge', help = 'if=?,br=?,ip=?,bg=?')
    parser.add_argument('--hv-up', help = 'rise up', action = 'store_true')
    parser.add_argument('--packer-git', help = 'packer git address')
    parser.add_argument('--new-user', help = 'add new user')
    parser.add_argument('--remove-user', help = 'remove everthing')
    parser.add_argument('--yes', help = 'yes to remove', action = 'store_true')
    parser.add_argument('--verbose', '-v', help = 'verbose',
                        action = 'store_true')
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
            check_keys(dictdom, '--new-domain')
            check_keys(dictset, '--set')
            user = dictdom['name']
            user_home = v12n_home + user
            dicted = fix_dict(dict(dictset, **dictdom), user)
            new_user(user, user_home)
            if dicted['packer'] == '':
                virt_install('iso', user, dicted)
            else:
                packer_up(user, user_home, dicted)
                virt_install('image', user, dicted)
        else:
            user = os.environ.get('USER')
            dictset = to_dict(args.set)
            for key in dictset:
                try:
                    dom_act(get_conn(user), user, key, dictset[key])
                except KeyError:
                    print(bcolors.FAIL, 'error: invalid', key, bcolors.ENDC)
                    pass

    if len(sys.argv) < 2:
        parser.print_help()
    if args.start:
        user = args.start
        dom_act(get_conn(user), user, 'start', 0)
    if args.stop:
        user = args.stop
        dom_act(get_conn(user), user, 'stop', 0)
    if args.info:
        user = args.info
        dom_info(get_conn(user), user)

    if args.add_bridge:
        brigdict = to_dict(args.add_bridge)
        check_keys(brigdict, '--add-bridge')
        setup_bridge(brigdict)

    if args.hv_up:
        if args.packer_git:
            hv_up(args.packer_git)
        else:
            sys.exit(bcolors.FAIL +
                     ' error: packer git address is not specified' +
                     bcolors.ENDC)

if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit as sys_e:
        sys.exit(sys_e.code)
    except KeyboardInterrupt:
        logging.debug('', exc_info = True)
        print_stderr(_('aborted at user request'))
    #except Exception as main_e:
     #   fail(main_e)
